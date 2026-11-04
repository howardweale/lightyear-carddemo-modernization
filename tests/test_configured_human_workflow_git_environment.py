"""CI-only original workflow Git reads; public markers and audit observations.
No fake Git/API/context, signed proof, credentials or admission is constructed.
"""
import json,os,subprocess,sys,unittest

@unittest.skipUnless(os.environ.get('GITHUB_ACTIONS')=='true','CI-only workflow Git checks')
class ConfiguredWorkflowGitEnvironment(unittest.TestCase):
    def probe(self,kind):
        code=r"""
import hashlib,json,os,subprocess,sys,tempfile
from pathlib import Path
from lightyear_execution.tower_drill_context import _workflow_source
from lightyear_execution.contracts import ExecutionContractError
kind=sys.argv[1]
for name in list(os.environ):
    if name.startswith('GIT_'):del os.environ[name]
def git(root,*args):
    return subprocess.check_output(['git','-c','core.autocrlf=false','-c','commit.gpgSign=false','-C',str(root),*args],stderr=subprocess.PIPE)
with tempfile.TemporaryDirectory() as directory:
    root=Path(directory);relative='.github/workflows/public-fixture.yml'
    git(root,'init','--object-format=sha1')
    git(root,'config','user.name','Public Fixture');git(root,'config','user.email','fixture@example.invalid')
    path=root/relative;path.parent.mkdir(parents=True)
    content=b'name: Public inert workflow\n'
    path.write_bytes(content);git(root,'add','--',relative);git(root,'commit','-m','Public workflow bytes')
    executable=git(root,'rev-parse','HEAD').decode().strip()
    if kind=='changed':path.write_bytes(b'name: Changed inert workflow\n')
    (root/'public-marker.txt').write_bytes(b'Public unrelated bytes\n')
    git(root,'add','--',relative,'public-marker.txt');git(root,'commit','-m','Second public revision')
    revision=git(root,'rev-parse','HEAD').decode().strip()
    if kind=='missing':revision='f'*40
    if kind=='identity':revision='not-a-revision'
    location='howardweale/lightyear-carddemo-modernization/'+relative
    # These mappings exercise byte comparison only; they are not verified proof.
    review={'drill_binding':{'ci':{'workflow_ref':location+'@'+executable}}}
    environment={'GITHUB_WORKFLOW_REF':location+'@refs/heads/main','GITHUB_WORKFLOW_SHA':revision}
    os.environ['OPENAI_API_KEY']='public-provider-marker'
    os.environ['FACTORY_TRANSPORT_KEY']='public-transport-marker'
    os.environ['WORKFLOW_GIT_PUBLIC_MARKER']='public-utility-marker'
    observed=[]
    def observe(event,args):
        if event!='subprocess.Popen':return
        program,argv,cwd,child_environment=args
        excluded=child_environment is not None and all(k.casefold() not in {'openai_api_key','factory_transport_key'} for k in child_environment)
        kept=child_environment is not None and child_environment.get('WORKFLOW_GIT_PUBLIC_MARKER')=='public-utility-marker'
        observed.append(dict(git=Path(program).name.lower() in ('git','git.exe'),excluded=excluded,kept=kept))
    sys.addaudithook(observe)
    refusal=None;matches=False;execution_authorized=None
    try:
        result=_workflow_source(root,review,environment)
        matches=(result['sha256']==hashlib.sha256(content).hexdigest() and result['path']==relative and result['signed_executable']==executable and result['workflow_sha']==revision)
        execution_authorized=result['execution_authorized']
    except ExecutionContractError as error:
        refusal=str(error)
    parent_unchanged=(os.environ['OPENAI_API_KEY']=='public-provider-marker' and os.environ['FACTORY_TRANSPORT_KEY']=='public-transport-marker')
    print(json.dumps(dict(refusal=refusal,matches=matches,execution_authorized=execution_authorized,observed=observed,parent_unchanged=parent_unchanged)))
"""
        result=subprocess.run([sys.executable,'-B','-c',code,kind],capture_output=True,text=True,timeout=60)
        self.assertEqual(result.returncode,0,'isolated workflow Git probe failed')
        row=json.loads(result.stdout)
        self.assertTrue(row['parent_unchanged'])
        self.assertEqual(len(row['observed']),0 if kind=='identity' else 2)
        self.assertTrue(all(x==dict(git=True,excluded=True,kept=True) for x in row['observed']))
        return row

    def test_same_workflow_at_distinct_commits_uses_filtered_git(self):
        row=self.probe('same')
        self.assertIsNone(row['refusal']);self.assertTrue(row['matches'])
        self.assertIs(row['execution_authorized'],False)

    def test_changed_workflow_still_refused(self):
        row=self.probe('changed')
        self.assertEqual(row['refusal'],'human-drill-workflow-source-changed')
        self.assertFalse(row['matches'])

    def test_missing_running_blob_still_refused(self):
        row=self.probe('missing')
        self.assertEqual(row['refusal'],'human-drill-workflow-source-unavailable')
        self.assertFalse(row['matches'])

    def test_invalid_identity_refused_before_git(self):
        row=self.probe('identity')
        self.assertEqual(row['refusal'],'human-drill-workflow-source-identity')
        self.assertFalse(row['matches'])
