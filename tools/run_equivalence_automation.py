"""CI-only zero-model equivalence pipeline; emits immutable overlays, no activation."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

from lightyear_mainframe.equivalence_automation import (PROGRAMS, digest, sealed, verify, triage, load_ir,
                                                       historical_population, audit_samples, score)
from lightyear_mainframe.equivalence_compiler import require_ci, toolchain, adversarial_rules, compile_object
from lightyear_mainframe.equivalence_solver import pair, validate_pair, prove, recheck
from lightyear_mainframe.equivalence_classes import dead_store, class_contract, unobservable_counter
from lightyear_mainframe.legacy_twin import ROOT, write_json


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, value)


def markdown_triage(data):
    lines = ['# Equivalence triage — 2026-10-15', '', 'Candidate routes are work allocations, not promised resolutions. Unknown reachability stays unknown.', '',
             '| Program | Argued | Individual | Other survivors / evidence gaps | Inventory |', '|---|---:|---:|---:|---:|']
    for d in data:
        rows=d['rows']; lines.append(f"| {d['program']} | {sum(r['argued'] for r in rows)} | {sum(r['individual_review'] for r in rows)} | {sum(not r['argued'] for r in rows)} | {d['inventory_count']} |")
    lines += ['', '| Program | Route | Individual candidates | Survivor candidates | Proven expected resolutions |', '|---|---|---:|---:|---:|']
    for d in data:
        for route, counts in d['route_candidates'].items():
            lines.append(f"| {d['program']} | {route} | {counts['individual']} | {counts['survivors']} | 0 |")
    lines += ['', 'All rows, exact source bindings, PIC/USAGE metadata and located translation gaps are in the companion JSON. Historical decisions and scores are unchanged.']
    return '\n'.join(lines)+'\n'


def audit_request(job, head, baseline, samples, resolutions):
    ids=sorted(i for s in samples for i in s['items'])
    if not ids: return dict(status='no-machine-resolutions-to-audit', samples=samples)
    packet=sealed(dict(head=head, program=job, samples=samples, resolutions=[r for r in resolutions if r['id'] in ids]))
    contract=dict(schema='factory-contract/1',kind='equivalence-review',program=job if job in ('INTCALC','POSTTRAN') else 'factory',
                  sources=[dict(path=f'docs/factory/equivalence-evidence-2026-10-15/{job}/audit-packet.json',sha256=digest((json.dumps(packet,indent=2,sort_keys=True)+'\n').encode()),commit=head)],
                  details=dict(packet_sha256=digest(packet),items=ids,class_proof_sha256=None,reviewer_type='human',claim_scope='twin',dependencies=['run:'+digest(resolutions)]))
    from lightyear_control_tower.factory_policy import validate_contract
    validate_contract(contract)
    return dict(status='unsigned',contract=contract,packet=packet)


def budgets(start, output, solver_targets, generated_cases):
    if solver_targets > 200 or generated_cases > 1000 or time.monotonic()-start > 14400:
        raise RuntimeError('approved-budget-exhausted')
    if sum(p.stat().st_size for p in output.rglob('*') if p.is_file()) > 8589934592:
        raise RuntimeError('approved-output-budget-exhausted')


def route_counts(resolutions, *, held_out=False):
    return {route:dict(resolved=sum(r['route']==route and r['status'] in ('equivalent','killed') for r in resolutions),
        individual_resolved=sum(r['route']==route and r['individual_review'] and r['status'] in ('equivalent','killed') for r in resolutions),
        survivors_resolved=0 if held_out else sum(r['route']==route and not r['argued'] and r['status'] in ('equivalent','killed') for r in resolutions),
        kills=0 if held_out else sum(r['route']==route and r['status']=='killed' for r in resolutions)) for route in ('S1','S2','S3','S4')}


def execute_pipeline(job, output, head, search=True):
    require_ci(); output.mkdir(parents=True, exist_ok=False); start=time.monotonic()
    baseline=triage(ROOT,job,head); write(output/'triage.json',baseline)
    text,ir=load_ir(ROOT,PROGRAMS[job]); write(output/'typed-ir.json',ir)
    chain=toolchain(); write(output/'toolchain.json',chain)
    numeric_profile={k:chain['binary_profile'][k] for k in ('binary_truncate','byteorder')}
    tests=adversarial_rules(output/'normalization-tests');write(output/'normalization-tests.json',tests)
    original=compile_object(ROOT,output/'compiler/original',PROGRAMS[job])
    resolutions=[]; matches={}; validations=[]; class_validations=[]; solver_count=0
    matcher_hash=digest((ROOT/'src/lightyear_mainframe/equivalence_classes.py').read_bytes())
    for row in baseline['rows']:
        budgets(start,output,solver_count,0)
        mutant=row['mutant']; mid=row['id']; folder=output/'mutants'/mid; folder.mkdir(parents=True)
        result=dict(id=mid,program=job,head=head,mutant_sha256=digest(mutant),source_sha256=mutant['source_sha256'],
                    argued=row['argued'],individual_review=row['individual_review'],status='unresolved',route=None,evidence=[])
        gap=unobservable_counter(ir,text,mutant)
        if gap:
            write(folder/'oracle-gap.json',gap)
            result.update(status='unobservable',oracle_gap=gap)
            resolutions.append(result)
            continue
        match=dead_store(ir,text,mutant)
        if match:
            from lightyear_mainframe.equivalence_solver import statement
            local=pair(text,mutant,ir); following=text.splitlines()[match['overwrite_line']-1]
            after=statement(following,ir)
            class_pair=dict(original=after,mutant=after,fields={**local['fields'],**after['fields']},target=local['target'],
                            original_source=local['original_source']+'\n'+following,mutant_source=local['mutant_source']+'\n'+following)
            validation=validate_pair(class_pair,folder/'class-validation',**numeric_profile)
            class_validations.append(dict(id=mid,class_id=match['class_id'],passed=validation['enabled'],validation_sha256=validation['content_sha256']))
            if validation['enabled']:matches.setdefault(match['class_id'],{})[mid]=match
        try:
            obj=compile_object(ROOT,folder/'compiler',PROGRAMS[job],mutant)
            identity=sealed(dict(original=original,mutant=obj,toolchain_sha256=chain['content_sha256'],
                                 rules_test_sha256=digest(tests),identical=original['object_sha256']==obj['object_sha256']))
            write(folder/'compiler-proof.json',identity)
            if identity['identical']:
                result.update(status='equivalent',route='S1',basis='compiler-proven (normalized)',
                              evidence=[dict(path=f'mutants/{mid}/compiler-proof.json',sha256=digest(identity))])
        except (ValueError,RuntimeError,subprocess.TimeoutExpired) as error:
            result['compiler_refusal']=str(error)
        if result['status']=='unresolved' and solver_count<200:
            try:
                local=pair(text,mutant,ir)
                write(folder/'pair.json',local)
                # No local probe may exceed the approved program wall/output caps.
                solver_count+=1
                validation=validate_pair(local,folder/'solver',**numeric_profile)
                validations.append(dict(id=mid,**validation))
                if mutant['operator']=='rounded':class_validations.append(dict(id=mid,class_id='receiving-pic-identity/1',passed=validation['enabled'],validation_sha256=validation['content_sha256']))
                if validation['enabled']:
                    proof=prove(local,folder/'solver',validation,binary_truncate=numeric_profile['binary_truncate'])
                    recheck(folder/'solver')
                    if proof['result']=='unsat' and proof['complete_written_state']:
                        result.update(status='equivalent',route='S3',basis='solver-proven (local)',
                                      evidence=[dict(path=f'mutants/{mid}/solver/solver.json',sha256=digest(proof))])
                        if mutant['operator']=='rounded':
                            matches.setdefault('receiving-pic-identity/1',{})[mid]=dict(mutant_sha256=digest(mutant),pair_sha256=digest(local),solver_sha256=proof['content_sha256'],validation_sha256=validation['content_sha256'])
                    elif proof['result']=='sat': result['counterexample']=proof['counterexample_scaled_integers']
                    else: result['solver_unresolved']='numeric UNSAT without complete storage proof' if proof['result']=='unsat' else proof['result']
                else: result['solver_disabled']='encoder/twin disagreement; exact statement/PIC shape disabled'
            except (ValueError,RuntimeError,subprocess.TimeoutExpired) as error:
                result['solver_unresolved']=str(error)
        resolutions.append(result);write(output/'resolutions-in-progress.json',resolutions)
    write(output/'encoder-validation.json',sealed(dict(program=job,statements=validations,
          enabled=sum(v['enabled'] for v in validations),disabled=sum(not v['enabled'] for v in validations),
          minimum_inputs_per_statement=10000,model_calls=0)))
    # Every pre-existing class claim gets a fresh unsigned, source-bound request.
    legacy={}
    if job!='TRANREPT':
        from lightyear_mainframe.equivalence_evidence import appl_result_census,register_dependencies
        _,arguments,_=historical_population(ROOT,job)
        census=appl_result_census(text,PROGRAMS[job]);write(output/'legacy-class-census.json',census)
        for row in baseline['rows']:
            if row['current_basis']!='class':continue
            retained=arguments[row['id']];argument=retained.get('disposition',retained)
            legacy[row['id']]=dict(mutant_sha256=digest(row['mutant']),source_sha256=row['mutant']['source_sha256'],
                                   historical_basis='class',argument=argument,census_sha256=census['content_sha256'],
                                   register_dependencies=register_dependencies(argument),requires_argument_review=True)

    if legacy: matches['legacy-APPL-RESULT/1']=legacy
    requests=[]
    for name, members in sorted(matches.items()):
        packet=sealed(dict(program=job,head=head,class_id=name,matches=members,matcher_sha256=matcher_hash))
        filename=name.replace('/','-')+'.json';write(output/'class-packets'/filename,packet)
        request=class_contract(job,head,name,members,f'docs/factory/equivalence-evidence-2026-10-15/{job}/class-packets/{filename}',
                               digest((output/'class-packets'/filename).read_bytes()),matcher_hash)
        requests.append(request)
    write(output/'class-requests.json',requests)
    write(output/'class-validation.json',sealed(dict(program=job,held_out=job=='TRANREPT',head=head,
          matcher_sha256=matcher_hash,measurements=class_validations,
          disabled_classes=sorted({v['class_id'] for v in class_validations if not v['passed']}))))
    search_report=dict(status='not-supported-for-held-out-harness' if job=='TRANREPT' else 'not-run',generated_cases=0,kills=0)
    if search and job!='TRANREPT':
        from tools.search_equivalence_survivors import search as directed_search
        search_report=directed_search(job,baseline,resolutions,output,start)
    write(output/'directed-search.json',search_report)
    run_hash=digest(dict(head=head,baseline=baseline['content_sha256'],toolchain=chain['content_sha256'],resolutions=resolutions))
    samples=audit_samples(resolutions,run_hash);audit=audit_request(job,head,baseline,samples,resolutions)
    write(output/'audit-request.json',audit)
    if audit.get('packet'): write(output/'audit-packet.json',audit['packet'])
    remaining=[dict(**r, output_slice=next(x['output_slice'] for x in baseline['rows'] if x['id']==r['id'])) for r in resolutions if r['status'] not in ('equivalent','killed')]
    remaining.sort(key=lambda r:(r['output_slice']['reaches_money'] is not True,r['output_slice']['reaches_control'] is not True,r['output_slice']['reaches_output'] is not True,r['output_slice']['output_distance'] if r['output_slice']['output_distance'] is not None else 10**9,r['id']))
    write(output/'remaining-review.json',sealed(dict(drafting='structured evidence only; no model',rows=remaining,
          assumed_minutes_per_packet=5,estimated_person_minutes=5*len(remaining),estimate_not_observation=True)))
    before=None;after=None
    if job!='TRANREPT':
        old=verify(json.loads((ROOT/f'docs/factory/equivalence-baseline-2026-10-15/{job}.json').read_text()))['mutants']
        inventory_ids={r['id'] for r in __import__('lightyear_mainframe.systematic_mutation',fromlist=['generate']).generate(text,PROGRAMS[job])}
        unresolved={r['id'] for r in baseline['rows']}
        kills=[r['id'] for r in old if r['id'] in inventory_ids and r['status'].startswith('killed-') and r['id'] not in unresolved]
        before=score(baseline['inventory_count'],kills,[],[])
        after=score(baseline['inventory_count'],kills,[],resolutions)
    summary=sealed(dict(schema='equivalence-automation/1',head=head,program=job,held_out=job=='TRANREPT',run_sha256=run_hash,
                        baseline=baseline['baseline_counts'],routes=route_counts(resolutions,held_out=job=='TRANREPT'),
                        argued_resolved=sum(r['argued'] and r['status'] in ('equivalent','killed') for r in resolutions),
                        argued_total=sum(r['argued'] for r in resolutions),unresolved=len(remaining),
                        unobservable=sum(r['status']=='unobservable' for r in resolutions),
                        before=before,after=after,audit=samples,class_requests=len(requests),
                        solver_targets=solver_count,generated_cases=search_report['generated_cases'],model_calls=0,
                        disabled_encoders=[v['id'] for v in validations if not v['enabled']],
                        unsupported_limits=['No paragraph/path-to-output solver encoding','No ON SIZE ERROR handlers, division or alias encoder','No held-out executable application harness'],
                        release_authorized=False,qualification_credit=False,claim_scope='twin'))
    ledger=sealed(dict(head=head,program=job,rows=resolutions))
    write(output/'resolutions.json',ledger)
    from lightyear_mainframe.equivalence_projection import project
    write(output/'signature-projection.json',project(ledger,
        [r for r in requests if r['class_proof']['class_id']=='legacy-APPL-RESULT/1'],matcher_hash))
    write(output/'summary.json',summary)
    # A stable content manifest binds every proof, input, executable and log.
    manifest={p.relative_to(output).as_posix():digest(p.read_bytes()) for p in sorted(output.rglob('*')) if p.is_file()}
    write(output/'manifest.json',sealed(dict(head=head,files=manifest)))
    return summary


def main():
    parser=argparse.ArgumentParser();parser.add_argument('job',choices=PROGRAMS);parser.add_argument('output',type=Path)
    parser.add_argument('--triage-only',action='store_true');parser.add_argument('--no-search',action='store_true')
    args=parser.parse_args();head=os.environ['EQUIVALENCE_HEAD'];require_ci()
    if args.triage_only:
        data=triage(ROOT,args.job,head);write(args.output/'triage.json',data)
        (args.output/'triage.md').write_text(markdown_triage([data]));print(json.dumps(data['baseline_counts']))
    else: print(json.dumps(execute_pipeline(args.job,args.output,head,not args.no_search),indent=2))

if __name__=='__main__':main()
