import copy,json,tempfile,unittest,hashlib
from pathlib import Path
from tools.b06_image_artifacts import build_once as b,runtime_capture as capture

class BuildOnceReplayTests(unittest.TestCase):
 def test_replay_actual_capture_shape_and_reject_wrong_class_source(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);app=root/'application';out=root/'results';app.mkdir();out.mkdir()
   devpath=b.TEST_ROOT+'/target/work/dev.properties';devraw=b'org.idempiere.test=target/classes\n'
   for n,raw in {'META-INF/MANIFEST.MF':b'Manifest-Version: 1.0\r\nBundle-SymbolicName: org.idempiere.test\r\nBundle-Version: 1.0.0\r\nBundle-ClassPath: .\r\n\r\n',b.TEST_ENTRY:b'class-two','target/opaque.jar':b'unchanged archive','target/work/dev.properties':devraw}.items():
    f=app/n;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(raw)
   fork=['/opt/java/openjdk/bin/java','-jar','/root/.m2/launcher.jar','-testproperties',b.TEST_ROOT+'/target/surefire.properties']
   obs=dict(schema='b06-runtime-launch-observation/5',install_area='file:/application/test/',java_tmpdir='/results/java-tmp',osgi_dev='file:'+devpath,
    fork_command=fork,loaded_bundle_classes=[],bundles=[dict(id=1,state=32,location='file:'+b.TEST_ROOT+'/',symbolic_name='org.idempiere.test',version='1.0.0',eclipse_source_bundle=False,preserved_copy=None)])
   raw=json.dumps(obs).encode();(out/'closure-observation.json').write_bytes(raw)
   (out/'closure-complete.json').write_text(json.dumps(dict(status='complete',observation_sha256=hashlib.sha256(raw).hexdigest())))
   (out/'runtime-catalogue.tsv').write_text(b.TEST_CLASS+'\tfile:'+b.TEST_ROOT+'/target/classes/\n')
   resolve=lambda name:app if name.rstrip('/')==b.TEST_ROOT else app/name.removeprefix(b.TEST_ROOT+'/')
   capture.capture_application(obs,out,resolve=resolve)
   (out/'effective-config.ini').write_bytes(b'config');(out/'effective-surefire.properties').write_bytes(b'props');(out/'measured-inventory.json').write_text('{"artifacts":[]}')
   expected=b.descriptor(b'class-two');maps=b.application_maps(out)
   manifest=b.seal(dict(base_applications=maps,artifacts={},source_files={},variants={'2':{'class':expected}},consumer_argv=fork,
    base_config_sha256=hashlib.sha256(b'config').hexdigest(),testproperties_path='/props',sealed_files={'/props':b.descriptor(b'props'),devpath:b.descriptor(devraw)}))
   record=dict(schema='b06-practice-class-observation/1',name=b.TEST_CLASS,origin='file:'+b.TEST_ROOT+'/target/classes/',loader='loader@1',**expected)
   (out/'per-run-class.json').write_text(json.dumps(record))
   for name in ('before.json','after.json'):(out/name).write_text(json.dumps(dict(manifest_sha256=manifest['content_sha256'],variant='2',verified=True)))
   self.assertTrue(b.verify_consumer(manifest,out,'2')['passed'])
   for changes in ({'origin':'jar:file:/application/test.jar!/'},{'sha256':'0'*64},{'loader':'bootstrap'}):
    (out/'per-run-class.json').write_text(json.dumps({**record,**changes}))
    with self.subTest(changes=changes),self.assertRaises(ValueError):b.verify_consumer(manifest,out,'2')
   (out/'per-run-class.json').write_text(json.dumps(record));(out/'per-run-class-error.json').write_text('{}')
   with self.assertRaisesRegex(ValueError,'observer-error'):b.verify_consumer(manifest,out,'2')

if __name__=='__main__':unittest.main()
