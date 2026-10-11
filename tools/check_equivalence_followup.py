"""B1 compiler comparison, class census and 200-case targeted host experiments."""
import argparse
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


def check(campaign,job):
    started=time.monotonic()
    campaign=Path(campaign).resolve();provenance=validate_campaign(campaign,job)
    output=campaign/'equivalence-followup';output.mkdir()
    program=PROGRAMS[job];text=(ROOT/f'spec/mainframe/public-source/{program}.cbl').read_text()
    census=appl_result_census(text,program);write_json(output/'appl-result-census.json',census)
    inventory={r['id']:r for r in generate(text,program)}; old=population(job)
    fresh={r['id']:r for r in json.loads((campaign/'mutation-results.json').read_text())}
    baseline=compiler_output(output/'TCE-original',program);results=[];baseline_cases={}
    for identifier,previous in old.items():
        if time.monotonic()-started>7800:raise RuntimeError('B1-targeted-wall-budget-exhausted; partial evidence retained')
        if sum(p.stat().st_size for p in campaign.rglob('*') if p.is_file())>8*1024**3:raise RuntimeError('B1-output-budget-exhausted; partial evidence retained')
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
                name=f"b1-target:{job}:{target['name']}:{index:03d}";fault,base,changed=challenges[index%len(challenges)]
                key=(name,fault)
                if key not in baseline_cases:
                    basefolder=output/'target-baselines'/f"{target['name']}-{index:03d}-{fault or 'normal'}";basefolder.parent.mkdir(exist_ok=True)
                    baseline_cases[key]=attempt(base,name,basefolder)
                normal=baseline_cases[key];folder=output/'targets'/identifier/f'{index:03d}';folder.parent.mkdir(parents=True,exist_ok=True)
                actual=attempt(changed,name,folder)
                classification=targeted_outcome(normal,actual)
                item=dict(index=index,case=name,fault=fault,baseline=normal,actual=actual,status=classification)
                measurements.append(item)
                if classification.startswith('killed-') and not row['refuted']:row.update(refuted=True,witness=item)
            write_json(output/'targets'/identifier/'results.json',measurements)
            row.update(targeted_accounting(measurements))
            row['targeted_limitation']='Finite cases and selected declared status paths only; full internal-byte/ABI arguments retain their separately recorded compiler probes and scope.'
            row['status']='refuted-by-targeted-campaign' if row['refuted'] else 'equivalent (argued, individual review pending)'
        results.append(row);write_json(output/'results.json',results)
    counts=Counter(r['status'] for r in results)
    current=json.loads((campaign/'review-summary.json').read_text())
    differences=[dict(id=r['id'],historical=r.get('status'),fresh=fresh[r['id']]['status'])
        for r in json.loads((ROOT/f'docs/factory/systematic-{job.lower()}-review311.json').read_text())['mutants']
        if r['id'] in fresh and r['status']!=fresh[r['id']]['status']]
    acceptance=json.loads((ROOT/'docs/factory/equivalence-decision-binding-2026-10-11.json').read_text())
    register=json.loads((ROOT/'docs/factory/keep-or-fix-register.json').read_text())
    scoped={scope:mutation_threshold_report(list(fresh.values()),results,acceptance['accepted_mutants'],scope,register) for scope in ('twin','zos-facing')}
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
    complete={scope:amended_threshold_report(assessment,current['after_faults'],{k:len(v) for k,v in values.items()},list(values),head)
              for scope,assessment in scoped.items()}
    write_json(output/'threshold-2-by-scope.json',complete)
    accepted_ids={r['id'] for r in acceptance['accepted_mutants']}
    for row in results:row['operator_review']='accepted by Howard, AI-assisted stated scope' if row['id'] in accepted_ids else 'not individually accepted'
    write_json(output/'results.json',results)
    review=[r for r in results if r['status']=='equivalent (argued, individual review pending)']
    write_json(output/'remaining-review-packet.json',dict(review_class='AI-assisted operator review pending; not independent attestation',job=job,mutants=review,already_accepted_ids=sorted(set(r['id'] for r in review)&accepted_ids),requires_new_review_ids=sorted(r['id'] for r in review if r['id'] not in accepted_ids)))
    result=receipt(output/'summary.json',phase='B1-equivalence-followup',job=job,population=len(old),counts=dict(counts),
        class_census=census['content_sha256'],fresh_sites=current['mutant_count'],expected_sites={'INTCALC':421,'POSTTRAN':483}[job],
        fresh_refusals=current['not_compiled'],retained_disposition_differences=differences,
        target_cases=sum(r.get('targeted_cases',0) for r in results),target_valid_comparisons=sum(r.get('targeted_valid_comparisons',0) for r in results),
        target_evidence_gap_ids=[r['id'] for r in results if r.get('targeted_cases') and not r['targeted_evidence_complete']],
        target_refutations=sum(r['refuted'] for r in results),
        individually_reviewable=len(review),threshold_by_scope=complete,acceptance_decision=acceptance['decision_content_sha256'],compiler_scope='pinned GnuCOBOL twin, never a z/OS compiler proof',
        current_head=head,campaign_manifest_sha256=provenance['content_sha256'],model_calls=0)
    print(json.dumps(result,indent=2))
    if current['mutant_count']!=result['expected_sites']:raise AssertionError('B1-fresh-site-count')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('campaign',type=Path);parser.add_argument('job',choices=PROGRAMS)
    args=parser.parse_args();check(args.campaign,args.job)
