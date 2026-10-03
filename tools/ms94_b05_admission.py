"""B05 executable admission. Preflight permission never grants model permission."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
from lightyear_calibration.contracts import read_json, require, verify
from lightyear_calibration.journey_order import file_hash
from lightyear_control_tower.decisions import verify_envelope
from tools.ms94_b05_plan import check_plan, period_guard

APPROVED = Path('docs/calibration/idempiere-ms94/stage-b-05')
CONFIG = Path('factory/idempiere/ms94-b05-executable')
CAMPAIGN = Path('work/ms94/stage-b-05')
PREFLIGHT = Path('work/ms94/stage-b-05-preflight')
PLAN = '56b13b23a319af3d207552f5022fd3bbaeb9744dba2f79cf535acb2b5fd49951'
DECLARATION = '07bf81eb26edb82f9e74be3535af23e7ec51ae965f1581047bf82b87a6404cd2'

def signature(root, path):
    value=read_json(root/path)
    require(verify_envelope(value,(root/'work/ms87/operator/authority.public.pem').read_bytes()), 'Invalid signature: '+str(path))
    return value

def bindings(root, live=False):
    plan=check_plan(read_json(root/APPROVED/'plan.json'))
    require(plan['content_sha256']==PLAN, 'Approved B05 plan changed')
    declaration=signature(root,APPROVED/'declaration.json')
    require(declaration['content_sha256']==DECLARATION, 'Approved B05 declaration changed')
    q=plan['qualification_binding']
    snapshot=read_json(root/APPROVED/'qualification/execution-snapshot.json');verify(snapshot)
    require(snapshot['content_sha256']==q['snapshot_sha256'] and len(snapshot['files'])==q['frozen_files'], 'Qualification snapshot differs')
    for name,sha in snapshot['files'].items():
        require(file_hash(root/name)==sha, 'Qualified input changed: '+name)
    for name,sha in q['qualified_input_hashes'].items():
        require(file_hash(root/name)==sha, 'Qualified module changed: '+name)
    audit=signature(root,APPROVED/'qualification/terminal-verification.json')
    require(audit['content_sha256']==q['terminal_audit_sha256'], 'Qualification terminal audit differs')
    require(file_hash(root/APPROVED/'qualification/terminal-verification.json')==q['terminal_audit_file_sha256'], 'Audit bytes differ')
    prompt=read_json(root/APPROVED/'builder-prompt.json')
    from lightyear_calibration.contracts import canonical
    require(hashlib.sha256(canonical(prompt)).hexdigest()==plan['slots'][0].get('initial_prompt_sha256', read_json(root/APPROVED/'trials/pilot-01/plan.json')['initial_prompt_sha256']), 'Prompt bytes differ')
    executable=read_json(root/'execution-snapshot.json');verify(executable)
    for name,sha in executable['files'].items():require(file_hash(root/name)==sha, 'Executable input changed: '+name)
    if live:
        from tools.ms94_execution_snapshot import guard
        guard(root);period_guard(datetime.now(timezone.utc))
    return plan,executable

def preflight_authorization(root):
    plan,snapshot=bindings(root,True)
    auth=signature(root,PREFLIGHT/'authorization.json')
    require(auth['scope']=='b05-zero-model-preflight' and auth['model_calls_authorized'] is False
            and auth['snapshot_sha256']==snapshot['content_sha256'] and auth['approved_plan_sha256']==PLAN
            and auth['approved_declaration_sha256']==DECLARATION and auth['maximum_native_pairs']==2,
            'Preflight authorization differs')
    return auth

def validate_model_authorization(auth, snapshot_sha, preflight_sha, publication_sha):
    require(auth.get('scope')=='b05-model-measurement-launch' and auth.get('model_calls_authorized') is True,
            'Separate explicit B05 model launch approval is required; preflight is not model authorization')
    require(auth.get('snapshot_sha256')==snapshot_sha and auth.get('preflight_report_sha256')==preflight_sha
            and auth.get('publication_receipt_sha256')==publication_sha and auth.get('approved_plan_sha256')==PLAN
            and auth.get('approved_declaration_sha256')==DECLARATION, 'Launch approval bindings differ')
    require(auth.get('operator_approval') and '<hash>' not in auth['operator_approval'], 'Unfilled approval template is not authorization')
    require(auth.get('limits')=={'calls':115,'compilations':69,'seconds':93600}, 'Launch limits changed')

def model_authorization(root, launching=False):
    _,snapshot=bindings(root,True)
    auth=signature(root,CAMPAIGN/'authorization.json')
    report=signature(root,PREFLIGHT/'report.json')
    published=signature(root,CAMPAIGN/'published-executable.json')
    require(report['passed'] and report['model_calls']==0 and report['snapshot_sha256']==snapshot['content_sha256'], 'Preflight did not pass')
    require(published['snapshot_sha256']==snapshot['content_sha256'] and published['preflight_report_sha256']==report['content_sha256']
            and published['all_public_bytes_verified'] is True, 'Executable is not publicly frozen')
    validate_model_authorization(auth,snapshot['content_sha256'],report['content_sha256'],published['content_sha256'])
    period_guard(datetime.now(timezone.utc),launching=launching)
    return auth

def trial(root,campaign,live=False):
    approved,snapshot=bindings(root,live)
    plan=read_json(campaign/'plan.json');verify(plan)
    fixture=campaign==root/PREFLIGHT
    name='preflight' if fixture else campaign.name
    require(read_json(root/CONFIG/(name+'.json'))==plan, 'Executable trial plan differs')
    if not fixture:
        require(any(Path(s['path']).name==name and s['plan_sha256']==plan['preregistered_trial_sha256'] for s in approved['slots']), 'Unregistered slot')
    if live:
        from tools.ms94_b05_controller import tool_runtime
        require(plan['tool_runtime']==tool_runtime(), 'Tool runtime changed')
        preflight_authorization(root) if fixture else model_authorization(root)
    plan=dict(plan)
    plan['implementation_sha256']={**snapshot['files'],'execution-snapshot.json':file_hash(root/'execution-snapshot.json')}
    return plan

def actual_cleanup(run):
    """Check only the exact resource names recorded by this native runner."""
    import subprocess
    resources=read_json(run/'resources.json')['resources']
    commands={'container':['container','ls','-a','--format','{{.Names}}'],
              'network':['network','ls','--format','{{.Name}}'], 'volume':['volume','ls','--format','{{.Name}}']}
    inventories={k:set(subprocess.run(['docker',*v],check=True,capture_output=True,text=True).stdout.splitlines()) for k,v in commands.items()}
    require(resources, 'No owned resource inventory')
    for r in resources:require(r['name'] not in inventories[r['kind']], 'Owned resource remains: '+r['name'])
    return [{'kind':r['kind'],'name':r['name'],'absent':True} for r in resources]
