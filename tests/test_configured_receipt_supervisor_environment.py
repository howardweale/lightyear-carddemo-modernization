"""CI-only OS environment boundaries with public dummy strings, never keys.

Every probe runs in a separate real Python process. No fake Popen/API/context,
native admission, provider request, lease, credential or secure-erasure claim.
"""
import json,os,subprocess,sys,unittest

@unittest.skipUnless(os.environ.get('GITHUB_ACTIONS')=='true','CI-only OS environment checks')
class SupervisorParentEnvironment(unittest.TestCase):
    def probe(self,body):
        setup="""
import os,sys,json,tempfile,io,contextlib,threading,time
from pathlib import Path
from tools.ci.p5_configured_receipt_supervisor import _launch_and_wait,_discard_parent_provider_environment,main
os.environ['OPENAI_API_KEY']='public-provider-marker-not-a-key'
os.environ['FACTORY_TRANSPORT_KEY']='public-transport-marker-not-a-key'
os.environ['GH_TOKEN']='public-service-marker-not-a-token'
def absent():return all(k not in os.environ for k in ('OPENAI_API_KEY','FACTORY_TRANSPORT_KEY'))
"""
        result=subprocess.run([sys.executable,'-B','-c',setup+'\n'+body],capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,'isolated environment probe failed')
        return json.loads(result.stdout)
    def test_only_parent_provider_and_transport_names_are_removed(self):
        row=self.probe("_discard_parent_provider_environment();print(json.dumps(dict(absent=absent(),service=os.environ.get('GH_TOKEN')=='public-service-marker-not-a-token')))")
        self.assertEqual(row,dict(absent=True,service=True))
    def test_absent_parent_names_are_idempotent(self):
        row=self.probe("_discard_parent_provider_environment();_discard_parent_provider_environment();print(json.dumps(dict(absent=absent())))")
        self.assertEqual(row,dict(absent=True))
    def test_original_child_receives_markers_parent_drops_names(self):
        row=self.probe("""
with tempfile.TemporaryDirectory() as directory:
    code="import os,sys;sys.exit(0 if os.environ.get('OPENAI_API_KEY')=='public-provider-marker-not-a-key' and os.environ.get('FACTORY_TRANSPORT_KEY')=='public-transport-marker-not-a-key' else 9)"
    path=Path(directory)/'observations.txt'
    with path.open('x',encoding='ascii') as stream:result=_launch_and_wait([sys.executable,'-B','-c',code],directory,stream)
    text=path.read_text()
    print(json.dumps(dict(result=result,absent=absent(),reaped=text.count('event=original-child-reaped '),leaked_marker='public-provider-marker' in text or 'public-transport-marker' in text)))
""")
        self.assertEqual(row,dict(result=0,absent=True,reaped=1,leaked_marker=False))
    def test_nonzero_and_abrupt_child_exits_keep_original_codes(self):
        for code in ("raise SystemExit(17)","import os;os._exit(23)"):
            with self.subTest(code=code):
                row=self.probe("""
with tempfile.TemporaryDirectory() as directory:
    with (Path(directory)/'observations.txt').open('x',encoding='ascii') as stream:
        result=_launch_and_wait([sys.executable,'-B','-c',%s],directory,stream)
    print(json.dumps(dict(result=result,absent=absent())))
"""%repr(code))
                self.assertEqual(row,dict(result=17 if '17' in code else 23,absent=True))
    def test_parent_names_absent_before_original_wait_finishes(self):
        row=self.probe(r"""
with tempfile.TemporaryDirectory() as directory:
    path=Path(directory)/'observations.txt';release=Path(directory)/'release'
    observed=[]
    def observer():
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            if path.exists() and 'event=child-created ' in path.read_text():
                observed.append(absent());release.write_bytes(b'public-release');return
            time.sleep(.01)
    thread=threading.Thread(target=observer);thread.start()
    code='import time,sys;from pathlib import Path;p=Path('+repr(str(release))+');deadline=time.monotonic()+10\nwhile not p.exists() and time.monotonic()<deadline:time.sleep(.01)\nsys.exit(0 if p.exists() else 9)'
    with path.open('x',encoding='ascii') as stream:result=_launch_and_wait([sys.executable,'-B','-c',code],directory,stream)
    thread.join(12)
    print(json.dumps(dict(result=result,observed=observed,joined=not thread.is_alive())))
""")
        self.assertEqual(row,dict(result=0,observed=[True],joined=True))
    def test_native_argument_refusal_discards_parent_names(self):
        row=self.probe("""
refused=False
with contextlib.redirect_stderr(io.StringIO()):
    try:main(['--unknown-supervisor-fixture-option'])
    except SystemExit as exc:refused=exc.code!=0
print(json.dumps(dict(refused=refused,absent=absent())))
""")
        self.assertEqual(row,dict(refused=True,absent=True))
