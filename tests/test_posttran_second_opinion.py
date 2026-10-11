import unittest
from lightyear_factory.posttran_second_opinion import prepare,require_inputs,require_phase2
class SecondOpinionTests(unittest.TestCase):
    def test_allowlist_and_no_call_plan(self):
        p=prepare();require_inputs(p['inputs'])
        self.assertFalse(p['execution_authorized']);self.assertEqual(0,p['model_calls_made'])
        self.assertFalse(any('/after/' in x or 'review-sheet' in x for x in p['inputs']))
        self.assertTrue(any('/before/' in x for x in p['inputs']))
        with self.assertRaises(ValueError):require_inputs({**p['inputs'],'docs/factory/posttran-human-review-sheet.json':'fake'})
        self.assertEqual(3,p['phases']['1']['model_calls']);self.assertEqual(2,p['phases']['2']['model_calls'])
    def test_unresolved_and_twin_defects_block_normal_loop(self):
        for decision in (None,'twin-defect'):
            with self.assertRaises(ValueError):require_phase2([dict(adjudication=decision,signed_review=True)])
