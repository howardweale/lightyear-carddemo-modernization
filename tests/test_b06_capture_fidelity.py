import io,json,tempfile,unittest,zipfile
from pathlib import Path
from tools.b06_image_artifacts.bundle_content import bundle_content_view,EXCLUSIONS
from tools.b06_image_artifacts.runtime_capture import capture_folder
from tools.b06_image_artifacts.warning_baseline import build,check

class FidelityTests(unittest.TestCase):
 def fixture(self,root):
  files={'META-INF/MANIFEST.MF':b'Bundle-SymbolicName: test\r\nBundle-Version: 1.0.0\r\nBundle-ClassPath: lib/a.jar\r\n\r\n','lib/a.jar':b'jar','pom.xml':b'pom','META-INF/maven/g/a/pom.xml':b'embedded','OSGI-INF/l10n/bundle.properties':b'name','about_files/LICENSE':b'license','bin/ant':b'script','etc/log.xsl':b'xsl','src/resource.txt':b'resource','target/classes/X.class':b'class','target/work/live.log':b'excluded','target/surefire.properties':b'bound separately'}
  for n,v in files.items():
   p=root/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(v)
  return files
 def test_folder_capture_replay_same_complete_view(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t)/'bundle';files=self.fixture(root);dest=Path(t)/'copy.jar'
   before=bundle_content_view(root,kind='folder');proof=capture_folder(root,dest,['target/classes'])
   replay=bundle_content_view(dest,kind='folder-archive')
   self.assertEqual(before['entries'],replay['entries'])
   self.assertEqual(len(replay['entries']),len(files)-2)
   self.assertEqual(proof['exclusions'],EXCLUSIONS)
   self.assertIn('META-INF/maven/g/a/pom.xml',replay['entries']);self.assertIn('bin/ant',replay['entries'])
 def test_jar_never_filters_live_names_or_poms(self):
  b=io.BytesIO()
  with zipfile.ZipFile(b,'w') as z:
   z.writestr('META-INF/MANIFEST.MF',b'manifest');z.writestr('target/work/run.log',b'jar resource');z.writestr('pom.xml',b'pom')
  self.assertEqual(len(bundle_content_view(b.getvalue(),kind='jar')['entries']),3)
 def test_only_root_relative_named_exclusions(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);self.fixture(root);p=root/'resources/target/work/file';p.parent.mkdir(parents=True);p.write_bytes(b'keep')
   self.assertIn('resources/target/work/file',bundle_content_view(root,kind='folder')['entries'])
 def test_warning_intersection_and_new_failure(self):
  logs={str(i):f'2026-10-08T19:00:0{i}Z ERROR known /application/plugin_1.0.0.202610081015\n[WARNING] common\n'.encode() for i in range(3)}
  logs['0']+=b'[WARNING] one-off\n';b=build(logs)
  self.assertFalse(check(logs['0'],b)['passed']);self.assertTrue(check(logs['1'],b)['passed'])
  self.assertFalse(check(logs['1']+b'[WARNING] novel\n',b)['passed'])
  b['accepted'].append('[WARNING] forged')
  with self.assertRaises(ValueError):check(logs['0'],b)

 def test_new_plan_cannot_request_tower_without_six_checks(self):
  from tools.b06_image_artifacts.runtime_launch import request
  with self.assertRaisesRegex(ValueError,'six-checks-required'):
   request({'schema':'b06-runtime-closure-plan/2'},'0'*40)
 def test_shared_view_comparison_rejects_lost_resource(self):
  from tools.b06_image_artifacts.content_comparison import identity,compare
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);self.fixture(root);a=identity(root,'folder');(root/'bin/ant').unlink();b=identity(root,'folder')
   result=compare(a,b);self.assertFalse(result['passed']);self.assertEqual(result['removed'],['bin/ant'])
 def test_jar_bytes_copied_exactly(self):
  from tools.b06_image_artifacts.runtime_capture import stream_file
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);source=root/'original.jar';target=root/'copied.jar'
   with zipfile.ZipFile(source,'w') as z:
    z.writestr('META-INF/MANIFEST.MF',b'manifest');z.writestr('pom.xml',b'p');z.writestr('target/work/runtime-name',b'keep')
   with target.open('xb') as f:stream_file(source,f)
   self.assertEqual(source.read_bytes(),target.read_bytes())

 def test_authorization_window_does_not_change_frozen_plan(self):
  from tools.b06_image_artifacts.runtime_launch import request
  from lightyear_calibration.contracts import seal,canonical
  plan=seal(dict(schema='b06-runtime-closure-plan/2',id='b06-runtime-test',source_commit='1'*40,snapshot_sha256='2'*64,maximum_runtime_seconds=2700,cleanup_reserve_seconds=600,window=None))
  checks=dict(schema='b06-frozen-practice-checks/1',passed=True,checks={k:True for k in ('census','source_only','application_content','tycho','warning_baseline','frozen_bytes','cleanup')},source_commit=plan['source_commit'],snapshot_sha256=plan['snapshot_sha256'],plan_sha256=plan['content_sha256'])
  before=canonical(plan);window=dict(not_before_utc='2026-10-09T10:00:00Z',latest_start_utc='2026-10-09T10:05:00Z',deadline_utc='2026-10-09T11:00:00Z')
  _,_,artifacts=request(plan,'3'*40,window=window,practice=checks)
  self.assertEqual(canonical(plan),before);self.assertEqual(artifacts['window'],window)
  self.assertEqual(artifacts['plan'],plan);self.assertEqual(artifacts['practice'],checks)
  checks['snapshot_sha256']='4'*64
  with self.assertRaisesRegex(ValueError,'practice-plan-binding'):request(plan,'3'*40,window=window,practice=checks)

 def test_real_system_bundle_sentinel_census(self):
  from tools.b06_image_artifacts.frozen_runtime import bundle_census
  observed=dict(install_area='file:/application/org.idempiere.test/target/work',bundles=[
   dict(id=0,location='System Bundle'),
   dict(id=1,location='reference:file:/root/.m2/framework.jar'),
   dict(id=2,location='file:/application/test'),
   dict(id=3,location='file:/tmp/tycho_wrapped_source123.jar')])
  self.assertEqual(bundle_census(observed),{'system':1,'/root/.m2':1,'/application':1,'/tmp':1,'other':0})
  observed['bundles'][1]['location']='System Bundle'
  with self.assertRaisesRegex(ValueError,'tycho-file-url-required'):bundle_census(observed)

 def test_prepare_rejects_invalid_revision_before_writes(self):
  from tools.b06_image_artifacts.frozen_runtime import prepare
  with self.assertRaisesRegex(ValueError,'invalid-runtime-plan-id'):
   prepare(None,None,None,None,None,None,None,None,plan_id='../r10')
