"""Disk-backed synthetic r5b/r7 shapes through the real worker, producer, replay."""
import copy,hashlib,json,io,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from tools.b06_image_artifacts import runtime_capture as cap,runtime_worker as worker
from tools.b06_image_artifacts.runtime_inventory import measure
from tools.b06_image_artifacts.runtime_producer import produce
from tools.b06_image_artifacts.runtime_closure import assemble
from tools.b06_image_artifacts.application_identity import copies_at
from tools.b06_image_artifacts.transient_sources import copies_at as transient_copies_at
from test_b06_application_identity import fixture
from test_b06_tycho_runtime import signed_inputs

class RuntimeCaptureTests(unittest.TestCase):
 def folder(self,root):
  for name,data in {'META-INF/MANIFEST.MF':b'Manifest-Version: 1.0\r\nBundle-SymbolicName: x\r\nBundle-Version: 1.0.0\r\nBundle-ClassPath: .\r\n\r\n','target/classes/p/A.class':b'A','target/test-classes/p/T.class':b'T','target/work/volatile':b'not captured','target/surefire-reports/log':b'not captured','resource.txt':b'resource'}.items():
   p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
 def test_folder_runtime_only_and_dev_output(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t)/'app';self.folder(root);dest=Path(t)/'copy.jar'
   proof=cap.capture_folder(root,dest,['target/classes','target/test-classes'])
   with zipfile.ZipFile(dest) as z:self.assertEqual(set(z.namelist()),{'META-INF/MANIFEST.MF','target/classes/p/A.class','target/test-classes/p/T.class','resource.txt'})
   self.assertEqual(proof['policy'],cap.POLICY)
 def test_folder_mutation_writes_specific_worker_error(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t)/'app';self.folder(root);real=cap.stream_file
   def changing(p,out):
    row=real(p,out)
    if p.name=='resource.txt':p.write_bytes(b'changed')
    return row
   try:
    with patch.object(cap,'stream_file',changing):cap.capture_folder(root,Path(t)/'copy.jar',['target/classes'])
   except ValueError as e:cap.failure(Path(t),'application-capture',e)
   else:self.fail('mutation accepted')
   error=json.loads((Path(t)/'worker-error.json').read_bytes())
   self.assertEqual(error['stage'],'application-capture');self.assertIn('changed-during-capture',error['message']);self.assertTrue(error['stack_trace'])
 def test_missing_declared_root_reports_exact_path_and_still_refuses(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t)/'app';self.folder(root)
   missing='target/classes/missing-output'
   with self.assertRaises(ValueError) as caught:cap.selection(root,[missing])
   self.assertEqual(str(caught.exception),f'runtime-folder-root-missing: bundle={root.as_posix()}; root={missing}; path={(root/missing).as_posix()}')
 def test_optional_dev_output_absence_is_recorded_not_created(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t)/'app';self.folder(root)
   (root/'target/test-classes/p/T.class').unlink();(root/'target/test-classes/p').rmdir();(root/'target/test-classes').rmdir()
   proof=cap.capture_folder(root,Path(t)/'copy.jar',['target/classes','target/test-classes'])
   self.assertEqual(proof['absent_dev_roots'],['target/test-classes'])
   self.assertFalse((root/'target/test-classes').exists())
   obs={'install_area':'file:/application/','bundles':[{'location':'file:/application/test','runtime_selection':proof}]}
   cap.validate_absent_origins(obs,[{'name':'Test','origin':'file:/application/test/target/classes/'}])
   with self.assertRaisesRegex(ValueError,'loaded-class-from-absent'):
    cap.validate_absent_origins(obs,[{'name':'Test','origin':'file:/application/test/target/test-classes/'}])
 def test_missing_manifest_root_is_not_optional_dev(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t)/'app';self.folder(root)
   p=root/'META-INF/MANIFEST.MF';p.write_bytes(p.read_bytes().replace(b'Bundle-ClassPath: .',b'Bundle-ClassPath: target/test-classes/missing'))
   with self.assertRaisesRegex(ValueError,'runtime-folder-root-missing'):cap.selection(root,['target/test-classes/missing'])
 def test_dev_root_appearing_during_capture_refuses(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t)/'app';self.folder(root)
   (root/'target/test-classes/p/T.class').unlink();(root/'target/test-classes/p').rmdir();(root/'target/test-classes').rmdir()
   real=cap.stream_file
   def change(p,out):
    row=real(p,out);(root/'target/test-classes').mkdir(exist_ok=True);return row
   with patch.object(cap,'stream_file',change),self.assertRaisesRegex(ValueError,'runtime-dev-presence-changed'):
    cap.capture_folder(root,Path(t)/'copy.jar',['target/test-classes'])
 def test_live_dev_root_refused(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t)/'app';self.folder(root)
   for dev in ('target/work','../outside','target/surefire-reports'):
    with self.subTest(dev=dev),self.assertRaises(ValueError):cap.capture_folder(root,Path(t)/'copy.jar',[dev])
 def test_structured_probe_error_is_reported_verbatim_before_missing_observation(self):
  with tempfile.TemporaryDirectory() as t:
   raw=b'{"exception_class":"Example","message":"lost\\ncopy","stack_trace":"trace","stage":"capture"}'
   (Path(t)/'closure-error.json').write_bytes(raw)
   fake=type('Output',(),{'buffer':io.BytesIO()})()
   with patch('sys.stderr',fake),self.assertRaisesRegex(ValueError,'verbatim'):cap.probe_result(t)
   self.assertEqual(fake.buffer.getvalue(),raw+b'\n')
 def test_completion_hash_and_missing_marker_refuse(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);(root/'closure-observation.json').write_text('{}')
   with self.assertRaises(FileNotFoundError):cap.probe_result(root)
   (root/'closure-complete.json').write_text('{"status":"complete","observation_sha256":"bad"}')
   with self.assertRaisesRegex(ValueError,'completion-binding'):cap.probe_result(root)
 def test_jar_mutation_with_restored_metadata_is_refused(self):
  import os
  from test_b06_application_identity import jar
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);app=root/'app.jar';app.write_bytes(jar());out=root/'out';out.mkdir()
   obs={'schema':'b06-runtime-launch-observation/5','install_area':'file:/application/','fork_command':[], 'bundles':[{'id':1,'location':'file:/application/app.jar','symbolic_name':'org.idempiere.test'}]}
   (out/'closure-observation.json').write_text(json.dumps(obs));(out/'closure-complete.json').write_text('{}')
   real=cap.stream_file
   def changed(src,dst):
    row=real(src,dst);before=src.stat();data=bytearray(src.read_bytes());data[-1]^=1;src.write_bytes(data);os.utime(src,ns=(before.st_atime_ns,before.st_mtime_ns));return row
   with patch.object(cap,'stream_file',changed),self.assertRaisesRegex(ValueError,'jar-changed'):cap.capture_application(obs,out,resolve=lambda p:app)
   self.assertFalse((out/'runtime-application').exists());self.assertFalse((out/'worker-observation.json').exists())
 def full(self,shape):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);out=root/'results';out.mkdir();fs=root/'fs';fs.mkdir()
   resolve=lambda v:fs/str(v).lstrip('/')
   c,p,obs,unused,sources,apps=fixture();obs['schema']='b06-runtime-launch-observation/5';obs['osgi_dev']=''
   for b in obs['bundles']:
    b.pop('application_copy',None)
    if b['id'] in (1,2):
     raw=apps[f"/results/runtime-application/{b['id']}.jar"]
     origin=b['location'].removeprefix('file:');dest=resolve(origin);dest.parent.mkdir(parents=True,exist_ok=True)
     if shape.startswith('r7-folder'):
      old=origin;origin=origin.removesuffix('.jar');b['location']='file:'+origin;c=c.replace(old.encode(),origin.encode());dest=resolve(origin);dest.mkdir()
      with zipfile.ZipFile(io.BytesIO(raw)) as z:z.extractall(dest)
      if b['id']==1:
       for n,data in {'target/classes/p/Real.class':b'actual-dev-output','target/test-classes/p/Test.class':b'test-dev-output','target/work/live.log':b'excluded'}.items():
        if shape=='r7-folder-absent' and n.startswith('target/test-classes/'):continue
        f=dest/n;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(data)
       dev='/application/org.idempiere.test/target/work/dev.properties';f=resolve(dev);f.parent.mkdir(parents=True,exist_ok=True)
       f.write_text(b['symbolic_name']+'='+origin+'/target/classes,'+origin+'/target/test-classes\n')
       obs['osgi_dev']='file:'+dev;c+=('osgi.dev=file\\:'+dev+'\n').encode()
     else:dest.write_bytes(raw)
   # Saved r5b/r7 scale: 44 application + 203 Maven + 102 transient + system.
   # Synthetic bytes/identities only; not substituted into either failed record.
   extra=[];next_id=4
   from test_b06_application_identity import jar as appjar
   for group,count in (('application',42),('maven',203),('transient',101)):
    for index in range(count):
     symbolic=f'fixture.{group}.{index}'+('.source' if group=='transient' else '')
     origin=(f'/application/fixture/{index}.jar' if group=='application' else f'/root/.m2/fixture/{index}.jar' if group=='maven' else f'/tmp/tycho_wrapped_source{index+1000}.jar')
     raw=appjar(symbolic,qualifier='one')
     row=dict(id=next_id,state=4,location='file:'+origin,symbolic_name=symbolic,version='1.2.3.one',eclipse_source_bundle=group=='transient',preserved_copy=None)
     if group=='transient':
      buf=io.BytesIO()
      with zipfile.ZipFile(buf,'w') as z:z.writestr('META-INF/MANIFEST.MF',f'Manifest-Version: 1.0\r\nBundle-SymbolicName: {symbolic}\r\nBundle-Version: 1.2.3.one\r\nEclipse-SourceBundle: fixture\r\n\r\n')
      raw=buf.getvalue();dest=f'/results/runtime-transient/{next_id}.jar';sources[dest]=raw
      row['preserved_copy']=dict(path=dest,sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))
     else:
      f=resolve(origin);f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(raw)
     obs['bundles'].append(row);extra.append('reference\\:file\\:'+origin);next_id+=1
   c=c.replace(b'osgi.bundles=',('osgi.bundles='+','.join(extra)+',').encode())
   # Complete, class-free preserved source copy survives deletion of /tmp original.
   (out/'runtime-transient').mkdir()
   for n,raw in sources.items():(out/'runtime-transient'/Path(n).name).write_bytes(raw)
   raw=json.dumps(obs).encode();(out/'closure-observation.json').write_bytes(raw)
   (out/'closure-complete.json').write_text(json.dumps(dict(status='complete',observation_sha256=hashlib.sha256(raw).hexdigest())))
   configuration=resolve('/application/org.idempiere.test/target/work/configuration');configuration.mkdir(parents=True);(configuration/'config.ini').write_bytes(c)
   runtime=out/'runtime';runtime.mkdir();(runtime/'config.ini').write_bytes(c);(runtime/'surefire.properties').write_bytes(p)
   (runtime/'TEST.xml').write_text('<testsuite><testcase classname="org.idempiere.test.B06RuntimeCatalogTest"/></testsuite>')
   # accept() requires a TEST- prefix, matching real Tycho reports.
   (runtime/'TEST.xml').rename(runtime/'TEST-probe.xml')
   loaded=out/'loaded';loaded.mkdir();lines=[]
   for n in sorted(worker.TARGETS):
    data=n.encode();sha=hashlib.sha256(data).hexdigest();(loaded/(sha+'.class')).write_bytes(data);lines.append(f'{n}\t{sha}\tfile:/application/test-one.jar\tfixture')
   (loaded/'loaded.tsv').write_text('\n'.join(lines));(out/'runtime-catalogue.tsv').write_text('Test\tfile:/application/test-one.jar\n')
   (out/'attempt.json').write_text(json.dumps(dict(exit_code=0,model_calls=0,native_pairs=0,database_containers=0,qualified=False)))
   paths=['/app/framework.jar',obs['java_class_path'],'/jdk/bin/java','/jdk/bin/jimage','/jdk/lib/modules']
   for n in paths:
    f=resolve(n);f.parent.mkdir(parents=True,exist_ok=True)
    if n.endswith('.jar'):
     with zipfile.ZipFile(f,'w') as z:z.writestr('X.class',b'fixture')
    else:f.write_bytes(b'fixture-'+n.encode())
   def synthetic_jimage(args,**kw):
    dest=Path(args[args.index('--dir')+1]);dest.mkdir();(dest/'Object.class').write_bytes(b'synthetic-JDK-class')
    return type('Exit',(),dict(returncode=0,stdout=b'synthetic offline jimage',stderr=b''))()
   def measured(*a,**kw):return measure(*a,**kw,resolve=resolve,jimage_runner=synthetic_jimage)
   inventory=worker.process_outputs(out,0,resolve=resolve,measure_fn=measured)
   observed=json.loads((out/'worker-observation.json').read_bytes())
   ac=copies_at(observed,out);tc=transient_copies_at(observed,out)
   raw,fork,expected,receipt,signer=signed_inputs(c,p,observed,inventory)
   receipt=signer.sign({**{k:v for k,v in receipt.items() if k not in ('signature','content_sha256')},'schema':'b06-runtime-launch-receipt/6'})
   resolution=produce(raw,c,p,inventory,receipt,signer.public,expected,fork_command=fork,transient_copies=tc,application_copies=ac)
   self.assertEqual(resolution['schema'],'b06-resolved-runtime/6')
   self.assertFalse(assemble(inventory,resolution,launch_key=signer.public,expected_launch=expected,transient_copies=tc,application_copies=ac)['native_admission'])
   if shape=='r7-folder-absent':
    selected=next(b for b in observed['bundles'] if b['id']==1)
    self.assertEqual(selected['runtime_selection']['absent_dev_roots'],['target/test-classes'])
    tampered=copy.deepcopy(observed)
    next(b for b in tampered['bundles'] if b['id']==1)['runtime_selection']['absent_dev_roots']=['target/classes']
    with self.assertRaisesRegex(ValueError,'absent-dev-has-content'):cap.validate_capture(tampered,ac)
   with self.assertRaisesRegex(ValueError,'already-exists'):cap.capture_application(obs,out,resolve=resolve)
   # A changed raw agent record is detected by independent replay even if the envelope is re-signed.
   altered=copy.deepcopy(observed);altered['agent_observation']['bundles'][1]['state']=2
   with self.assertRaisesRegex(ValueError,'agent-observation-changed'):cap.validate_capture(altered,ac)
 def test_full_worker_producer_replay_r5b_jar_shape(self):self.full('r5b-jar')
 def test_full_worker_producer_replay_r7_folder_shape(self):self.full('r7-folder')

 def test_full_worker_replay_optional_dev_absence(self):self.full('r7-folder-absent')
