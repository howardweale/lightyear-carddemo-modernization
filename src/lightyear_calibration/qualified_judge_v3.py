"""Versioned, total result envelope around the complete independent native judge.

MS92 remains unchanged. Details are PRIVATE; builders only receive the separate
closed diagnostic projection. A thrown judge exception never means a pass.
"""
from datetime import datetime, timezone
from pathlib import Path
import traceback
from .contracts import CalibrationError, read_json, seal, verify
from .journey_order import RUNS, save, file_hash
from .qualified_contract import structural_result

VERSION = 'idempiere-qualified-judge-v3'
STATUSES = frozenset(('passed','business-failure','execution-failure','judge-error','insufficient-evidence'))


def result(status, *, plan_hash=None, checks=None, error=None, qualification=True):
    if status not in STATUSES: raise ValueError('Unknown result status')
    return seal({'artifact_type':'lightyear-structured-native-judgment',
        'judge_version':VERSION,'status':status,'passed':status=='passed',
        'plan_sha256':plan_hash,'checks':checks or {},'error':error,
        'qualification_only':qualification,'autonomous_success':False,
        'platform_qualification':False,'builder_visible':False})


def evaluate(run, *, verifier=None):
    """Always persist gate.json, including parser, integrity and implementation errors."""
    run=Path(run).resolve(); checks={}; plan_hash=None; stage='plan'; status='judge-error';error=None
    try:
        plan=read_json(run/'plan.json');verify(plan);plan_hash=plan['content_sha256']
        root=run.parents[len(RUNS.parts)]
        stage='execution'
        executions={}
        for lane in ('oracle','postgresql'):
            p=run/'cases/operations/1/execution'/lane/'execution.json'
            if p.exists():
                value=read_json(p);verify(value);executions[lane]=value['exit_code']
        checks['execution_exit_codes']=executions
        if any(code != 0 for code in executions.values()):
            status='execution-failure'
        elif set(executions) != {'oracle','postgresql'}:
            status='insufficient-evidence'
        else:
            stage='public-structure'
            structure=structural_result(run,root,plan['scenario']);checks['structure']=structure
            if not structure['passed']:
                status='insufficient-evidence'
            else:
                stage='combined-native-judge'
                if verifier is None:
                    from .qualification_combined_v2 import verify_run
                    verifier=verify_run
                native=verifier(run);verify(native);checks['combined']=native
                # Missing native witnesses is evidence insufficiency, not proof of a business defect.
                observers=native.get('database_observers',{})
                status=('passed' if native['passed'] else 'insufficient-evidence'
                        if any(not x['passed'] for x in observers.values()) else 'business-failure')
    except FileNotFoundError as exc:
        status='insufficient-evidence';error={'stage':stage,'type':type(exc).__name__,'message':str(exc)}
    except CalibrationError as exc:
        message=str(exc)
        # Only established business/shape checks become business failures. All other
        # assertions (including identity and capture validation) remain judge errors.
        business=('Missing or ambiguous committed application record:',
                  'Write outside declared procurement footprint',
                  'Write outside declared journey footprint',
                  'Quantity outcome differs','Monetary outcomes differ',
                  'Missing accounting entries','Unbalanced accounting entries',
                  'Journey document links differ','Payment allocation amount differs',
                  'Rollback','Recovery','Rolled-back','Credit','Procurement quantities differ',
                  'Vendor document link differs','Payment must be outbound',
                  'Document is not completed','Closing inventory differs',
                  'Trace differs from committed business value:')
        status='business-failure' if stage=='combined-native-judge' and message.startswith(business) else 'judge-error'
        error={'stage':stage,'type':type(exc).__name__,'message':message}
    except Exception as exc:
        error={'stage':stage,'type':type(exc).__name__,'message':str(exc)};status='judge-error'
    value=result(status,plan_hash=plan_hash,checks=checks,error=error)
    save(run/'gate.json',value)
    return value


if __name__=='__main__':
    import argparse,json
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);a=p.parse_args()
    print(json.dumps(evaluate(a.run),indent=2))
