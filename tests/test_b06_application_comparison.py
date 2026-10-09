import tempfile,unittest
from pathlib import Path
from tools.b06_image_artifacts.application_comparison import compare,loaded
class ApplicationComparisonTests(unittest.TestCase):
 def test_empty_is_missing_not_equivalent_evidence(self):
  r=compare({},{});self.assertFalse(r['evidence_present']);self.assertEqual(r['compared'],0)
 def test_changed_added_and_missing_are_explicit(self):
  r=compare({'same':'a','changed':'b','removed':'c'},{'same':'a','changed':'d','added':'e'})
  self.assertEqual((r['compared'],r['identical'],r['different']),(2,1,1))
  self.assertEqual(r['only_previous'],['removed']);self.assertEqual(r['only_current'],['added'])
 def test_catalogue_does_not_trust_unverified_blob(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);(root/'loaded').mkdir();h='a'*64
   (root/'loaded/loaded.tsv').write_text('A\t'+h+'\tfile:/application/a.jar\tloader\n')
   (root/'loaded'/(h+'.class')).write_bytes(b'wrong')
   with self.assertRaisesRegex(ValueError,'saved-loaded-class-hash'):loaded(root)
