"""B1 compiler comparison, class census and 200-case targeted host experiments."""
import argparse
from lightyear_mainframe.target_retention import Retention,size,BUDGET,paired_case
from lightyear_mainframe.campaign_provenance import sealed
from collections import Counter
import json
from pathlib import Path
import re
import shutil
import time
from lightyear_mainframe.legacy_twin import ROOT,PROGRAMS,FLAGS,execute,receipt,write_json,sha
from lightyear_mainframe.systematic_mutation import generate,apply,outcome
from lightyear_mainframe.equivalence_evidence import appl_result_census,class_covered,register_dependencies,mutation_threshold_report,amended_threshold_report
from lightyear_mainframe.targeted_witness import profile
from tools.check_factory_review import attempt
from lightyear_mainframe.campaign_provenance import validate as validate_campaign


def population(job):
    old=json.loads((ROOT/f'docs/factory/systematic-{job.lower()}-review311.json').read_text())['mutants']
    rows={r['id']:r for r in old if r['status']=='equivalent (argued, listed)'}
    for r in json.loads((ROOT/'docs/factory/post-campaign-equivalence-review311.json').read_text())['arguments']:
        if r['id'].startswith(PROGRAMS[job]+'-'):rows[r['id']]={**r,'disposition':r}
    return rows


def normalize_c(text):
    # Remove only comments and preprocessor line/debug location directives.
    # Quoted literal bytes and executable statements remain exact.
    token=re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*.*?\*/|//[^\n]*',re.S)
    text=token.sub(lambda m:'' if m[0].startswith(('/*','//')) else m[0],text)
    return '\n'.join(line.rstrip() for line in text.splitlines()
        if line.strip() and not re.match(r'^\s*#\s*(?:line\b|\d+\s+")',line))+'\n'


def compiler_output(folder,program,mutant=None):
    folder.mkdir(parents=True)
    for path in (ROOT/'spec/mainframe/copybooks').glob('*.cpy'):shutil.copyfile(path,folder/path.name)
    source=ROOT/f'spec/mainframe/public-source/{program}.cbl';(folder/source.name).write_bytes(source.read_bytes())
    if mutant:
        operand=folder/mutant.get('source_path',source.name)
        operand.write_text(apply(operand.read_text(),mutant),encoding='ascii')
    execute(['cobc','-C','-fixed','-std=ibm','-fsign=EBCDIC','-O2','-I','.',source.name],folder,folder/'compile-C')
    files={p.name:normalize_c(p.read_text()) for p in sorted(folder.glob(program+'*')) if p.suffix in ('.c','.h')}
    if not files or not any(x.endswith('.c') for x in files):raise ValueError('TCE-generated-C-unavailable')
    payload=json.dumps(files,sort_keys=True,separators=(',',':')).encode()
    (folder/'normalized-C.json').write_bytes(payload)
    return dict(sha256=sha(payload),files={name:sha(value.encode()) for name,value in files.items()},bytes=len(payload))


def targeted_outcome(baseline, actual):
    # Tool/runtime refusals are missing comparisons, not observed mutant kills.
    # Only two completed executions can establish a return-code/output delta.
    if baseline['status']!='executed':return 'baseline-refusal'
    if actual['status']!='executed':return 'mutant-execution-refusal'
    return outcome(baseline,actual)


def targeted_accounting(measurements):
    gaps=[dict(index=r['index'],case=r['case'],baseline_status=r['baseline']['status'],mutant_status=r['actual']['status'])
          for r in measurements if r['baseline']['status']!='executed' or r['actual']['status']!='executed']
    return dict(targeted_cases=len(measurements),targeted_valid_comparisons=len(measurements)-len(gaps),
        targeted_counts=dict(Counter(r['status'] for r in measurements)),
        targeted_fault_case_counts=dict(Counter(r['fault'] or 'normal' for r in measurements)),
        targeted_evidence_complete=len(measurements)==200 and not gaps,targeted_evidence_gaps=gaps)


