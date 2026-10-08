"""Offline inventory tests; no native origin or qualification claim."""
import hashlib,io,tempfile,unittest,zipfile,warnings
from pathlib import Path
from tools.b06_image_artifacts.native_catalogue import archive_classes,read_class,summarize,select_exact
from test_ms94_b06_classfile import fixture

class NativeCatalogueTests(unittest.TestCase):
 def jar(self,root,name,entries):
  p=root/name
  with warnings.catch_warnings():
   warnings.simplefilter('ignore')
   with zipfile.ZipFile(p,'w') as z:
    for n,b in entries:z.writestr(n,b)
  return p,hashlib.sha256(p.read_bytes()).hexdigest()
 def test_nested_and_multi_release_definitions_are_not_silently_selected(self):
  raw,_=fixture()
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);inner,ih=self.jar(root,'inner.jar',[('test/Fixture.class',raw)])
   p,h=self.jar(root,'outer.jar',[('lib/inner.jar',inner.read_bytes()),('META-INF/versions/21/test/Fixture.class',raw+b'x')])
   rows=archive_classes(p,h,'/root/.m2/outer.jar')
   self.assertEqual(len(rows),2);self.assertFalse(rows[0]['multi_release']);self.assertTrue(rows[1]['multi_release'])
   s=summarize(rows);self.assertEqual(s['differing_definition_names'],1);self.assertFalse(s['native_admission'])
   row=select_exact(rows,'test.Fixture',artifact_sha256=h,members=['lib/inner.jar','test/Fixture.class'])
   self.assertEqual(read_class(row,p),raw)
   with self.assertRaisesRegex(ValueError,'exact-origin'):select_exact(rows,'test.Fixture',artifact_sha256=h,members=['test/Fixture.class'])
 def test_hash_tampering_refuses(self):
  with tempfile.TemporaryDirectory() as d:
   p,h=self.jar(Path(d),'a.jar',[('test/Fixture.class',fixture()[0])])
   rows=archive_classes(p,h,'x');p.write_bytes(b'changed')
   with self.assertRaisesRegex(ValueError,'archive-hash'):read_class(rows[0],p)
 def test_duplicate_names_refuse(self):
  with tempfile.TemporaryDirectory() as d:
   p,h=self.jar(Path(d),'a.jar',[('test/Fixture.class',fixture()[0])]*2)
   with self.assertRaisesRegex(ValueError,'duplicate'):archive_classes(p,h,'x')
 def test_parent_escape_refuses(self):
  with tempfile.TemporaryDirectory() as d:
   p,h=self.jar(Path(d),'a.jar',[('../test/Fixture.class',fixture()[0])])
   with self.assertRaisesRegex(ValueError,'bundle-view-path'):archive_classes(p,h,'x')
 def test_decompression_bound_refuses(self):
  with tempfile.TemporaryDirectory() as d:
   p,h=self.jar(Path(d),'a.jar',[('test/Fixture.class',fixture()[0])])
   with self.assertRaisesRegex(ValueError,'entry-bound'):archive_classes(p,h,'x',limit=2)
