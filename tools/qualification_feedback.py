"""Development v3 structural projection; no gate prose or business values exported."""
from pathlib import Path
from lightyear_calibration.contracts import read_json,verify
from lightyear_calibration.qualified_diagnostics import compiler
from lightyear_calibration.qualified_contract import trace_diagnostics
from lightyear_calibration.measured_diagnostics import diagnostics as old_diagnostics

VERSION='qualified-structural-feedback-v3-development'


def export(run, declaration, *, root, api):
    run=Path(run);root=Path(root);out=[]
    for lane in ('oracle','postgresql'):
        where=run/'cases/operations/1/execution'/lane
        log=where/'maven.log'
        if log.exists():out.extend(compiler(log.read_text(encoding='utf-8',errors='replace'),root=root,api=api))
        # A trace interrupted by a compiler/runtime failure is not evidence that
        # the completed implementation omitted every downstream field.
        execution=where/'execution.json'
        if execution.exists():
            value=read_json(execution);verify(value)
            if value['exit_code']==0:out.extend(trace_diagnostics(where/'journey.xml',declaration))
    candidate=run/'inputs/operations.java'
    if candidate.exists():
        # Preserve source-verified Boolean representation diagnostics. Do not
        # inherit the legacy unqualified purchasing footprint or compiler parser.
        for value in old_diagnostics(run,candidate.read_text(encoding='utf-8'),api):
            if value['category']=='api-type-mismatch':
                out.append({k:v for k,v in value.items() if k!='id'})
    unique=[]
    for value in out:
        if value not in unique:unique.append(value)
    return [{'id':'structural-'+str(i+1),**value} for i,value in enumerate(unique)]


def replay(root, output):
    import collections
    from lightyear_calibration.qualified_contract import contract
    from lightyear_calibration.journey_order import save
    from lightyear_calibration.contracts import seal
    root=Path(root);api=read_json(root/'factory/idempiere/analyst-repair/api-provenance.json')
    attempts=[];counts=collections.Counter()
    for receipt_path in sorted((root/'work/ms92/cohort-proposal-four-conditions-01/trials').glob('*/receipt.json')):
        receipt=read_json(receipt_path)
        for attempt in receipt['attempts']:
            run=root/attempt['run_directory'];plan=read_json(run/'plan.json')
            values=export(run,contract(root,plan['scenario']),root=root,api=api)
            counts.update(v.get('code',v['category']) for v in values)
            attempts.append({'run_id':run.name,'diagnostics':values})
    value=seal({'artifact_type':'structural-diagnostic-development-replay','version':VERSION,
        'attempt_count':len(attempts),'attempts_with_feedback':sum(bool(a['diagnostics']) for a in attempts),
        'codes':dict(counts),'attempts':attempts,'old_campaign_changed':False,
        'repair_success_claimed':False,'model_calls':0,
        'limits':['Old purchasing footprint assertions are not exported as proven repair instructions.',
                  'Source-supported API type diagnostics do not prove the sole runtime failure cause.',
                  'Business failures can still require a halt under the no-business-answer feedback policy.']})
    save(Path(output),value);return value


if __name__=='__main__':
    import json
    value=replay(Path('.').resolve(),Path('work/ms93/diagnostic-replay-v3.json'))
    print(json.dumps({k:v for k,v in value.items() if k!='attempts'}))
