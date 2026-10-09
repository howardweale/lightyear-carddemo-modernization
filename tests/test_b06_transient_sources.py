"""Synthetic source-bundle controls; no native or qualification claim."""
import copy,hashlib,io,json,tempfile,unittest,zipfile
from pathlib import Path
from tools.b06_image_artifacts.transient_sources import classify,copies_at,catalogue,bind_measured
from tools.b06_image_artifacts.runtime_producer import produce
from tools.b06_image_artifacts.runtime_closure import assemble
from tools.b06_image_artifacts.runtime_inventory import read_file
from test_b06_tycho_runtime import fixture,signed_inputs

def jar(*,code=False,nested=False,header=True,extra=b''):
 b=io.BytesIO()
 with zipfile.ZipFile(b,'w') as z:
  z.writestr('META-INF/MANIFEST.MF','Manifest-Version: 1.0\r\nBundle-SymbolicName: example.source\r\nBundle-Version: 1.2.3\r\n'+('Eclipse-SourceBundle: example;version="1.2.3"\r\n' if header else '')+'\r\n')
  z.writestr('Source.java',b'// source only'+extra)
  if code:z.writestr('hidden/Code.class',b'code')
  if nested:z.writestr('lib/code.jar',jar())
 return b.getvalue()

def modern(raw=None):
 c,p,o,i=fixture();raw=jar() if raw is None else raw
 o.update(schema='b06-runtime-launch-observation/3',java_tmpdir='/tmp',loaded_bundle_classes=[dict(name='Test',bundle_id=1)])
 for b in o['bundles']:b.update(version='1.2.3',eclipse_source_bundle=False,preserved_copy=None)
 b=dict(id=3,state=2,location='file:/tmp/tycho_wrapped_source123.jar',symbolic_name='example.source',version='1.2.3',eclipse_source_bundle=True,
  preserved_copy=dict(path='/results/runtime-transient/3.jar',sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw)))
 o['bundles'].append(b)
 c=c.replace(b'osgi.bundles=',b'osgi.bundles=reference\\:file\\:/tmp/tycho_wrapped_source123.jar,')
 copies={b['preserved_copy']['path']:raw};loaded=[dict(name='Test',origin='file:/app/test.jar')]
 return c,p,o,i,copies,loaded

def resolution(data):
 c,p,o,i,copies,loaded=data
 i.update(transient_source_bundles=classify(o,copies,loaded),runtime_catalogue=loaded)
 raw,fork,expected,receipt,signer=signed_inputs(c,p,o,i)
 body={k:v for k,v in receipt.items() if k not in ('signature','content_sha256')};body['schema']='b06-runtime-launch-receipt/4';receipt=signer.sign(body)
 r=produce(raw,c,p,i,receipt,signer.public,expected,fork_command=fork,transient_copies=copies)
 return r,signer.public,expected

