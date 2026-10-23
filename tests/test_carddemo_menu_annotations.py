"""CI-only exact menu annotation binding refusals."""
import copy,json,tempfile,unittest
from pathlib import Path
from tools.carddemo_menu_annotations import SCOPE,check_scope
ROOT=Path(__file__).resolve().parents[1]
class MenuAnnotationTests(unittest.TestCase):
    def test_exact_seven_annotations_and_scoped_claims(self):
        self.assertEqual(7,check_scope(ROOT)['annotations'])
        original=json.loads((ROOT/SCOPE).read_bytes())
        for defect in ('source','inventory','binding','method','span','hash','claim','independent'):
            scope=copy.deepcopy(original)
            if defect=='source':scope['source']['sha256']='0'*64
            elif defect=='inventory':scope['source']['inventory'].pop()
            elif defect=='binding':scope['bindings'].pop()
            elif defect=='method':scope['bindings'][0]['method']='wrong'
            elif defect=='span':scope['bindings'][0]['lines']='75-109'
            elif defect=='hash':scope['bindings'][0]['source_span_sha256']='0'*64
            elif defect=='claim':scope['whole_screen_idiomatic']=True
            else:scope['independent_full_slice_required']=False
            with self.subTest(defect=defect),self.assertRaises(ValueError):check_scope(ROOT,scope)
    def test_java_annotation_and_executable_changes_are_refused(self):
        scope=json.loads((ROOT/SCOPE).read_bytes())
        paths=[SCOPE,scope['source']['path'],*scope['executable_sha256']]
        originals={p:(ROOT/p).read_text() for p in paths}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for path,text in originals.items():
                target=root/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text)
            self.assertEqual(7,check_scope(root)['annotations'])
            for binding in scope['bindings']:
                path=binding['file'];original=originals[path]
                annotation='@CobolSource(program="COMEN01C", paragraph="'+binding['paragraph']+'", lines="'+binding['lines']+'")'
                self.assertIn(annotation,original)
                for changed in (original.replace(annotation,''),original.replace(annotation,annotation+'\n    '+annotation),original+'\n// unexpected change\n'):
                    (root/path).write_text(changed)
                    with self.subTest(paragraph=binding['paragraph']),self.assertRaises(ValueError):check_scope(root)
                (root/path).write_text(original)

    def test_existing_signon_annotation_cannot_be_removed_or_changed(self):
        scope=json.loads((ROOT/SCOPE).read_bytes())
        paths=[SCOPE,scope['source']['path'],*scope['executable_sha256']]
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for path in paths:
                target=root/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((ROOT/path).read_bytes())
            path='factory/carddemo-web/service/src/main/java/ai/lightyear/carddemo/ScreenFrame.java'
            original=(root/path).read_text()
            annotation='    @CobolSource(program="COSGN00C", paragraph="POPULATE-HEADER-INFO", lines="177-208")'
            self.assertIn(annotation,original)
            for bad in (original.replace(annotation+'\n',''),original.replace(annotation,annotation.replace('177-208','177-207'))):
                (root/path).write_text(bad)
                with self.assertRaises(ValueError):check_scope(root)
            (root/path).write_text(original)
            self.assertEqual(7,check_scope(root)['annotations'])

    def test_coordinated_annotation_and_manifest_range_changes_are_refused(self):
        from tools.carddemo_menu_annotations import digest
        scope=json.loads((ROOT/SCOPE).read_bytes())
        paths=[SCOPE,scope['source']['path'],*scope['executable_sha256']]
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for path in paths:
                target=root/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((ROOT/path).read_bytes())
            self.assertEqual(7,check_scope(root)['annotations'])
            lines=(root/scope['source']['path']).read_text().splitlines()
            for index,binding in enumerate(scope['bindings']):
                path=binding['file'];original=(ROOT/path).read_text()
                annotation='@CobolSource(program="COMEN01C", paragraph="'+binding['paragraph']+'", lines="'+binding['lines']+'")'
                first,last=map(int,binding['lines'].split('-'))
                for end in (last-1,last+1):
                    altered=copy.deepcopy(scope);span=str(first)+'-'+str(end)
                    altered['bindings'][index]['lines']=span
                    altered['bindings'][index]['source_span_sha256']=digest('\n'.join(lines[first-1:end])+'\n')
                    (root/path).write_text(original.replace(annotation,annotation.replace(binding['lines'],span)))
                    with self.subTest(paragraph=binding['paragraph'],end=end),self.assertRaisesRegex(ValueError,'menu-range'):
                        check_scope(root,altered)
                (root/path).write_text(original)
            self.assertEqual(7,check_scope(root)['annotations'])