def check(campaign,job,shard=0,shards=1):
    if not 0<=shard<shards or shards not in (1,2,4):raise ValueError('invalid-shard')
    started=time.monotonic()
    campaign=Path(campaign).resolve();provenance=validate_campaign(campaign,job)
    output=campaign/'equivalence-followup';output.mkdir()
    retention=Retention(output/'execution-retention')
    fresh_bytes=size(campaign)-size(output)
    program=PROGRAMS[job];text=(ROOT/f'spec/mainframe/public-source/{program}.cbl').read_text()
    census=appl_result_census(text,program);write_json(output/'appl-result-census.json',census)
    inventory={r['id']:r for r in generate(text,program)}; old=population(job)
    fresh={r['id']:r for r in json.loads((campaign/'mutation-results.json').read_text())}
    baseline=compiler_output(output/'TCE-original',program);results=[]
    for position,(identifier,previous) in enumerate(sorted(old.items())):
        if position%shards!=shard:continue
        if time.monotonic()-started>7800:raise RuntimeError('B1-targeted-wall-budget-exhausted; partial evidence retained')
        if size(output)>BUDGET:raise RuntimeError('B1-output-budget-exhausted; partial evidence retained')
        mutant=inventory.get(identifier); row=dict(id=identifier,prior_status=previous.get('status','survived'),TCE=None,refuted=False)
        if mutant is None:
            row.update(status='not-in-current-inventory',reason='review required; not silently excluded');results.append(row);continue
        argument=previous.get('disposition',{})
        if not isinstance(argument,dict):raise ValueError('missing-individual-argument:'+identifier)
        argument={**argument,'depends_on_register':register_dependencies(argument)}
        if identifier=='CBTRN02C-delete-MOVE-718-447':argument['review_classification']='equivalent (host-compiler-scoped)'
        row.update(argument=argument,mutant=mutant,fresh_status=fresh[identifier]['status'])
        try:
            compiled=compiler_output(output/'TCE'/identifier,program,mutant)
            row['TCE']=dict(original=baseline,mutant=compiled,identical=compiled==baseline,
                method='GnuCOBOL -O2 generated C, exact after only comment and line-directive removal',scope='pinned-host-compiler only; not z/OS')
        except (RuntimeError,ValueError) as error:row['TCE']=dict(status='compiler-refusal',detail=str(error))
        covered=class_covered(mutant,argument,census);row['class_covered']=covered
        if fresh[identifier]['status']=='not-compiled':row['status']='not-compiled (listed exclusion)'
        elif fresh[identifier]['status'].startswith('killed-'):
            row.update(status='refuted-by-fresh-campaign',refuted=True,witness=fresh[identifier]['killed_by'])
        elif row['TCE'].get('identical'):row['status']='equivalent (compiler-proven)'
        elif covered:row['status']='equivalent (class-proof)'
        else:
            target=profile(mutant,argument);row['target_plan']=target;measurements=[]
            challenges=[(None,campaign/'baseline',campaign/'mutants'/identifier/'build')]
            for challenge in fresh[identifier].get('fault_challenges',[]):
                fault=challenge['fault'];path=campaign/'mutants'/identifier/('fault-'+fault)/'build'
                base=campaign/'faults'/fault/'build'
                if path.exists() and base.exists() and challenge['status']!='fault-challenge-unavailable':challenges.append((fault,base,path))
            for index in range(200):
                if time.monotonic()-started>7800:raise RuntimeError('B1-targeted-wall-budget-exhausted; partial evidence retained')
                name=f"b1-target:{job}:{target['name']}:{index:03d}";fault,base,changed=challenges[index%len(challenges)]
                item=paired_case(retention,base,changed,name,index,row['refuted'],attempt,targeted_outcome)
                item['fault']=fault;measurements.append(item)
                if item['status'].startswith('killed-') and not row['refuted']:row.update(refuted=True,witness=item)
            (output/'targets'/identifier).mkdir(parents=True)
            write_json(output/'targets'/identifier/'results.json',measurements)
            row.update(targeted_accounting(measurements))
            row['targeted_limitation']='Finite cases and selected declared status paths only; full internal-byte/ABI arguments retain their separately recorded compiler probes and scope.'
            row['status']='refuted-by-targeted-campaign' if row['refuted'] else 'equivalent (argued, individual review pending)'
        results.append(row);write_json(output/'results.json',results)
    current=json.loads((campaign/'review-summary.json').read_text())
    # Observe diversity on this same compiled head's ordinary public/generated
    # baseline outputs, never by borrowing a historical or mutant output receipt.
    from lightyear_mainframe.records import load_copybook,from_ascii_fixed
    from lightyear_mainframe.zos_bindings import load_bindings,dataset_binding
    values={}; layouts={}
    for dd in (('ACCTFILE','TRANSACT') if job=='INTCALC' else ('ACCTFILE','TRANFILE','DALYREJS','TCATBALF')):
        layout=load_copybook(ROOT/dataset_binding(load_bindings(),job,'STEP15',dd)['copybook']);layouts[dd]=layout
        for f in layout.fields:
            if not f.filler:values[dd+':'+f.path]=set()
    for group in ('public','cases'):
        for folder in sorted((campaign/group).glob('*/after')):
            for dd,layout in layouts.items():
                path=folder/dd
                if not path.exists():continue
                for record in from_ascii_fixed(layout,path.read_bytes()):
                    for f in record['fields']:
                        if not f['filler']:values[dd+':'+f['path']].add(str(f['value']))
    if validate_campaign(campaign,job)['content_sha256']!=provenance['content_sha256']:raise ValueError('campaign-changed-during-followup')
    head=provenance['binding']['head']
    retained=retention.seal(head)
    usage=dict(job=job,shard=shard,shards=shards,wall_seconds=time.monotonic()-started,
        fresh_compiled_bytes=fresh_bytes,fresh_resource_usage=json.loads((campaign/'resource-usage.json').read_text()),targeted_bytes=size(output),targeted_budget_bytes=BUDGET,
        execution=retention.metrics())
    write_json(output/'resource-usage.json',sealed(usage))
    payload=dict(schema='equivalence-shard/1',head=head,job=job,shard=shard,shards=shards,
        population=sorted(old),selected=sorted(r['id'] for r in results),results=results,
        fresh=list(fresh.values()),current=current,diversity={k:len(v) for k,v in values.items()},
        census=census,provenance_sha256=provenance['content_sha256'],usage=usage,
        retention_manifest_sha256=retained['content_sha256'],
        measurements={p.relative_to(output).as_posix():sha(p.read_bytes()) for p in (output/'targets').glob('*/results.json')} if (output/'targets').exists() else {})
    if job=='INTCALC' and (campaign/'loader-domain-overlay.json').exists():
        from lightyear_mainframe.loader_domain import project, verify_seal
        overlay=verify_seal(json.loads((campaign/'loader-domain-overlay.json').read_bytes()))
        project(list(fresh.values()),overlay)
        payload['loader_domain_overlay']=overlay
    write_json(output/'shard.json',sealed(payload))
    if size(output)>BUDGET:raise RuntimeError('B1-targeted-output-budget-exhausted')
    if shards==1:finalize(output,job,head,results,fresh,current,{k:len(v) for k,v in values.items()},census,[payload])


