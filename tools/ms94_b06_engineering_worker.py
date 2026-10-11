"""Bounded child for one already-approved engineering attempt."""
import argparse
from pathlib import Path
from lightyear_calibration.contracts import read_json
from tools.ms94_b06_engineering import approve_check, guard, EngineeringSigner, write_new, LABEL, require


def main():
    from tools.ms94_b06_engineering import require_execution_ready
    require_execution_ready()
    p=argparse.ArgumentParser()
    for name in ('assets','run','authority','approval','approved-sha256'): p.add_argument('--'+name,required=True)
    a=p.parse_args(); run=Path(a.run).resolve()
    approval=read_json(Path(a.approval)); approve_check(approval,a.approved_sha256,a.approval); guard(approval)
    from tools.ms94_b06_engineering_run import source_commit
    require(source_commit(Path(__file__).resolve().parents[1]) == approval['implementation_commit'],
            'worker-implementation-commit')
    from tools.ms94_b06_engineering import validate_run_binding
    record=validate_run_binding(run,approval,read_json(run/'plan.json'))
    require(record['approval_sha256']==approval['content_sha256'] and record['owner']==run.name and
            run.parent.parent.parent.name=='b06-engineering','worker-run-binding')
    require((run.parent.parent.parent/'active.lock').read_text()==approval['content_sha256'],'worker-lease')
    require(not (run/'worker-started.json').exists(),'worker-restart')
    guard(approval,starting=True,attempt_number=record['run_number'])
    from tools.ms94_b06_engineering_key import DedicatedEngineeringSigner
    from tools.ms94_b06_engineering_native import execute
    signer=EngineeringSigner(DedicatedEngineeringSigner(a.authority, approval['engineering_key_sha256']))
    write_new(run/'worker-started.json',signer.sign(dict(**LABEL,owner=run.name)))
    result=execute(Path(a.assets),run,approval,signer)
    write_new(run/'worker-result.json',signer.sign(dict(**LABEL,**result,owner=run.name,plan_sha256=read_json(run/'plan.json')['content_sha256'])))


if __name__=='__main__': main()
