"""Materialize only the independent pre-sign CI clone and verify native M.

No remote publication, reservation, context, credential lease, or model call.
The caller is the disposable producer; its original journal is checked before
and after this native verification, independently of the exported proof.
"""
import os,subprocess
from pathlib import Path
from tools.ci.operator_flow_metadata import prepare_candidate,PREFIX,require

def verify_candidate(root,executable,metadata,commit_epoch,trust_path):
    require(os.environ.get('GITHUB_ACTIONS')=='true'
        and os.environ.get('GITHUB_JOB')=='operator-producer','candidate-producer-ci-only')
    root=Path(root);temporary=Path(os.environ['RUNNER_TEMP']).resolve(strict=True)
    require(root.is_absolute() and root.resolve(strict=True)==root
        and root.is_relative_to(temporary) and root!=temporary,'candidate-independent-temporary-checkout')
    source=Path(os.environ['GITHUB_WORKSPACE']).resolve(strict=True)
    require(root!=source and not root.is_relative_to(source),'candidate-source-must-stay-unchanged')
    candidate=prepare_candidate(root,executable,metadata,commit_epoch)
    def git(*args,data=None):
        completed=subprocess.run(['git','--no-optional-locks','-C',str(root),*args],input=data,capture_output=True,timeout=45)
        require(completed.returncode==0,'candidate-local-git-refused')
        return completed.stdout
    require(git('config','--get','core.autocrlf').decode().strip()=='false','candidate-prepared-byte-checkout')
    # Only this already prepared independent clone receives new objects. Every
    # object is independently verified; source E and sealed wrapper remain E.
    for oid,(kind,body) in candidate['objects'].items():
        require(git('hash-object','-w','-t',kind,'--stdin',data=body).decode().strip()==oid,
            'candidate-object-storage-mismatch')
    git('checkout','--detach',candidate['commit'])
    require(not git('status','--porcelain=v1','--untracked-files=all'),'candidate-clean-M')
    require(git('rev-list','--parents','-n','1',candidate['commit']).decode().split()==[candidate['commit'],executable],
        'candidate-sole-parent-E')
    require(set(git('diff','--name-only',executable,candidate['commit']).decode().splitlines())==set(metadata),
        'candidate-exact-metadata-diff')
    for path,raw in metadata.items():
        require((root/path).read_bytes()==git('show',candidate['commit']+':'+path)==raw,'candidate-original-metadata-bytes')
    from lightyear_factory.contracts import WorkOrder
    from lightyear_factory.model_admission import FactoryModelAdmission
    from lightyear_execution.contracts import ExecutionPolicy
    from lightyear_execution.tower_drill_admission import verify_human_drill_plan
    order=WorkOrder.load(root/'tests/fixtures/p5_public/human-clean-control/work-order.json')
    policy=ExecutionPolicy.load(root/(PREFIX+'execution-policy.json'))
    # Native paths are strict relative strings, never Path objects. The exact
    # external trust file/key came from the producer's independent journal read.
    admission=FactoryModelAdmission.from_external_trust(root,PREFIX+'plan.json',PREFIX+'proof.json',
        PREFIX+'contract.json',trust_path)
    review=verify_human_drill_plan(admission,order,policy)
    plan=admission._committed_json(PREFIX+'plan.json')
    runtime=admission.verify_runtime(order,source_root=root,
        input_paths={key:root/row['path'] for key,row in plan['bound_inputs'].items()},policy=policy)
    verified=review['verified_model_admission']
    require(verified['executable_commit']==candidate['commit'] and plan['executable_commit']==executable
        and runtime['executable_commit']==candidate['commit'],'candidate-native-E-M-binding')
    require(verify_human_drill_plan(admission,order,policy)==review,'candidate-native-trust-changed')
    require(not git('status','--porcelain=v1','--untracked-files=all'),'candidate-final-clean-M')
    return dict(parent=executable,base_tree=candidate['base_tree'],tree=candidate['tree'],commit=candidate['commit'],
        commit_epoch=commit_epoch,files=candidate['files'],native_candidate_verified=True,
        plan_sha256=verified['plan_sha256'],decision_sha256=verified['decision_sha256'],
        journal_head_sha256=verified['trusted_journal_head'],nonce_sha256=review['drill_binding']['nonce_sha256'],
        native_runtime_inputs_verified=True,full_guards_passed=False,publish_ready=False,
        publication_authorized=False,full_route_passed=False,real_pack_ready=False)