def finalize(output,job,head,results,fresh,current,diversity,census,shard_records):
    old=population(job);counts=Counter(r['status'] for r in results)
    differences=[dict(id=r['id'],historical=r.get('status'),fresh=fresh[r['id']]['status'])
        for r in json.loads((ROOT/f'docs/factory/systematic-{job.lower()}-review311.json').read_text())['mutants']
        if r['id'] in fresh and r['status']!=fresh[r['id']]['status']]
    acceptance=json.loads((ROOT/'docs/factory/equivalence-decision-binding-2026-10-11.json').read_text())
    register=json.loads((ROOT/'docs/factory/keep-or-fix-register.json').read_text())
    scoped={scope:mutation_threshold_report(list(fresh.values()),results,acceptance['accepted_mutants'],scope,register) for scope in ('twin','zos-facing')}
    complete={scope:amended_threshold_report(assessment,current['after_faults'],diversity,list(diversity),head)
              for scope,assessment in scoped.items()}
    write_json(output/'threshold-2-by-scope.json',complete)
    if job=='POSTTRAN':
        from lightyear_mainframe.release_projection import review_projection
        projection=review_projection(list(fresh.values()),results,acceptance['accepted_mutants'],job,register)
        projection['head']=head
        write_json(output/'operator-review-projection.json',projection)
    if job=='INTCALC' and shard_records and all('loader_domain_overlay' in r for r in shard_records):
        from lightyear_mainframe.loader_domain import project
        projections=[project(r['fresh'],r['loader_domain_overlay']) for r in shard_records]
        if [[(v['id'],v['status']) for v in rows] for rows in projections].count([(v['id'],v['status']) for v in projections[0]])!=len(projections):
            raise ValueError('loader-domain-shard-projections-disagree')
        from lightyear_mainframe.release_projection import supplemental_acceptances
        supplemented,pending,supplement_sha=supplemental_acceptances(results,acceptance['accepted_mutants'],job,register)
        projected={scope:mutation_threshold_report(projections[0],results,supplemented,scope,register) if scope=='twin' else scoped[scope] for scope in ('twin','zos-facing')}
        from tools.crosscheck_release_threshold import check as crosscheck
        independent={scope:crosscheck(projections[0] if scope=='twin' else list(fresh.values()),results,supplemented if scope=='twin' else acceptance['accepted_mutants'],scope,projected[scope]) for scope in ('twin','zos-facing')}
        write_json(output/'loader-domain-review-projection.json',dict(schema='intcalc-loader-domain-review-projection/1',head=head,
            raw_thresholds=scoped,projected_thresholds=projected,independent_crosscheck=independent,overlays=[r['loader_domain_overlay'] for r in shard_records],
            effective=False,release_authorized=False,pending_effective_acceptances=pending,supplement_sha256=supplement_sha,limitation='Unsigned review projection only, conditional on explicit effectiveness signatures; no new z/OS-facing acceptance or active-policy change.'))
    accepted_ids={r['id'] for r in acceptance['accepted_mutants']}
    for row in results:row['operator_review']='accepted by Howard, AI-assisted stated scope' if row['id'] in accepted_ids else 'not individually accepted'
    write_json(output/'results.json',results)
    review=[r for r in results if r['status']=='equivalent (argued, individual review pending)']
    write_json(output/'remaining-review-packet.json',dict(review_class='AI-assisted operator review pending; not independent attestation',job=job,mutants=review,already_accepted_ids=sorted(set(r['id'] for r in review)&accepted_ids),requires_new_review_ids=sorted(r['id'] for r in review if r['id'] not in accepted_ids)))
    evidence_gaps=sorted({r['id'] for r in results if fresh[r['id']]['status']=='evidence-gap' or ('targeted_cases' in r and not r['targeted_evidence_complete'])})
    dispositions=dict(compiler_proven=counts['equivalent (compiler-proven)'],class_proof=counts['equivalent (class-proof)'],individually_argued=len(review),refuted=sum(r['refuted'] for r in results),evidence_gap=len(evidence_gaps),evidence_gap_ids=evidence_gaps,evidence_gap_overlaps_proof_categories=True)
    result=receipt(output/'summary.json',phase='B1-equivalence-followup',job=job,population=len(old),counts=dict(counts),disposition_counts=dispositions,
        class_census=census['content_sha256'],fresh_sites=current['mutant_count'],expected_sites={'INTCALC':421,'POSTTRAN':483}[job],
        fresh_refusals=current['not_compiled'],retained_disposition_differences=differences,
        target_cases=sum(r.get('targeted_cases',0) for r in results),target_valid_comparisons=sum(r.get('targeted_valid_comparisons',0) for r in results),
        target_evidence_gap_ids=[r['id'] for r in results if r.get('targeted_cases') and not r['targeted_evidence_complete']],
        target_refutations=sum(r['refuted'] for r in results),
        individually_reviewable=len(review),threshold_by_scope=complete,acceptance_decision=acceptance['decision_content_sha256'],compiler_scope='pinned GnuCOBOL twin, never a z/OS compiler proof',
        current_head=head,campaign_manifest_sha256=[r['provenance_sha256'] for r in shard_records],resource_usage=[r['usage'] for r in shard_records],model_calls=0)
    print(json.dumps(result,indent=2))
    if current['mutant_count']!=result['expected_sites']:raise AssertionError('B1-fresh-site-count')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('campaign',type=Path);parser.add_argument('job',choices=PROGRAMS)
    parser.add_argument('--shard',type=int,default=0);parser.add_argument('--shards',type=int,default=1)
    args=parser.parse_args();check(args.campaign,args.job,args.shard,args.shards)
