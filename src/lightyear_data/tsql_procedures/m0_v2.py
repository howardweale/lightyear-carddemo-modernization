"""Public-corpus procedure-level acceptance, recomputed from complete paired cases.

No verdict overrides: all cases, wrong variants and policy obligations survive.
SQL coverage is the union of exact source sites across declared fresh cases.
PG branch completion requires one native case to prove a complete module: no
union of anonymous branch fractions is invented.
"""
from collections import defaultdict
from copy import deepcopy
import json
from pathlib import Path
from .coverage import replay_coverage, summarize, _inside
from .native_evidence import replay_pair, verify, sha


def expand(items):
    result=[]
    for item in items:
        base=deepcopy(item);base['scenario']='primary';result.append(base)
        for scenario in item.get('coverage_scenarios',[]):
            extra=deepcopy(item)
            extra.update(assets=deepcopy(scenario['assets']),
                         calling_convention=deepcopy(scenario['calling_convention']),
                         scenario=scenario['id'])
            result.append(extra)
    cases=[]
    for item in result:
        for case in item['cases']:
            one=deepcopy(item);one['cases']=[case]
            if len(item['cases'])>1:one['scenario']+=':'+case['id']
            cases.append(one)
    return cases


def coverage_union(records):
    if not records:raise ValueError('coverage-cases-missing')
    versions={v['raw']['schema'].rsplit('/',1)[-1] for v in records}
    if len(versions)!=1:raise ValueError('coverage-mixed-revisions')
    from .coverage import replay_coverage, summarize
    if versions=={'2'}:
        from .coverage_v2 import replay_coverage, summarize
    groups=defaultdict(list);source_hashes={}
    collectors=set()
    for record in records:
        result=replay_coverage(record);collectors.add(result['collector'])
        for raw, summary in zip(record['raw']['modules'],result['modules'],strict=True):
            key=summary['name'];h=summary['source_sha256']
            if source_hashes.setdefault(key,h)!=h:raise ValueError('coverage-source-changed-across-cases')
            groups[key].append((raw,summary))
    if len(collectors)!=1:raise ValueError('coverage-collector-changed')
    modules=[]
    for name,rows in groups.items():
        raw,first=rows[0];row=deepcopy(first)
        if first['branches'] is not None:
            statements=raw['parsed']['coverage_catalogue']['statements']
            hits=set();branches={};handlers={}
            for raw,s in rows:
                if raw['parsed']['coverage_catalogue']['statements']!=statements:raise ValueError('coverage-sites-changed')
                for offset in s['native_started_offsets_utf16']:
                    candidates=[site for site in statements if _inside(offset,site)]
                    if candidates:hits.add(min(candidates,key=lambda v:v['length_utf16'])['start_utf16'])
                for edge in s['branches']:
                    key=(edge['site'],edge['edge']);branches[key]=branches.get(key,False) or edge['hit']
                for e in s['error_paths']:handlers[e['site']]=handlers.get(e['site'],False) or e['hit']
            row['statements_hit']=len(hits)
            row['branches']=[dict(site=k[0],edge=k[1],hit=v) for k,v in sorted(branches.items())]
            row['error_paths']=[dict(site=k,hit=v) for k,v in sorted(handlers.items())]
            row['uncovered_lines']=sorted({s['line'] for s in statements if s['start_utf16'] not in hits})
            row['native_started_offsets_utf16']=sorted({v for _,s in rows for v in s['native_started_offsets_utf16']})
        else:
            sites={v['stmtid'] for v in raw['after'] if v['stmtname']!='statement block'}
            hits=set()
            for r,_ in rows:
                if {v['stmtid'] for v in r['after'] if v['stmtname']!='statement block'}!=sites:
                    raise ValueError('profiler-sites-changed')
                hits.update(v['stmtid'] for v in r['after'] if v['stmtid'] in sites and v['exec_stmts'])
            fraction=max(s['branch_fraction'] for _,s in rows)
            row.update(statements_hit=len(hits),branch_fraction=fraction,
                uncovered_lines=sorted({v['lineno'] for v in raw['after'] if v['stmtid'] in sites-hits}),
                error_paths=[dict(site='one-native-case-complete-module-branches-and-handlers',hit=fraction==1)],
                error_path_resolution='at least one retained native case proves all module branches; fractions never added')
        modules.append(row)
    return summarize(next(iter(collectors))+'+declared-cases/1',modules)


