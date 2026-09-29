"""Replayable controller failures plus the typed native judge; no message dispatch."""
from pathlib import Path
from lightyear_calibration.contracts import read_json,require,verify
from lightyear_calibration.ms94_v4_judge import evaluate as judge,result,VERSION
from lightyear_calibration.journey_order import save
from lightyear_control_tower.decisions import verify_envelope


def evaluate(run,**unused):
    run=Path(run)
    if not (run/'controller-outcome.json').exists():return judge(run)
    # The private controller publishes this only after application containers
    # stop. It is signed and bound to the plan and cleanup record.
    try:
        plan=read_json(run/'plan.json');verify(plan)
        value=read_json(run/'controller-outcome.json');cleanup=read_json(run/'cleanup.json')
        key=(run/'authority.public.pem').read_bytes()
        require(verify_envelope(value,key) and verify_envelope(cleanup,key),'Controller outcome signature differs')
        require(value['plan_sha256']==plan['content_sha256'] and value['cleanup_sha256']==cleanup['content_sha256']
                and value['run_id']==cleanup['run_id']==run.name,'Controller outcome binding differs')
        require(value['status']=='execution-failure' and (value['error'] or not cleanup['complete']),
                'Controller failure has no recorded cause')
        gate=result('execution-failure',plan_hash=plan['content_sha256'],error=value['error'],
                    checks={'controller_outcome_sha256':value['content_sha256'],'cleanup_sha256':cleanup['content_sha256']})
    except Exception as error:
        gate=result('judge-error',error={'type':type(error).__name__,'message':str(error),'stage':'controller-outcome'})
    save(run/'gate.json',gate);return gate
