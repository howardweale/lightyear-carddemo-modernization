"""One engineering attempt per invocation, only with Howard's pinned approval.

No freeze, Tower request, signing-key generation, automatic retry or business judge.
The newly approved bound asset root is read-only. Outputs use a distinct root.
"""
import argparse
from copy import deepcopy
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from lightyear_calibration.contracts import read_json, seal, canonical, verify
from tools.ms94_b06_engineering import (LABEL, IMAGE, LIMITS, Ledger, EngineeringSigner,
    approve_check, guard, require, write_new, seal_artifacts, refusal_context, append_log, sha, now)

IMAGES = (IMAGE, 'sha256:f3bed005214fbaec7f580a2d27e0dffa7a868bfc913db8c231d6f2b3fe4e0300',
          'sha256:96c4bda58cd8a8dfda586b2d83a2eb2a3e9f28fda0f1915d3fd758c890dc02b7')


def source_commit(root):
    def git(*args): return subprocess.check_output(['git','-C',str(root),*args],text=True).strip()
    require(not git('diff','HEAD','--name-only','--','.',':(exclude)docs/b06-engineering-runs.md'), 'source-dirty')
    # Ignore untracked run artifacts but never import untracked Python modules.
    require(not git('ls-files','--others','--exclude-standard','src','tools'), 'untracked-source')
    return git('rev-parse','HEAD')


def template(assets, source, approval):
    from tools.ms94_b06_admission import bound_file
    assets, source = Path(assets).resolve(), Path(source).resolve()
    require(source.is_relative_to(assets), 'template-path')
    value=read_json(source); verify(value)
    from tools.ms94_b06_engineering import validate_instrumented
    validate_instrumented(approval)
    require(value['content_sha256']==approval['native_template_sha256'] and value['journey']=='J1' and
            value['control']=='retained-reference' and value['built_runtime']['image']==IMAGE, 'instrumented-template')
    require(value['posting_observer']['class_files_sha256']==approval['observer_class_files_sha256'],
            'compiled-observer-changed')
    source_path=assets/'factory/idempiere/b06-observer/PostingObserver.java'
    require(sha(source_path)==approval['observer_source_sha256'], 'observer-source-changed')
    for name,digest in value['implementation_sha256'].items(): bound_file(assets,name,digest)
    for name,digest in value['posting_observer']['class_files_sha256'].items():
        bound_file(assets/value['posting_observer']['classes_directory'],name,digest)
    return value


def prepare_run(assets, source, run, approval):
    from tools.ms94_b06_admission import bound_file
    base=template(assets,source,approval); plan=deepcopy(base); plan.pop('content_sha256')
    plan.update(LABEL); plan.update(artifact_type='b06-engineering-oracle-plan/1',
        qualification_only=False, qualification_credit=False, measurement_credit=False,
        engineering_approval_sha256=approval['content_sha256'], engineering_template_sha256=approval['native_template_sha256'])
    plan['docker_run_window'] = dict(not_before_utc=approval['not_before_utc'], deadline_utc=approval['deadline_utc'], run_class='engineering')
    plan['candidate_timeout_seconds']=LIMITS['candidate_seconds']
    from tools.ms94_b06_observer_diagnostics import configuration
    from tools.ms94_b06_engineering import validate_run_binding
    mode=validate_run_binding(run,approval)['mode']
    plan['posting_observer'].pop('unmatched_return', None)
    plan['posting_observer']['native_diagnostics']=configuration(mode)
    plan['engineering_key_sha256']=approval['engineering_key_sha256']
    plan['engineering_limits']=dict(LIMITS)
    # No reference to any old native output is copied.
    for name,digest in base['inputs_sha256'].items():
        require(Path(name).name==name,'input-name')
        src=bound_file(Path(source).parent/'inputs',name,digest)
        target=Path(run)/'inputs'/name; target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(src,target)
    prepared=seal(plan)
    validate_run_binding(run,approval,prepared)
    write_new(Path(run)/'plan.json',prepared)