def accept(root, corpus, plan, records, public):
    """Called only after owned cleanup, and independently during terminal replay."""
    root=Path(root);expected=[];items={i['id']:i for i in corpus['procedures']}
    if (len(items)!=43 or {i['trap_family'] for i in items.values()}!=set(range(1,27)) or
            plan['variants']!=['correct','wrong'] or set(plan['ids'])!=set(items) or
            sha((root/'corpus.json').read_bytes())!=plan['corpus_sha256']):
        raise ValueError('M0-corpus-plan-closure')
    for item in expand(corpus['procedures']):
        for variant in ('correct','wrong'):
            for repeat in range(item['cases'][0]['repeated_runs']):
                expected.append((item['id'],variant,item['scenario'],repeat+1))
    actual=[(r['id'],r['variant'],r.get('scenario','primary'),r['repeat']) for r in records]
    if sorted(actual)!=sorted(expected) or len(set(actual))!=len(actual):raise ValueError('M0-case-closure')
    groups=defaultdict(list);reset_times=defaultdict(list)
    for r in records:
        folder=root/f"pair-{r['index']:03d}-{r['id']}-{r['variant']}-{r['repeat']}"
        manifest=verify(json.loads((folder/'manifest.json').read_bytes()),public)
        if manifest['plan_sha256']!=sha((root/'plan.json').read_bytes()):raise ValueError('M0-plan-binding')
        result=replay_pair(folder,public,r['manifest_sha256'])['comparison']
        item=next(i for i in expand([items[r['id']]]) if i['scenario']==r.get('scenario','primary'))
        if manifest['assets']!=item['assets'] or result['mapping']['calling_convention']!=item['calling_convention']:
            raise ValueError('M0-case-assets')
        if not result.get('coverage_qualification',{}).get('passed'):raise ValueError('M0-collector-unqualified')
        lanes={lane:json.loads((folder/(lane+'.json')).read_bytes()) for lane in ('source','target')}
        for lane,value in lanes.items():
            reset_times[lane].append(value['reset']['reset_elapsed_seconds'])
        groups[(r['id'],r['variant'])].append((r,result,lanes))
    outcomes=[]
    for (name,variant),rows in sorted(groups.items()):
        item=items[name];policy=item['expected']['policy_required']
        coverage={lane:coverage_union([v[lane]['observation']['coverage'] for _,_,v in rows])
                  for lane in ('source','target')}
        differences=[d for _,c,_ in rows for d in c['differences']]
        unresolved=[d for _,c,_ in rows for d in c['unresolved']]
        if differences:
            verdict='divergent';passed=variant=='wrong'
        elif policy:
            passed=all(c['verdict']=='insufficient-evidence' and any(u['classification']=='policy-decision-required' for u in c['unresolved']) for _,c,_ in rows)
            verdict='policy-decision-required'
        else:
            verdict='equivalent' if not unresolved and all(c['eligible'] for c in coverage.values()) else 'insufficient-evidence'
            passed=variant=='correct' and verdict=='equivalent'
        outcomes.append(dict(id=name,variant=variant,trap_family=item['trap_family'],verdict=verdict,
            accepted=passed,case_manifests=[r['manifest_sha256'] for r,_,_ in rows],coverage=coverage,
            unresolved=unresolved,policy_is_not_equivalence=policy))
    return dict(schema='tsql-M0-acceptance/2',passed=all(r['accepted'] for r in outcomes),
        procedures=len(items),native_pairs=len(records),variants=outcomes,
        reset_benchmark={lane:dict(count=len(v),total_seconds=sum(v),mean_seconds=sum(v)/len(v),
                                  minimum_seconds=min(v),maximum_seconds=max(v)) for lane,v in reset_times.items()},
        model_calls=0,claim='Operator review; not independent attestation; public corpus only')
