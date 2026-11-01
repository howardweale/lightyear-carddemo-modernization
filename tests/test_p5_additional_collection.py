"""New evidence runs independently; existing qualifier remains authoritative."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools.ci import p5_drills as drills
from tools.ci import p5_additional_controller_drills as additional


class AdditionalCollectionTests(unittest.TestCase):
    def test_both_collectors_must_pass_and_old_failure_does_not_skip_new_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)/'public'
            for first,second in ((False,True),(True,False),(False,False),(True,True)):
                with self.subTest(first=first,second=second), patch.dict('os.environ',{'GITHUB_ACTIONS':'true'}), patch('sys.argv',['p5_drills','--output',str(output)]), patch.object(drills,'collect',return_value=first) as old, patch.object(additional,'collect',return_value=second) as new:
                    self.assertEqual(drills.main(),0 if first and second else 1)
                    old.assert_called_once_with(Path.cwd(),output)
                    new.assert_called_once_with(Path.cwd(),output/'additional-controller')

    def test_qualification_neither_collects_nor_substitutes_additional_result(self):
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)/'public'
            with patch.dict('os.environ',{'GITHUB_ACTIONS':'true'}), patch('sys.argv',['p5_drills','--output',str(output),'--qualify']), patch.object(drills,'qualify',return_value=False) as qualify, patch.object(drills,'collect') as old, patch.object(additional,'collect') as new:
                self.assertEqual(drills.main(),1)
                qualify.assert_called_once_with(output)
                old.assert_not_called();new.assert_not_called()

    def test_native_workspace_rows_retain_originals_without_qualifying(self):
        import base64
        import hashlib
        import json
        from tools.ci import p5_workspace_replacement as workspace_probe
        repository = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp, \
                patch.object(additional, 'network_case', return_value=dict(expectation_met=True)), \
                patch.object(additional.deadline_probe, 'observe', return_value={}), \
                patch.object(additional, 'deadline_valid', return_value=True):
            output = Path(temp)/'observations'
            self.assertTrue(additional.collect(repository, output))
            report = json.loads((output/'observations.json').read_bytes())
        self.assertEqual([r['id'] for r in report['cases']], [
            'controller-worker-network', 'terminal-deadline-clean', 'terminal-deadline-expired',
            'controller-workspace-clean', 'controller-workspace-path-replacement'])
        self.assertFalse(report['strict_qualified'])
        self.assertFalse(report['production_controller_receipt'])
        self.assertEqual(report['gaps'], [
            'Tower append transport/fallback contract unidentified.',
            'Signed admission, full production receipt and reservation accounting are unproved.'])
        for path in ('tools/ci/p5_workspace_replacement.py', 'tests/test_p5_workspace_replacement.py',
                     'tests/test_p5_additional_collection.py', 'src/lightyear_factory/contracts.py'):
            self.assertEqual(report['source_sha256'][path], hashlib.sha256((repository/path).read_bytes()).hexdigest())
        for row in report['cases'][-2:]:
            self.assertTrue(row['expectation_met'])
            observed = row['observed']
            self.assertTrue(workspace_probe.validate_controller_case(observed))
            root = row['id']+'/runs/'+observed['run_id']+'/'
            originals = report['original_documents']
            for filename, key in [('receipt.json','receipt'), ('summary.json','summary'), ('events.jsonl','ledger')]:
                retained = originals[root+filename]
                raw = base64.b64decode(retained['base64'], validate=True)
                self.assertEqual(raw, observed[key]['utf8'].encode('utf-8'))
                self.assertEqual(hashlib.sha256(raw).hexdigest(), retained['sha256'])
            for artifact in observed['artifacts']:
                raw = base64.b64decode(originals[root+artifact['path']]['base64'], validate=True)
                self.assertEqual(raw, artifact['utf8'].encode('utf-8'))

    def test_workspace_harness_error_fails_collection_without_skipping_next_case(self):
        import json
        from tools.ci import p5_workspace_replacement as workspace_probe
        repository = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp, \
                patch.object(additional, 'network_case', return_value=dict(expectation_met=True)), \
                patch.object(additional.deadline_probe, 'observe', return_value={}), \
                patch.object(additional, 'deadline_valid', return_value=True), \
                patch.object(workspace_probe, 'observe_controller_case', side_effect=ValueError('unrelated fixture error')) as observe:
            output = Path(temp)/'observations'
            self.assertFalse(additional.collect(repository, output))
            report = json.loads((output/'observations.json').read_bytes())
        self.assertEqual(observe.call_count, 2)
        self.assertEqual([call.args[1] for call in observe.call_args_list], list(workspace_probe.CASES))
        self.assertTrue(all(not row['expectation_met'] and 'harness_error' in row for row in report['cases'][-2:]))
        self.assertFalse(report['expectations_met'])
        self.assertFalse(report['strict_qualified'])
