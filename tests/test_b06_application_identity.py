import copy,hashlib,io,json,unittest,zipfile
from tools.b06_image_artifacts.application_identity import content,compare,records,bind_posting_class,bind_measured_posting_classes
from tools.b06_image_artifacts.transient_sources import classify,bind_measured
from tools.b06_image_artifacts.archive import inspect
from tools.b06_image_artifacts.runtime_producer import produce
from tools.b06_image_artifacts.runtime_closure import assemble
from test_b06_transient_sources import modern
from test_b06_tycho_runtime import signed_inputs

def jar(symbolic='org.idempiere.test',qualifier='one',*,class_bytes=b'class-bytes',resource=b'resource',extra=False,imports='org.example',requires='org.example.bundle',timestamp=(2026,10,8,0,0,0),header='Build-Timestamp',value='1'):
 out=io.BytesIO()
 with zipfile.ZipFile(out,'w') as z:
  manifest=('Manifest-Version: 1.0\r\nBundle-SymbolicName: '+symbolic+'\r\nBundle-Version: 1.2.3.'+qualifier+'\r\nBuilt-By: '+value+'\r\nBnd-LastModified: '+value+'\r\n'+header+': '+value+'\r\nImport-Package: '+imports+'\r\nRequire-Bundle: '+requires+'\r\nBundle-ClassPath: .\r\n\r\n').encode()
  for name,raw in [('META-INF/MANIFEST.MF',manifest),('org/example/Posting.class',class_bytes),('config.properties',resource)]+([('extra',b'added')] if extra else []):
   z.writestr(zipfile.ZipInfo(name,timestamp),raw)
 return out.getvalue()

def fixture(qualifier='one'):
 c,p,o,i,sources,loaded=modern();o['schema']='b06-runtime-launch-observation/4';apps={}
 c=c.replace(b'/app/test.jar',('/application/test-'+qualifier+'.jar').encode()).replace(b'/app/other.jar',('/application/other-'+qualifier+'.jar').encode())
 for b in o['bundles']:
  b['application_copy']=None
  if b['id'] not in (1,2):continue
  old='/app/'+('test.jar' if b['id']==1 else 'other.jar');new='/application/'+('test-' if b['id']==1 else 'other-')+qualifier+'.jar'
  b['location']='file:'+new;b['version']='1.2.3.'+qualifier
  raw=jar(b['symbolic_name'],qualifier,value=qualifier);dest=f"/results/runtime-application/{b['id']}.jar"
  b['application_copy']=dict(path=dest,sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),kind='jar');apps[dest]=raw
  for r in i['artifacts']:
   if r['path']==old:r.update(path=new,sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),kind='captured-application-bundle',capture_path=dest,**inspect(raw))
 loaded[0]['origin']='file:/application/test-'+qualifier+'.jar'
 i.update(transient_source_bundles=classify(o,sources,loaded),runtime_catalogue=loaded,application_content_bundles=records(o,apps))
 return c,p,o,i,sources,apps

def seal_fixture(d):
 c,p,o,i,sources,apps=d;raw,fork,e,receipt,s=signed_inputs(c,p,o,i)
 receipt=s.sign({**{k:v for k,v in receipt.items() if k not in ('signature','content_sha256')},'schema':'b06-runtime-launch-receipt/5'})
 r=produce(raw,c,p,i,receipt,s.public,e,fork_command=fork,transient_copies=sources,application_copies=apps)
 return r,s.public,e

