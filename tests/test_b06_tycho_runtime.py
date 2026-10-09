"""Source-shaped Tycho 4.0.8 fixture; synthetic only, never native evidence."""
import copy,hashlib,json,tempfile,unittest
from pathlib import Path
from tools.b06_image_artifacts import tycho_runtime as tycho
from tools.b06_image_artifacts.runtime_producer import produce,h
from tools.b06_image_artifacts.runtime_closure import assemble
from test_b06_image_artifacts import test_signer

PROPERTIES=b'''# Tycho PropertiesWrapper / Java Properties.store shape
classLoaderOrder=booter
printWires=false
trimStackTrace=true
rerunFailingTestsCount=0
reportsdirectory=/application/org.idempiere.test/target/surefire-reports
printBundles=false
runOrder=filesystem
testclassesdirectory=/application/org.idempiere.test/target/test-classes
redirectTestOutputToFile=false
skipAfterFailureCount=0
testprovider=org.apache.maven.surefire.junitplatform.JUnitPlatformProvider
testpluginname=org.idempiere.test
__provider.tc.0=org.idempiere.test.B06RuntimeCatalogTest
__provider.junit.jupiter.execution.parallel.enabled=false
testSuiteXmlFiles0=/application/public-suite.xml
'''

def fixture():
 launcher='/repo/org.eclipse.equinox.launcher-1.6.500.jar'
 install='/application/org.idempiere.test/target/work'
 config=('osgi.bundles=reference\\:file\\:/app/test.jar,reference\\:file\\:/app/other.jar@4\\:start\n'
         'osgi.install.area=file\\:'+install+'\nosgi.framework=file\\:/app/framework.jar\n').encode()
 command=['/jdk/bin/java','-Duser.timezone=UTC','-jar',launcher,'-install',install,'-configuration',install+'/configuration','-testproperties',tycho.ORIGINAL_PROPERTIES]
 obs=dict(schema='b06-runtime-launch-observation/2',configuration_url='file:'+install+'/configuration/',
  install_area='file:'+install+'/',framework_url='file:/app/framework.jar',java_home='/jdk',java_class_path=launcher,
  fork_command=command,bundles=[dict(id=0,state=32,location='system',symbolic_name='org.eclipse.osgi'),
   dict(id=1,state=4,location='initial@reference:file:../../../../app/test.jar',symbolic_name='org.idempiere.test'),
   dict(id=2,state=2,location='initial@reference:file:../../../../app/other.jar',symbolic_name='unresolved.optional')])
 paths=['/app/test.jar','/app/other.jar','/app/framework.jar',launcher,'/jdk/bin/java','/jdk/bin/jimage','/jdk/lib/modules']
 rows=[dict(path=p,sha256=hashlib.sha256(p.encode()).hexdigest(),bytes=10,class_entries=1,nested_archives=0) for p in paths]
 rows[-1].update(expanded_class_entries=3,expanded_class_bytes=30)
 inv=dict(schema='b06-image-inventory/1',failure=None,artifacts=rows)
 return config,PROPERTIES,obs,inv


def signed_inputs(config,props,obs,inv):
 signer=test_signer();raw=json.dumps(obs).encode();fork=json.dumps(obs['fork_command']).encode()
 expected=dict(probe_sha256='a'*64,image='sha256:'+'b'*64,java_sha256=next(r['sha256'] for r in inv['artifacts'] if r['path']=='/jdk/bin/java'),
  plan_sha256='c'*64,tower_decision_sha256='d'*64,measured_command_sha256='e'*64,closure_command_sha256='f'*64,fork_command_sha256=h(fork))
 receipt=signer.sign(dict(schema='b06-runtime-launch-receipt/3',passed=True,cleanup_passed=True,bindings=expected,
  outputs={'observation':h(raw),'config.ini':h(config),'surefire.properties':h(props),'inventory':h(json.dumps(inv,sort_keys=True).encode()),'fork-command':h(fork)}))
 return raw,fork,expected,receipt,signer

