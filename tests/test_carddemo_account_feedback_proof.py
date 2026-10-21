"""CI-only J1 proof refusal cases."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from tools.carddemo_account_feedback_proof import SCOPE,CLASSES,check_scope,evaluate

ROOT=Path(__file__).resolve().parents[1]


class FeedbackProofTests(unittest.TestCase):
    def test_complete_inventory_and_scope_cannot_be_reduced(self):
        self.assertEqual(88,check_scope(ROOT)['paragraphs'])
        original=json.loads((ROOT/SCOPE).read_bytes())
        for defect in ('class','annotation','paragraph','hash','retirement','whole-screen','field'):
            scope=copy.deepcopy(original)
            if defect=='class':scope['required_mutation_classes'].pop()
            elif defect=='annotation':scope['annotations']['AccountValidationFeedback'].pop()
            elif defect=='paragraph':scope['source']['paragraphs'].pop()
            elif defect=='hash':scope['source']['sha256']='0'*64
            elif defect=='retirement':scope['newly_retired_paragraphs']=['1215-EDIT-MANDATORY']
            elif defect=='whole-screen':scope['whole_screen_idiomatic']=True
            else:scope['field_storage']['MESSAGE']='OTHER'
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
            path.write_text('<mutations><mutation status="KILLED"><mutatedClass>ai.lightyear.carddemo.AccountValidationFeedback</mutatedClass></mutation></mutations>')
            self.assertFalse(evaluate(path)['passed'])
            path.write_text('<mutations>'+''.join(f'<mutation status="KILLED"><mutatedClass>ai.lightyear.carddemo.{name}</mutatedClass></mutation>' for name in CLASSES)+'</mutations>')
            self.assertTrue(evaluate(path)['passed'])
