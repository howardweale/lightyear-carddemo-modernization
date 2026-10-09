import io,unittest,zipfile
from tools.b06_image_artifacts.observer_manifest import bundle_classes,headers
from test_ms94_b06_classfile import fixture

def jar(entries):
 out=io.BytesIO()
 with zipfile.ZipFile(out,'w') as z:
  for n,b in entries.items():z.writestr(n,b)
 return out.getvalue()
def bundle(cp='.',extra=None):
 raw=fixture()[0]
 return jar({'META-INF/MANIFEST.MF':('Manifest-Version: 1.0\r\nBundle-ClassPath: '+cp+'\r\n\r\n').encode(),**(extra or {'test/Fixture.class':raw})})
class AssemblyTests(unittest.TestCase):
 def run_bundle(self,raw,**kw):
  return bundle_classes(raw,origin='/application/bundle',folder=False,bundle_id=7,config_path='/config',**kw)
 def test_exact_jar_origin_and_bytes(self):
  raw=bundle();rows,shadow=self.run_bundle(raw)
  self.assertEqual(len(rows),1);self.assertEqual(shadow,[])
  self.assertEqual(rows[0]['artifact'],raw);self.assertEqual(rows[0]['members'],['test/Fixture.class'])
  self.assertEqual(rows[0]['code_source'],'/application/bundle')
 def test_nested_cache_code_source_is_not_outer_jar(self):
  raw=bundle('lib/x.jar',{'lib/x.jar':jar({'test/Fixture.class':fixture()[0]})})
  rows,_=self.run_bundle(raw)
  self.assertEqual(rows[0]['code_source'],'/config/org.eclipse.osgi/7/0/.cp/lib/x.jar')
  self.assertEqual(rows[0]['members'],['lib/x.jar','test/Fixture.class'])
 def test_folder_dev_and_nested_jar_origins(self):
  raw=bundle('.,lib/x.jar',{'out/test/Fixture.class':fixture()[0],
      'lib/x.jar':jar({'test/Fixture.class':fixture()[0]})})
  rows,sh=bundle_classes(raw,origin='/application/bundle',folder=True,bundle_id=7,
      config_path='/config',dev=['/application/bundle/out'])
  self.assertEqual(len(rows),1);self.assertEqual(len(sh),1)
  self.assertEqual(rows[0]['origin'],'/application/bundle/out/test/Fixture.class')
  self.assertEqual(rows[0]['code_source'],'/application/bundle/out/')
  self.assertEqual(rows[0]['members'],[])
 def test_root_does_not_admit_live_target_work_class(self):
  rows,_=self.run_bundle(bundle(extra={'target/work/test/Fixture.class':fixture()[0]}))
  self.assertEqual(rows,[])
 def test_missing_nested_jar_refuses(self):
  with self.assertRaisesRegex(ValueError,'nested-jar-missing'):self.run_bundle(bundle('missing.jar'))
 def test_external_dev_escape_refuses(self):
  with self.assertRaisesRegex(ValueError,'external-dev'):
   bundle_classes(bundle(),origin='/app',folder=True,bundle_id=1,config_path='/c',dev=['/outside'])
 def test_shadowed_class_is_recorded(self):
  raw=bundle('.,lib/x.jar',{'test/Fixture.class':fixture()[0],
      'lib/x.jar':jar({'test/Fixture.class':fixture()[0]+b'other'})})
  rows,sh=self.run_bundle(raw);self.assertEqual(len(rows),1);self.assertEqual(len(sh),1)
  self.assertEqual(rows[0]['bytes'],fixture()[0])
 def test_only_declared_multi_release_version_is_used(self):
  raw=jar({'META-INF/MANIFEST.MF':b'Multi-Release: true\r\n\r\n',
      'test/Fixture.class':fixture()[0],
      'META-INF/versions/21/test/Fixture.class':fixture()[0]+b'21',
      'META-INF/versions/22/test/Fixture.class':fixture()[0]+b'22'})
  rows,_=self.run_bundle(raw);self.assertEqual(rows[0]['bytes'],fixture()[0]+b'21')
 def test_unknown_complex_classpath_refuses(self):
  with self.assertRaisesRegex(ValueError,'complex-classpath'):self.run_bundle(bundle('".,lib/x.jar"'))
 def test_manifest_header_duplicate_refuses(self):
  with self.assertRaisesRegex(ValueError,'duplicate-header'):headers(b'Bundle-ClassPath: .\nBundle-ClassPath: lib/a.jar\n\n')
if __name__=='__main__':unittest.main()
