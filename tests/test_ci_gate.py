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
    def test_new_attempt_supersedes_failed_completed_snapshot(self):
        failed=dict(id=10,path='x',head_sha='h',event='pull_request',pull_requests=[{'number':1}],status='completed',conclusion='failure',run_attempt=1)
        rerunning=dict(failed,status='in_progress',conclusion=None,run_attempt=2)
        for runs in ([failed,rerunning],[rerunning,failed]):
            self.assertEqual(([],['x']),evaluate({'x'},runs,'h',1))
        self.assertEqual(([],[]),evaluate({'x'},[failed,dict(rerunning,status='completed',conclusion='success')],'h',1))

    def test_root_markdown_and_negative_paths(self):
        self.assertFalse(selected({'on':{'pull_request':{'paths-ignore':['**/*.md']}}},['README.md']))
        self.assertFalse(selected({'on':{'pull_request':{'paths':['src/**','!src/excluded/**']}}},['src/excluded/a']))


class ReviewPathFilterTests(unittest.TestCase):
    def test_data_readiness_and_b06_powershell_changes_select_pr_and_push(self):
        from pathlib import Path
        import yaml
        from tools.ci_gate import selected
        root=Path(__file__).resolve().parents[1]
        cases={
            'carddemo-data.yml':['src/lightyear_readiness/ims_qualification.py','readiness/ims-expiry/conformance/cases.json'],
            'b06-provenance-offline.yml':['tools/ms94_b06_pinned_exec.ps1','tools/inventory_b06_oct13_evidence.ps1'],
        }
        for name,paths in cases.items():
            config=yaml.load((root/'.github/workflows'/name).read_text(),Loader=yaml.BaseLoader)
            self.assertIn('main',config['on']['push']['branches'])
            for path in paths:
                with self.subTest(workflow=name,path=path):
                    self.assertTrue(selected(config,[path]))
                    push={'on':{'pull_request':config['on']['push']}}
                    self.assertTrue(selected(push,[path]))
        b06=(root/'.github/workflows/b06-provenance-offline.yml').read_text()
        self.assertIn('test_ms94_b06_*.py',b06)
