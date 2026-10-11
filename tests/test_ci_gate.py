import unittest
try:
    import yaml
except ImportError:
    raise unittest.SkipTest('Required CI installs pinned PyYAML; optional in general suites')
from tools.ci_gate import selected,evaluate,expected_workflows
class GateTests(unittest.TestCase):
    def test_docs_skip_heavy_but_json_does_not(self):
        e=expected_workflows(['docs/factory/review.md'])
        self.assertNotIn('.github/workflows/verify.yml',e)
        self.assertNotIn('.github/workflows/control-tower-decisions.yml',e)
        self.assertIn('.github/workflows/verify.yml',expected_workflows(['docs/receipt.json']))
    def test_shared_inputs_trigger_both(self):
        for p in ['src/lightyear_mainframe/records.py','src/lightyear_mainframe/zos_bindings.py','tests/mainframe/fixtures/x','spec/mainframe/x','tools/check_legacy_twin.py']:
            for w in ['factory-legacy-twin','factory-reconciliation']:
                self.assertIn(f'.github/workflows/{w}.yml',expected_workflows([p]),p)
    def test_only_final_head_completed_success_passes(self):
        r=dict(id=1,path='x',head_sha='new',event='pull_request',pull_requests=[{'number':9}],status='completed',conclusion='success')
        self.assertEqual(evaluate({'x'},[r],'new',9),([],[]))
        for c in ['failure','cancelled','skipped','neutral','timed_out']:
            self.assertEqual(evaluate({'x'},[dict(r,conclusion=c)],'new',9),(['x'],[]))
        for change in [{'head_sha':'old'},{'status':'in_progress'},{'pull_requests':[{'number':8}]}]:
            self.assertEqual(evaluate({'x'},[dict(r,**change)],'new',9),([],['x']))
        self.assertEqual(evaluate({'x'},[],'new',9),([],['x']))
        self.assertEqual(evaluate({'x'},[r,dict(r,id=2,conclusion='failure')],'new',9),(['x'],[]))
    def test_root_markdown_and_negative_paths(self):
        self.assertFalse(selected({'on':{'pull_request':{'paths-ignore':['**/*.md']}}},['README.md']))
        self.assertFalse(selected({'on':{'pull_request':{'paths':['src/**','!src/excluded/**']}}},['src/excluded/a']))
