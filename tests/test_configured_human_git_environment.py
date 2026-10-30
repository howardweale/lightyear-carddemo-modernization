"""CI-only actual Git reads with observational Python subprocess audit events.

Public markers only. No fake Git, API, context, signer, proof or passed admission.
The admission object is used only for committed-byte reads; no plan is verified.
"""
import json,os,subprocess,sys,unittest

@unittest.skipUnless(os.environ.get('GITHUB_ACTIONS')=='true','CI-only Git environment checks')
class ConfiguredGitEnvironment(unittest.TestCase):
    def probe(self,kind,changed=False):
        code=r"""
import hashlib,json,os,subprocess,sys,tempfile
from pathlib import Path
from lightyear_factory.model_admission import FactoryModelAdmission
from lightyear_factory.contracts import ContractError
from lightyear_factory.authorship import CandidateHistory
from lightyear_factory.workspace import IsolatedWorkspace
from lightyear_factory.ledger import RunLedger
from lightyear_execution.configured_receipt_materials import _committed_public_bytes,KEY_ID
from lightyear_execution.contracts import ExecutionContractError
kind=sys.argv[1];changed=sys.argv[2]=='yes'
for name in list(os.environ):
    if name.startswith('GIT_'):del os.environ[name]
def git(root,*args):
    return subprocess.check_output(['git','-c','core.autocrlf=false','-c','commit.gpgSign=false','-C',str(root),*args],stderr=subprocess.PIPE)
with tempfile.TemporaryDirectory() as directory:
    base=Path(directory);root=base/'source';root.mkdir()
    git(root,'init','--object-format=sha1')
    git(root,'config','user.name','Public Fixture');git(root,'config','user.email','fixture@example.invalid')
    relative='public.json' if kind=='json' else KEY_ID
    content=b'{"fixture":1}\n' if kind=='json' else b'public-fixture-id\n'
    path=root/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(content)
    git(root,'add','--',relative);git(root,'commit','-m','Public inert bytes')
    # No signature, proof, trust or native admission is asserted by these bytes.
    admission=FactoryModelAdmission(root,'unused-plan','unused-proof','unused-contract',public_key=b'inert-public-marker',trusted_head=lambda:'')
    if kind=='history':
        bare=base/'history.git';git(base,'init','--bare','--object-format=sha1',str(bare))
        workspace=IsolatedWorkspace(root,base/'workspace',(),read_manifest={})
        history=CandidateHistory(workspace,bare,'public-fixture',RunLedger(base/'events.jsonl'))
    if changed:path.write_bytes(b'{"fixture":2}\n' if kind=='json' else b'public-fixture-xx\n')
    os.environ['OPENAI_API_KEY']='public-provider-marker'
    os.environ['FACTORY_TRANSPORT_KEY']='public-transport-marker'
    observed=[]
    def observe(event,args):
        if event!='subprocess.Popen':return
        executable,argv,cwd,environment=args
        # Observation only: never modify arguments, deny a call or emit values.
        excluded=environment is not None and all(k.casefold() not in {'openai_api_key','factory_transport_key'} for k in environment)
        fixed_history=kind!='history' or (environment.get('GIT_CONFIG_NOSYSTEM')=='1' and environment.get('GIT_CONFIG_COUNT')=='0' and environment.get('GIT_TERMINAL_PROMPT')=='0' and environment.get('GIT_CONFIG_GLOBAL')==os.devnull)
        observed.append(dict(git=Path(executable).name.lower() in ('git','git.exe'),excluded=excluded,history_guards=fixed_history))
    sys.addaudithook(observe)
    refused=False;matches=False
    try:
        if kind=='json':matches=admission._committed_json(relative)==dict(fixture=1)
        elif kind=='public':matches=_committed_public_bytes(admission,KEY_ID)==content
        else:matches=history._git('rev-parse','--is-bare-repository',work_tree=False).strip()==b'true'
    except (ContractError,ExecutionContractError):refused=True
    parent_unchanged=os.environ['OPENAI_API_KEY']=='public-provider-marker' and os.environ['FACTORY_TRANSPORT_KEY']=='public-transport-marker'
    print(json.dumps(dict(refused=refused,matches=matches,observed=observed,parent_unchanged=parent_unchanged)))
"""
        result=subprocess.run([sys.executable,'-B','-c',code,kind,'yes' if changed else 'no'],capture_output=True,text=True,timeout=60)
        self.assertEqual(result.returncode,0,'isolated Git probe failed')
        row=json.loads(result.stdout)
        self.assertTrue(row['parent_unchanged']);self.assertTrue(row['observed'])
        self.assertTrue(all(x==dict(git=True,excluded=True,history_guards=True) for x in row['observed']))
        self.assertEqual(row['refused'],changed);self.assertEqual(row['matches'],not changed)
        return row
    def test_native_committed_json_read(self):
        self.assertEqual(len(self.probe('json')['observed']),3)
    def test_native_committed_json_still_refuses_changed_bytes(self):
        self.assertEqual(len(self.probe('json',True)['observed']),3)
    def test_native_public_material_read(self):
        self.assertEqual(len(self.probe('public')['observed']),3)
    def test_native_public_material_still_refuses_changed_bytes(self):
        self.assertEqual(len(self.probe('public',True)['observed']),3)
    def test_original_history_git_keeps_existing_environment_guards(self):
        self.assertEqual(len(self.probe('history')['observed']),1)
