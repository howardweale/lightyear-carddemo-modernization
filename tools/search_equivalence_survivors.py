"""Coverage-directed bounded public search; only two executed lanes can kill."""
import json
from pathlib import Path
import re
import shutil
import subprocess
from lightyear_mainframe.equivalence_automation import PROGRAMS,digest,sealed
from lightyear_mainframe.legacy_twin import ROOT,build
from lightyear_mainframe.scenario_coverage import code,observe
from lightyear_mainframe.systematic_mutation import outcome
from tools.check_factory_review import attempt


def search(job,baseline,resolutions,output,start):
    from tools.run_equivalence_automation import budgets,write
    from lightyear_mainframe.equivalence_scenarios import identifier
    from lightyear_mainframe.targeted_witness import PROFILES
    pending={r['id']:r for r in resolutions if r['status']=='unresolved'}
    if not pending:return dict(status='nothing-unresolved',generated_cases=0,kills=0)
    target=output/'search';target.mkdir();control=target/'control';observer=target/'observer'
    build(control,jobs=[job])
    from lightyear_mainframe.scenario_coverage import instrument,VERBS
    original=(ROOT/f'spec/mainframe/public-source/{PROGRAMS[job]}.cbl').read_text()
    traced,inventory=instrument(original,PROGRAMS[job]);source_lines=original.splitlines();derived=[]
    for line in traced.splitlines():
        derived.append(line)
        marker=re.fullmatch(r'      \*LY-ORIGINAL-LINE=(\d+)',line)
        if marker:
            number=int(marker[1]);words=code(source_lines[number-1]).split()
            if words and words[0] in VERBS-{'DISPLAY','CONTINUE','EXIT'}:
                derived.append("           DISPLAY 'LYC|M|"+str(number)+"|entered'")
    probe=dict(id='equivalence-statement-observer',operator='observer',line=1,end_line=len(source_lines),
               source_sha256=digest(original.encode()),original='\n'.join(source_lines),replacement='\n'.join(derived))
    build(observer,systematic=probe,jobs=[job])
    triaged={r['id']:r for r in baseline['rows']};counts={mid:0 for mid in pending}
    built={};records=[];killed=[];regressions=[];generated=0
    def mutant_build(mid):
        if mid not in built:
            folder=target/'builds'/mid
            try:build(folder,systematic=triaged[mid]['mutant'],jobs=[job]);built[mid]=folder
            except (ValueError,RuntimeError,subprocess.TimeoutExpired) as error:
                built[mid]=None;pending[mid]['search_refusal']=str(error)
        return built[mid]
    def run_case(case,mid,index):
        nonlocal generated
        budgets(start,output,0,generated+1);generated+=1
        folder=target/'cases'/f'{index:04d}';folder.mkdir(parents=True)
        base=attempt(control,case,folder/'original')
        changed_build=mutant_build(mid)
        changed=attempt(changed_build,case,folder/'mutant') if changed_build else dict(status='execution-refusal',reason='compiler-refusal')
        classification=outcome(base,changed)
        item=dict(case=case,id=mid,status=classification,baseline=base,actual=changed)
        if classification.startswith('killed-'):
            proof=sealed(dict(head=baseline['head'],program=job,mutant_sha256=digest(triaged[mid]['mutant']),
                              scenario=case,baseline=base,actual=changed,status=classification,
                              original_run=f'search/cases/{index:04d}/original/run-receipt.json',
                              mutant_run=f'search/cases/{index:04d}/mutant/run-receipt.json'))
            write(folder/'kill.json',proof)
            route='S3' if case.startswith('equivalence-cex:') else 'S4'
            pending[mid].update(status='killed',route=route,basis='executed-output-difference',
                                evidence=[dict(path=f'search/cases/{index:04d}/kill.json',sha256=digest(proof))])
            killed.append(mid);regressions.append(dict(id=mid,scenario=case,proof=proof['content_sha256']))
            del pending[mid]
        else:shutil.rmtree(folder)
        records.append(item);counts[mid]+=1
    # SAT is a candidate only: unsupported dataset bindings remain unresolved.
    for mid in list(sorted(pending)):
        row=pending[mid]
        if row.get('counterexample'):
            try:
                local=json.loads((output/'mutants'/mid/'pair.json').read_text())
                case=identifier(job,local,row['counterexample'])
                run_case(case,mid,generated)
            except ValueError as error:row['counterexample_replay_unresolved']=str(error)
    # Observe original branch coverage before selecting which survivor to challenge.
    # Existing public profiles have 200 deterministic variants each; the shared
    # 1,000-case cap includes all solver replay attempts above.
    candidates=[f'b1-target:{job}:{profile}:{index:03d}' for index in range(200) for profile in PROFILES]
    coverage_records=[]
    for case in candidates:
        if not pending or generated>=1000:break
        budgets(start,output,0,generated+1)
        obs_folder=target/'observation';obs=attempt(observer,case,obs_folder)
        covered=set();statements=set();branches=[]
        check_folder=target/'observation-control';observed_control=attempt(control,case,check_folder)
        observation_valid=outcome(observed_control,obs)=='survived'
        if obs['status']=='executed' and observation_valid:
            transcript=(obs_folder/'logs/program.stdout').read_text()
            covered={int(n) for n in re.findall(r'LYC\|P\|(\d+)\|entered',transcript)}
            statements={int(n) for n in re.findall(r'LYC\|M\|(\d+)\|entered',transcript)}
            branches=re.findall(r'LYC\|D\|(\d+)\|(true|false)',transcript)
        # Coverage ranks proximity only; it is never treated as a kill or proof.
        paragraphs=sorted(p['line'] for p in inventory['paragraphs'])
        def priority(mid):
            line=triaged[mid]['mutant']['line']
            paragraph=max((p for p in paragraphs if p<=line),default=0)
            return (line not in statements,paragraph not in covered,counts[mid],mid)
        mid=min(pending,key=priority)
        coverage_records.append(dict(case=case,paragraphs=sorted(covered),statements=sorted(statements),branches=branches,selected=mid,
                                     observer_control_agree=observation_valid,evidence='actual statement and branch probes, accepted only after unchanged control comparison'))
        if obs_folder.exists():shutil.rmtree(obs_folder)
        if check_folder.exists():shutil.rmtree(check_folder)
        run_case(case,mid,generated)
        write(target/'progress.json',dict(generated_cases=generated,kills=len(killed),remaining=len(pending)))
    write(target/'attempts.json',records);write(target/'coverage-selection.json',coverage_records)
    write(target/'regression-scenarios.json',regressions)
    return sealed(dict(status='complete',generated_cases=generated,budget=1000,kills=len(killed),
                       counterexample_kills=sum(r['scenario'].startswith('equivalence-cex:') for r in regressions),
                       remaining=len(pending),exhaustion_resolves_nothing=True,model_calls=0))
