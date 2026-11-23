"""CI-only real OS environment probes using public marker strings.

These tests never invoke gh, an API, reservation, admission or a provider.
They qualify environment-copy behavior only, not authenticated API behavior.
"""
import json,os,subprocess,sys,unittest

@unittest.skipUnless(os.environ.get('GITHUB_ACTIONS')=='true','CI-only OS environment probes')
class GitHubSubprocessEnvironment(unittest.TestCase):
    def probe(self,body):
        setup="""
import json,os,subprocess,sys
from lightyear_execution.tower_drill_reservation import _github_subprocess_environment
os.environ['OPENAI_API_KEY']='public-provider-marker'
os.environ['FACTORY_TRANSPORT_KEY']='public-transport-marker'
os.environ['GH_TOKEN']='public-service-marker'
"""
        result=subprocess.run([sys.executable,'-B','-c',setup+'\n'+body],capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,'isolated environment probe failed')
        return json.loads(result.stdout)
    def test_real_child_excludes_two_names_and_retains_service_and_path(self):
        row=self.probe("""
environment=_github_subprocess_environment()
code="import json,os;print(json.dumps(dict(excluded=all(k.casefold() not in {'openai_api_key','factory_transport_key'} for k in os.environ),service=os.environ.get('GH_TOKEN')=='public-service-marker')))"
child=subprocess.run([sys.executable,'-B','-c',code],env=environment,capture_output=True,text=True,timeout=10)
assert child.returncode==0
row=json.loads(child.stdout)
row['path_preserved']=environment.get('PATH')==os.environ.get('PATH')
row['parent_unchanged']=os.environ['OPENAI_API_KEY']=='public-provider-marker' and os.environ['FACTORY_TRANSPORT_KEY']=='public-transport-marker'
print(json.dumps(row))
""")
        self.assertEqual(row,dict(excluded=True,service=True,path_preserved=True,parent_unchanged=True))
    def test_absent_names_need_no_placeholder_or_fallback(self):
        row=self.probe("""
for name in list(os.environ):
    if name.casefold() in {'openai_api_key','factory_transport_key'}:del os.environ[name]
environment=_github_subprocess_environment()
print(json.dumps(dict(excluded=all(k.casefold() not in {'openai_api_key','factory_transport_key'} for k in environment),service=environment['GH_TOKEN']=='public-service-marker')))
""")
        self.assertEqual(row,dict(excluded=True,service=True))
    def test_case_variant_names_are_also_excluded(self):
        row=self.probe("""
os.environ['OpenAI_Api_Key']='public-case-marker'
os.environ['Factory_Transport_Key']='public-case-marker'
environment=_github_subprocess_environment()
print(json.dumps(dict(excluded=all(k.casefold() not in {'openai_api_key','factory_transport_key'} for k in environment))))
""")
        self.assertEqual(row,dict(excluded=True))
    def test_snapshot_is_detached_and_next_call_uses_current_environment(self):
        row=self.probe("""
os.environ['PUBLIC_ENVIRONMENT_PROBE']='first'
first=_github_subprocess_environment()
os.environ['PUBLIC_ENVIRONMENT_PROBE']='second'
os.environ['GH_TOKEN']='public-service-marker-second'
second=_github_subprocess_environment()
first['PUBLIC_ENVIRONMENT_PROBE']='copy-only'
print(json.dumps(dict(current=second['PUBLIC_ENVIRONMENT_PROBE']=='second',service_current=second['GH_TOKEN']=='public-service-marker-second',service_original=first['GH_TOKEN']=='public-service-marker',parent_unchanged=os.environ['PUBLIC_ENVIRONMENT_PROBE']=='second',excluded='OPENAI_API_KEY' not in second and 'FACTORY_TRANSPORT_KEY' not in second)))
""")
        self.assertEqual(row,dict(current=True,service_current=True,service_original=True,parent_unchanged=True,excluded=True))