def main():
    from tools.ms94_b06_engineering import require_execution_ready
    require_execution_ready()
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('approval','approved-sha256','assets','template','output','authority'):
        p.add_argument('--'+name,required=True)
    args=p.parse_args(); repo=Path(__file__).resolve().parents[1]
    approval=read_json(Path(args.approval)); approve_check(approval,args.approved_sha256,args.approval)
    guard(approval,starting=True)
    output=Path(args.output).resolve()
    require(not any(x in output.parts for x in ('factory','b06-execution-snapshots')), 'output-in-evidence-tree')
    commit=source_commit(repo)
    assets=Path(args.assets).resolve()
    require(not output.is_relative_to(assets) and not assets.is_relative_to(output), 'output-assets-overlap')
    require(commit==approval.get('implementation_commit'),'implementation-commit-changed')
    template(assets,args.template,approval)
    from tools.ms94_b06_engineering_native import no_overlap, absence, OracleEngineeringRunner
    from lightyear_calibration.journey_runtime import inspect
    from lightyear_calibration.measured_native import cleanup_owned
    from tools.ms94_b06_engineering_key import DedicatedEngineeringSigner
    from tools.ms94_b05_supervisor import wait_process, terminate
    require(shutil.disk_usage(output.parent).free>=LIMITS['minimum_free_bytes'], 'free-space')
    ledger=Ledger(output,approval)
    with ledger.lock():
        # All Docker calls are downstream of exact standing approval/calendar.
        signer=EngineeringSigner(DedicatedEngineeringSigner(args.authority, approval['engineering_key_sha256']))
        no_overlap()
        for image in IMAGES: require(inspect('image',image)['Id']==image, 'pinned-image-missing')
        started=time.monotonic()
        run=ledger.reserve(commit); prepare_run(assets,args.template,run,approval)
        write_new(run/'approval.json',approval)
        command=[sys.executable,'-B','-m','tools.ms94_b06_engineering_worker',
            '--assets',str(assets),'--run',str(run),'--authority',args.authority,
            '--approval',args.approval,'--approved-sha256',args.approved_sha256]
        environment={**os.environ,'PYTHONPATH':os.pathsep.join((str(repo/'src'),str(repo))),
                     'PYTHONUTF8':'1','PYTHONDONTWRITEBYTECODE':'1'}
        opts={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {'start_new_session':True}
        terminal=None
        try:
            guard(approval,starting=True)
            require(time.monotonic()-started < LIMITS['run_seconds'], 'preparation-deadline')
            with (run/'controller.stdout').open('xb') as out, (run/'controller.stderr').open('xb') as err:
                child=subprocess.Popen(command,cwd=repo,env=environment,stdout=out,stderr=err,**opts)
                try: wait_process(child,started+LIMITS['run_seconds'],on_tick=lambda:guard(approval))
                finally: terminate(child)
            terminal=read_json(run/'worker-result.json')
            from lightyear_control_tower.decisions import verify_envelope
            require(verify_envelope(terminal,signer.public) and terminal['owner']==run.name and
                    terminal['plan_sha256']==read_json(run/'plan.json')['content_sha256'], 'worker-result-binding')
            terminal={k:v for k,v in terminal.items() if k not in ('signature','content_sha256')}
        except Exception as exc:
            # The failed attempt stays consumed. Cleanup is not a retry.
            runner=OracleEngineeringRunner(assets,run,read_json(run/'plan.json'),lambda *_:None,approval)
            cleaned=cleanup_owned(runner)
            terminal=dict(outcome='supervisor-failure',error=dict(exception_type=type(exc).__name__),
                          cleanup_verified=bool(cleaned['complete']) and absence(run.name))
            write_new(run/'supervisor-cleanup.json',signer.sign(dict(**LABEL,**cleaned)))
        context=refusal_context(run)
        write_new(run/'refusal-context.json',signer.sign(dict(**LABEL,context=context)))
        terminal={**terminal,**LABEL,'elapsed_seconds':round(time.monotonic()-started,3),
                  'finished_utc':now().isoformat(),'source_commit':commit,'image':IMAGE,'model_calls':0}
        require(terminal['elapsed_seconds']<=LIMITS['run_seconds']+LIMITS['cleanup_seconds'], 'cleanup-deadline')
        require(source_commit(repo)==commit, 'source-changed-during-run')
        write_new(run/'terminal.json',signer.sign(terminal))
        seal_artifacts(run,signer)
        require(time.monotonic()-started <= LIMITS['run_seconds']+LIMITS['cleanup_seconds'], 'finalization-deadline')
        append_log(repo/'docs/b06-engineering-runs.md',read_json(run/'engineering.json'),terminal,context)
        print(str(run))
        number=read_json(run/'engineering.json')['run_number']
        if context: print('Observer refusal captured; report full local context before another attempt.')
        if number==3: print('Three engineering attempts complete; report status to Howard now.')
        if number==approval['run_cap']: print('Standing run cap exhausted; stop. Howard must choose the next step.')


if __name__=='__main__': main()
