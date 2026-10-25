"""CI-only J5 proof refusal cases."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from tools.carddemo_account_render_proof import SCOPE,JAVA,CLASSES,check_scope,evaluate

ROOT=Path(__file__).resolve().parents[1]


class RenderProofTests(unittest.TestCase):
    def test_complete_inventory_and_scope_cannot_be_reduced(self):
        self.assertEqual(88,check_scope(ROOT)['paragraphs'])
        original=json.loads((ROOT/SCOPE).read_bytes())
        for defect in ('class','annotation','paragraph','hash','retirement','whole-screen','independent'):
            scope=copy.deepcopy(original)
            if defect=='class':scope['required_mutation_classes'].pop()
            elif defect=='annotation':scope['annotations'].pop()
            elif defect=='paragraph':scope['source']['paragraphs'].pop()
            elif defect=='hash':scope['source']['sha256']='0'*64
            elif defect=='retirement':scope['newly_retired_paragraphs'].pop()
            elif defect=='whole-screen':scope['whole_screen_idiomatic']=True
            else:scope['independent_full_slice_required']=False
            with self.subTest(defect=defect),self.assertRaises(ValueError):check_scope(ROOT,scope)

    def test_empty_missing_and_non_killed_mutants_cannot_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'mutations.xml'
            self.assertFalse(evaluate(path)['passed'])
            for status in ('SURVIVED','TIMED_OUT','NO_COVERAGE','RUN_ERROR','MEMORY_ERROR'):
                rows=[]
                for name in CLASSES:
                    for i in range(10):
                        state='KILLED' if i<8 else status
                        rows.append(f'<mutation status="{state}"><mutatedClass>ai.lightyear.carddemo.{name}$Nested</mutatedClass></mutation>')
                path.write_text('<mutations>'+''.join(rows)+'</mutations>')
                self.assertFalse(evaluate(path)['passed'],status)
            path.write_text('<mutations><mutation status="KILLED"><mutatedClass>ai.lightyear.carddemo.AccountRenderRules</mutatedClass></mutation></mutations>')
            self.assertFalse(evaluate(path)['passed'])
            path.write_text('<mutations>'+''.join(f'<mutation status="KILLED"><mutatedClass>ai.lightyear.carddemo.{name}</mutatedClass></mutation>' for name in CLASSES)+'</mutations>')
            self.assertTrue(evaluate(path)['passed'])

    def test_production_routes_dispatch_and_pom_cannot_be_removed(self):
        scope=json.loads((ROOT/SCOPE).read_bytes())
        paths=[SCOPE,scope['source']['path'],JAVA+'AccountRenderRules.java',
               JAVA+'AccountRenderModel.java',JAVA+'AccountUpdateService.java',JAVA+'SourceEdits.java',
               'factory/carddemo-web/service/pom.xml','factory/carddemo-web/service/render-proof.pom.xml']
        originals={p:(ROOT/p).read_text() for p in paths}
        defects=[(JAVA+'AccountRenderModel.java','AccountMapModel.retire(original)','original'),
                 (JAVA+'AccountRenderModel.java','paragraphs.remove(rule.getKey())','paragraphs.get(rule.getKey())'),
                 (JAVA+'AccountUpdateService.java','AccountRenderModel.retire(','AccountMapModel.retire('),
                 (JAVA+'SourceEdits.java','AccountRenderState.bind(this)','AccountMapState.bind(this)'),
                 ('factory/carddemo-web/service/render-proof.pom.xml','<mutationThreshold>90','<mutationThreshold>80')]
        for method in ('values','initial','original','updated','information','attributes','protect','unprotect','informationAttributes'):
            defects.append((JAVA+'SourceEdits.java','AccountRenderRules.'+method+'(state)','AccountRenderRules.initial(state)' if method!='initial' else 'AccountRenderRules.values(state)'))
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for path,text in originals.items():
                target=root/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text)
            self.assertEqual(88,check_scope(root)['paragraphs'])
            for path,old,new in defects:
                self.assertIn(old,originals[path])
                (root/path).write_text(originals[path].replace(old,new))
                with self.subTest(path=path,removed=old),self.assertRaises(ValueError):check_scope(root)
                (root/path).write_text(originals[path])