class TychoRuntimeTests(unittest.TestCase):
 def test_real_key_shape_and_all_values_recorded(self):
  c,p,o,i=fixture();r=tycho.read(c,p,o,o['fork_command'])
  self.assertEqual(r['tycho_properties'],tycho.properties(p));self.assertEqual(r['source_sha256']['surefire.properties'],h(p))
  self.assertEqual(r['boot_classpath'],[o['java_class_path']]);self.assertEqual(r['suite_xml_files'],['/application/public-suite.xml'])
 def test_properties_store_escapes_and_duplicate_decoded_keys(self):
  self.assertEqual(tycho.properties(b'a=file\\:/tmp/a\\ b\nb=\\u0041\nc=one\\\n two\n'),dict(a='file:/tmp/a b',b='A',c='onetwo'))
  for raw in (b'a=1\n\\u0061=2',b'a=\\q',b'a=\\u12',b'a=one\\'):
   with self.subTest(raw=raw),self.assertRaises(ValueError):tycho.properties(raw)
 def test_unknown_keys_and_old_maven_classpath_refused(self):
  c,p,o,i=fixture()
  for key in ('unexpected','classPathUrl.0','__provider.','testSuiteXmlFilesX'):
   with self.subTest(key=key),self.assertRaisesRegex(ValueError,'unknown-tycho-property'):tycho.read(c,p+(key+'=x\n').encode(),o,o['fork_command'])
 def test_wrong_missing_or_unresolved_test_plugin(self):
  for fault in ('property','missing','state','duplicate'):
   c,p,o,i=fixture()
   if fault=='property':p=p.replace(b'testpluginname=org.idempiere.test',b'testpluginname=forged')
   elif fault=='missing':o['bundles'][1]['symbolic_name']='other'
   elif fault=='state':o['bundles'][1]['state']=2
   else:o['bundles'][2]['symbolic_name']='org.idempiere.test'
   with self.subTest(fault=fault),self.assertRaisesRegex(ValueError,'testpluginname|test-bundle'):tycho.read(c,p,o,o['fork_command'])
 def test_empty_multiple_or_nonlauncher_boot_classpath(self):
  for cp in ('','/a:/b','/a:/b:/c','/app/unrelated.jar'):
   c,p,o,i=fixture();o['java_class_path']=cp
   with self.subTest(cp=cp),self.assertRaisesRegex(ValueError,'boot-classpath|equinox-launcher'):tycho.read(c,p,o,o['fork_command'])
 def test_missing_and_duplicate_properties_files(self):
  with tempfile.TemporaryDirectory() as t:
   r=Path(t)
   with self.assertRaisesRegex(ValueError,'exactly-one'):tycho.one_properties_file(r)
   (r/'surefire.properties').write_bytes(PROPERTIES)
   self.assertEqual(tycho.one_properties_file(r).read_bytes(),PROPERTIES)
   (r/'nested').mkdir();(r/'nested/surefire.properties').write_bytes(PROPERTIES)
   with self.assertRaisesRegex(ValueError,'exactly-one'):tycho.one_properties_file(r)
 def test_capture_is_exact_and_preserves_existing_copies(self):
  with tempfile.TemporaryDirectory() as t:
   r=Path(t);target=r/'target';runtime=r/'runtime';target.mkdir();runtime.mkdir();(runtime/'other.properties').write_bytes(b'old')
   with self.assertRaisesRegex(ValueError,'not-preserved'):tycho.capture_properties(target,runtime)
   (target/'surefire.properties').write_bytes(PROPERTIES);tycho.capture_properties(target,runtime)
   self.assertEqual((runtime/'surefire.properties').read_bytes(),PROPERTIES);self.assertEqual((runtime/'other.properties').read_bytes(),b'old')
   with self.assertRaises(FileExistsError):tycho.capture_properties(target,runtime)
 def test_fork_command_binding(self):
  for flag in ('-jar','-testproperties','-install','-configuration'):
   c,p,o,i=fixture();o['fork_command'][o['fork_command'].index(flag)+1]='/wrong'
   with self.subTest(flag=flag),self.assertRaisesRegex(ValueError,'mismatch'):tycho.read(c,p,o,o['fork_command'])
 def test_duplicate_fork_flag(self):
  c,p,o,i=fixture();o['fork_command']+=['-jar',o['java_class_path']]
  with self.assertRaisesRegex(ValueError,'fork-option'):tycho.read(c,p,o,o['fork_command'])
 def test_config_bundle_disagreement(self):
  c,p,o,i=fixture();c=c.replace(b'/app/other.jar',b'/app/forged.jar')
  with self.assertRaisesRegex(ValueError,'bundles-mismatch'):tycho.read(c,p,o,o['fork_command'])
 def test_producer_and_independent_replay_v3(self):
  c,p,o,i=fixture();raw,fork,expected,receipt,signer=signed_inputs(c,p,o,i)
  r=produce(raw,c,p,i,receipt,signer.public,expected,fork_command=fork)
  self.assertEqual(r['schema'],'b06-resolved-runtime/3');self.assertNotIn('surefire_booter_classpath',r)
  self.assertEqual(r['tycho_properties'],tycho.properties(p));self.assertEqual(r['unresolved_bundle_ids'],[2]);self.assertFalse(r['native_admission'])
  self.assertGreater(assemble(i,r,launch_key=signer.public,expected_launch=expected)['maximum_classes'],0)
  r['fork_command_utf8']=r['fork_command_utf8'].replace('-jar','-wrong')
  with self.assertRaises(ValueError):assemble(i,r,launch_key=signer.public,expected_launch=expected)
 def test_launcher_must_be_measured_even_with_valid_signed_receipt(self):
  c,p,o,i=fixture();i['artifacts']=[r for r in i['artifacts'] if r['path']!=o['java_class_path']]
  raw,fork,expected,receipt,signer=signed_inputs(c,p,o,i)
  with self.assertRaisesRegex(ValueError,'launcher-not-in-inventory'):produce(raw,c,p,i,receipt,signer.public,expected,fork_command=fork)
 def test_changed_capture_and_missing_fork_bytes_refuse(self):
  c,p,o,i=fixture();raw,fork,expected,receipt,signer=signed_inputs(c,p,o,i)
  for actual in (None,fork+b' '):
   with self.subTest(actual=actual),self.assertRaisesRegex(ValueError,'fork-command-binding'):produce(raw,c,p,i,receipt,signer.public,expected,fork_command=actual)
  with self.assertRaisesRegex(ValueError,'output-changed'):produce(raw,c,p+b'\n',i,receipt,signer.public,expected,fork_command=fork)
 def test_no_silent_observation_upgrade(self):
  c,p,o,i=fixture();o['schema']='b06-runtime-launch-observation/1';raw,fork,expected,receipt,signer=signed_inputs(c,p,o,i)
  with self.assertRaisesRegex(ValueError,'observation-schema'):produce(raw,c,p,i,receipt,signer.public,expected,fork_command=fork)

 def test_duplicate_config_entries_are_recorded_not_silently_dropped(self):
  c,p,o,i=fixture();c=c.replace(b'reference\\:file\\:/app/test.jar,',b'reference\\:file\\:/app/test.jar,reference\\:file\\:/app/test.jar,')
  r=tycho.read(c,p,o,o['fork_command']);self.assertEqual(r['duplicate_config_bundle_paths'],['/app/test.jar'])
  self.assertEqual(len(r['equinox_bundles']),3);self.assertEqual(len(r['observed_bundle_paths']),2)
 def test_offline_review_never_substitutes_missing_properties(self):
  from tools.b06_image_artifacts.tycho_offline import inspect
  c,p,o,i=fixture();o['schema']='b06-runtime-launch-observation/1';o.pop('fork_command')
  with tempfile.TemporaryDirectory() as t:
   a=Path(t);r=a/'results';(r/'runtime').mkdir(parents=True)
   (r/'closure-observation.json').write_text(json.dumps(o));(r/'runtime/config.ini').write_bytes(c)
   (r/'measured-command.json').write_text('["mvn"]');(r/'command.json').write_text('["mvn"]')
   (r/'maven.log').write_text('['+', '.join(fixture()[2]['fork_command'])+']')
   result=inspect(a);self.assertTrue(result['layout_checks_passed'])
   self.assertFalse(result['full_producer_replay_passed']);self.assertFalse(result['surefire_properties_preserved'])
   self.assertEqual(len(result['producer_replay_blocked_by']),4)