class TransientSourceTests(unittest.TestCase):
 def test_deleted_source_copy_passes_producer_and_replay(self):
  d=modern();r,k,e=resolution(d);self.assertEqual(r['schema'],'b06-resolved-runtime/4')
  self.assertNotIn('/tmp/tycho_wrapped_source123.jar',r['equinox_bundles'])
  self.assertNotIn('/tmp/tycho_wrapped_source123.jar',r['artifact_sha256'])
  closure=assemble(d[3],r,launch_key=k,expected_launch=e,transient_copies=d[4]);self.assertFalse(closure['native_admission'])
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);(root/'runtime-transient').mkdir();(root/'runtime-transient/3.jar').write_bytes(d[4]['/results/runtime-transient/3.jar'])
   self.assertEqual(copies_at(d[2],root),d[4]) # original file is never opened
 def test_tmp_without_header_refused(self):
  d=modern();d[2]['bundles'][-1]['eclipse_source_bundle']=False
  with self.assertRaisesRegex(ValueError,'header'):resolution(d)
 def test_manifest_header_is_inspected_not_just_observation_bool(self):
  with self.assertRaisesRegex(ValueError,'manifest'):resolution(modern(jar(header=False)))
 def test_class_or_nested_jar_refused(self):
  for raw in (jar(code=True),jar(nested=True)):
   with self.subTest(raw=len(raw)),self.assertRaisesRegex(ValueError,'has-code'):resolution(modern(raw))
 def test_attributed_class_refused_in_snapshot_or_final_catalogue(self):
  for use_snapshot in (True,False):
   d=modern()
   if use_snapshot:d[2]['loaded_bundle_classes'].append(dict(name='Injected',bundle_id=3))
   else:d[5].append(dict(name='Injected',origin='jar:file:/tmp/tycho_wrapped_source123.jar!/Code.class'))
   with self.subTest(snapshot=use_snapshot),self.assertRaisesRegex(ValueError,'loaded-class'):resolution(d)
 def test_nonmatching_tmp_name_refused(self):
  d=modern();d[2]['bundles'][-1]['location']='file:/tmp/other.source.jar'
  with self.assertRaisesRegex(ValueError,'location-refused'):resolution(d)
 def test_missing_non_tmp_file_is_not_exempted(self):
  with tempfile.TemporaryDirectory() as t:
   with self.assertRaises(FileNotFoundError):read_file(Path(t)/'application.jar')
 def test_missing_tampered_and_unbound_copy_refused(self):
  for fault in ('missing','tampered','unbound','metadata','no-catalogue'):
   d=modern()
   if fault=='missing':d[4].clear()
   elif fault=='tampered':d[4]['/results/runtime-transient/3.jar']+=b'bad'
   elif fault=='unbound':d[4]['/results/runtime-transient/4.jar']=jar()
   elif fault=='metadata':d[2]['bundles'][-1]['version']='wrong'
   else:d[5].clear()
   with self.subTest(fault=fault),self.assertRaises(ValueError):resolution(d)
 def test_replay_requires_original_copy_bytes(self):
  d=modern();r,k,e=resolution(d)
  for copies in (None,{},{'/results/runtime-transient/3.jar':jar(extra=b'changed')}):
   with self.subTest(copies=None if copies is None else len(copies)),self.assertRaises(ValueError):assemble(d[3],r,launch_key=k,expected_launch=e,transient_copies=copies)
 def test_cross_run_source_identity_only_with_proofs_ordinary_exact(self):
  a=modern();ar,ak,ae=resolution(a)
  b=modern(jar(extra=b'different wrapper bytes'));b[2]['bundles'][-1]['location']='file:/tmp/tycho_wrapped_source456.jar';b=(b[0].replace(b'123.jar',b'456.jar'),*b[1:]);br,bk,be=resolution(b)
  args=dict(closure_inventory=a[3],measured_inventory=b[3],closure_key=ak,measured_key=bk,closure_expected=ae,measured_expected=be,closure_copies=a[4],measured_copies=b[4])
  self.assertTrue(bind_measured(ar,br,**args))
  b[3]['artifacts'][0]['sha256']='9'*64;br,bk,be=resolution(b);args.update(measured_key=bk,measured_expected=be)
  with self.assertRaisesRegex(ValueError,'differ'):bind_measured(ar,br,**args)
 def test_duplicate_identity_refused(self):
  d=modern();b=copy.deepcopy(d[2]['bundles'][-1]);b['id']=4;b['location']='file:/tmp/tycho_wrapped_source456.jar';b['preserved_copy']['path']='/results/runtime-transient/4.jar';d[2]['bundles'].append(b);d[4][b['preserved_copy']['path']]=jar()
  with self.assertRaisesRegex(ValueError,'duplicate-transient-identity'):resolution(d)
 def test_catalogue_closed_rows(self):
  self.assertEqual(catalogue(b'A\tfile:/app.jar\n'),[dict(name='A',origin='file:/app.jar')])
  for raw in (b'',b'A\tB\tC'):
   with self.assertRaises(ValueError):catalogue(raw)