class ApplicationIdentityTests(unittest.TestCase):
 def test_qualifier_and_zip_timestamps_only_pass(self):
  a=content(jar(),'/application/test-one.jar','org.idempiere.test','1.2.3.one')
  b=content(jar(qualifier='two',value='2',timestamp=(2026,10,9,2,0,0)),'/application/test-two.jar','org.idempiere.test','1.2.3.two')
  self.assertTrue(compare(a,b));self.assertNotEqual(a['archive_sha256'],b['archive_sha256']);self.assertEqual(b['qualifier'],'two')
  self.assertEqual({r['header'] for r in b['normalized_headers']},{'Bundle-Version','Built-By','Bnd-LastModified','Build-Timestamp'})
 def test_class_resource_extra_import_and_require_mutants_refuse(self):
  a=content(jar(),'/application/a.jar','org.idempiere.test','1.2.3.one')
  for changes in (dict(class_bytes=b'changed'),dict(resource=b'changed'),dict(extra=True),dict(imports='wrong'),dict(requires='wrong')):
   b=content(jar(**changes),'/application/a.jar','org.idempiere.test','1.2.3.one')
   with self.subTest(changes=changes),self.assertRaisesRegex(ValueError,'content-differs'):compare(a,b)
 def test_outside_application_cannot_normalize(self):
  for path in ('/root/.m2/a.jar','/jdk/lib/a.jar','/tmp/a.jar','/application/../a.jar'):
   with self.subTest(path=path),self.assertRaisesRegex(ValueError,'origin'):content(jar(),path,'org.idempiere.test','1.2.3.one')
 def test_unlisted_header_stays_exact(self):
  a=content(jar(header='Build-Time',value='1'),'/application/a.jar','org.idempiere.test','1.2.3.one')
  b=content(jar(header='Build-Time',value='2'),'/application/a.jar','org.idempiere.test','1.2.3.one')
  with self.assertRaisesRegex(ValueError,'content-differs'):compare(a,b)
 def test_minor_version_is_not_normalized(self):
  raw=jar().replace(b'not a real replacement',b'ignored')
  with self.assertRaisesRegex(ValueError,'identity-mismatch'):content(raw,'/application/a.jar','org.idempiere.test','1.3.3.one')
 def test_producer_replay_and_measured_matching(self):
  a=fixture('one');b=fixture('two');ar,ak,ae=seal_fixture(a);br,bk,be=seal_fixture(b)
  self.assertEqual(ar['schema'],'b06-resolved-runtime/5');self.assertFalse(ar['native_admission'])
  self.assertTrue(bind_measured(ar,br,closure_inventory=a[3],measured_inventory=b[3],closure_key=ak,measured_key=bk,closure_expected=ae,measured_expected=be,closure_copies=a[4],measured_copies=b[4],closure_application_copies=a[5],measured_application_copies=b[5]))
  self.assertFalse(assemble(a[3],ar,launch_key=ak,expected_launch=ae,transient_copies=a[4],application_copies=a[5])['native_admission'])
 def test_replay_missing_or_changed_copy_refuses(self):
  d=fixture();r,k,e=seal_fixture(d)
  for apps in (None,{},dict(d[5],**{'/results/runtime-application/1.jar':jar(resource=b'bad')})):
   with self.subTest(apps=apps is None),self.assertRaises(ValueError):assemble(d[3],r,launch_key=k,expected_launch=e,transient_copies=d[4],application_copies=apps)
 def test_posting_class_binding_requires_exact_executed_bytes(self):
  d=fixture();r,k,e=seal_fixture(d);kwargs=dict(inventory=d[3],launch_key=k,expected_launch=e,transient_copies=d[4],application_copies=d[5])
  proof=bind_posting_class(r,'org.example.Posting','/application/test-one.jar',b'class-bytes',**kwargs)
  self.assertEqual(proof['class_sha256'],hashlib.sha256(b'class-bytes').hexdigest())
  with self.assertRaisesRegex(ValueError,'class-bytes'):bind_posting_class(r,'org.example.Posting','/application/test-one.jar',b'changed',**kwargs)
 def test_jar_hash_stays_exact_for_nonapplication_artifact(self):
  a=fixture();b=fixture();ar,ak,ae=seal_fixture(a)
  next(x for x in b[3]['artifacts'] if x['path']==b[2]['java_class_path'])['sha256']='9'*64;br,bk,be=seal_fixture(b)
  with self.assertRaisesRegex(ValueError,'artifacts-differ'):bind_measured(ar,br,closure_inventory=a[3],measured_inventory=b[3],closure_key=ak,measured_key=bk,closure_expected=ae,measured_expected=be,closure_copies=a[4],measured_copies=b[4],closure_application_copies=a[5],measured_application_copies=b[5])

 def test_measured_posting_consumer_replays_both_runs_then_checks_class_bytes(self):
  a=fixture('one');b=fixture('two');ar,ak,ae=seal_fixture(a);br,bk,be=seal_fixture(b)
  proofs=dict(closure_inventory=a[3],measured_inventory=b[3],closure_key=ak,measured_key=bk,closure_expected=ae,measured_expected=be,closure_copies=a[4],measured_copies=b[4],closure_application_copies=a[5],measured_application_copies=b[5])
  classes={'org.example.Posting':dict(defining_path='/application/test-two.jar',class_bytes=b'class-bytes')}
  self.assertFalse(bind_measured_posting_classes(ar,br,classes,**proofs)['native_admission'])
  classes['org.example.Posting']['class_bytes']=b'wrong'
  with self.assertRaisesRegex(ValueError,'class-bytes'):bind_measured_posting_classes(ar,br,classes,**proofs)
