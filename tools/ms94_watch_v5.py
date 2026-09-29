"""Owned-resource cleanup after unexpected controller exit; host-only signing."""
import sys,time
from pathlib import Path
from lightyear_calibration.contracts import read_json,require,verify
from lightyear_calibration.journey_runtime import LocalRunner,process_alive
from lightyear_calibration.measured_native import cleanup_owned
from lightyear_calibration.journey_order import save
from lightyear_control_tower.decisions import verify_envelope
from tools.ms94_signer_v5 import JourneySigner


def watch(root,run,pid):
    root,run=Path(root).resolve(),Path(run).resolve()
    require(run.is_relative_to(root/'factory/idempiere/ms86-journeys/runs'),'Watchdog run escaped root')
    plan=read_json(run/'plan.json');verify(plan);signer=JourneySigner(root)
    auth=read_json(run/'authorization.json')
    require(verify_envelope(auth,signer.public) and auth['run_id']==run.name
            and auth['plan']['plan_sha256']==plan['content_sha256'],'Untrusted watchdog authorization')
    while not (run/'receipt.json').exists() and process_alive(pid):time.sleep(5)
    if (run/'receipt.json').exists():return
    runner=LocalRunner(root,run,plan,lambda *_:None)
    try:
        cleaned=cleanup_owned(runner)
    except Exception as exc:
        cleaned={'complete':False,'error_type':type(exc).__name__}
    save(run/'watchdog-cleanup.json',signer.sign({'run_id':run.name,'plan_sha256':plan['content_sha256'],
        'controller_exited_without_receipt':True,'new_model_calls':0,**cleaned}))


if __name__=='__main__':watch(Path(sys.argv[1]),Path(sys.argv[2]),int(sys.argv[3]))
