"""Unit retention boundaries only; synthetic provider grants no admission."""
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from lightyear_factory.contracts import canonical_hash
from lightyear_execution.contracts import ExecutionContractError
from lightyear_execution.human_drill_dispatch import _retain_controller_provenance


class DispatchProvenanceRefusalTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')

    def test_success_retains_exact_existing_provenance_and_no_refusal(self):
        result = dict(schema='public-test', controller_origin_verified=False)
        provider = SimpleNamespace(provenance=lambda receipt: result)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.assertIs(_retain_controller_provenance(root, root/'run', provider, {}), result)
            expected = (json.dumps(result, sort_keys=True, separators=(',', ':'))+'\n').encode()
            self.assertEqual((root/'controller-output-provenance.json').read_bytes(), expected)
            self.assertFalse((root/'controller-output-provenance-refusal.json').exists())

    def test_closed_context_preserves_original_receipt_and_reraises_without_authority(self):
        refusal = ExecutionContractError('human-drill-fresh-process-context-required')
        def failed(receipt):
            raise refusal
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); run = root/'run'; run.mkdir()
            original = b'{"status":"blocked","public_fixture":true}\n'
            path = run/'receipt.json'; path.write_bytes(original)
            with self.assertRaises(ExecutionContractError) as caught:
                _retain_controller_provenance(root, run, SimpleNamespace(provenance=failed), {})
            self.assertIs(caught.exception, refusal)
            self.assertEqual(path.read_bytes(), original)
            value = json.loads((root/'controller-output-provenance-refusal.json').read_bytes())
            self.assertEqual(value['status'], 'refused')
            self.assertEqual(value['receipt_file_sha256'], hashlib.sha256(original).hexdigest())
            self.assertEqual(value['content_sha256'], canonical_hash(value, {'content_sha256'}))
            for field in ('controller_origin_verified','execution_authorized',
                          'production_qualified','qualifies_for_factory_receipt','resume_allowed'):
                self.assertIs(value[field], False)
            self.assertFalse((root/'controller-output-provenance.json').exists())
            self.assertFalse((root/'dispatch-summary.json').exists())
            self.assertNotIn(str(refusal), json.dumps(value))

    def test_existing_refusal_evidence_is_never_overwritten(self):
        def failed(receipt):
            raise ExecutionContractError('closed')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); run = root/'run'; run.mkdir()
            (run/'receipt.json').write_bytes(b'{}\n')
            path = root/'controller-output-provenance-refusal.json'
            path.write_bytes(b'original-public-evidence\n')
            with self.assertRaises(FileExistsError):
                _retain_controller_provenance(root, run, SimpleNamespace(provenance=failed), {})
            self.assertEqual(path.read_bytes(), b'original-public-evidence\n')
            self.assertEqual((run/'receipt.json').read_bytes(), b'{}\n')

    def terminal_unit_fixture(self, root):
        from lightyear_execution.public_drill_runtime import PublicDrillProvider
        run = root/'run'; run.mkdir()
        receipt = dict(status='blocked', public_unit_fixture=True)
        receipt['content_sha256'] = canonical_hash(receipt)
        original = (json.dumps(receipt, sort_keys=True)+'\n').encode()
        (run/'receipt.json').write_bytes(original)
        value = dict(schema='factory-human-drill-terminal-lineage/1', status='retained-blocked-lineage',
            same_process_controller_lineage_verified=True, receipt_sha256=receipt['content_sha256'],
            receipt_file_sha256=hashlib.sha256(original).hexdigest(), controller_origin_verified=False,
            execution_authorized=False, resume_allowed=False, retry_allowed=False,
            production_qualified=False, qualifies_for_factory_receipt=False,
            accounting_semantics_verified=False, expected_refusal_verified=False)
        value['content_sha256'] = canonical_hash(value)
        return run, receipt, original, object.__new__(PublicDrillProvider), value

    def test_terminal_diagnostic_keeps_original_refusal_and_links_exact_sidecar_bytes(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run, receipt, original, provider, value = self.terminal_unit_fixture(root)
            error = ExecutionContractError('closed-public-unit-context')
            with patch.object(provider, 'provenance', side_effect=error), \
                    patch.object(provider, 'retained_terminal_lineage', return_value=value) as terminal:
                with self.assertRaises(ExecutionContractError) as caught:
                    _retain_controller_provenance(root, run, provider, receipt)
            self.assertIs(caught.exception, error)
            terminal.assert_called_once_with(receipt)
            raw = (root/'controller-terminal-lineage.json').read_bytes()
            self.assertEqual(json.loads(raw), value)
            refusal = json.loads((root/'controller-output-provenance-refusal.json').read_bytes())
            self.assertEqual(refusal['terminal_lineage_status'], 'retained')
            self.assertEqual(refusal['terminal_lineage_file_sha256'], hashlib.sha256(raw).hexdigest())
            self.assertFalse(refusal['controller_origin_verified'])
            self.assertEqual((run/'receipt.json').read_bytes(), original)
            self.assertFalse((root/'controller-output-provenance.json').exists())

    def test_terminal_validation_failure_does_not_replace_original_refusal(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run, receipt, original, provider, value = self.terminal_unit_fixture(root)
            error = ExecutionContractError('original-public-unit-refusal')
            changed = dict(value, execution_authorized=True)
            changed['content_sha256'] = canonical_hash(changed, {'content_sha256'})
            with patch.object(provider, 'provenance', side_effect=error), \
                    patch.object(provider, 'retained_terminal_lineage', return_value=changed):
                with self.assertRaises(ExecutionContractError) as caught:
                    _retain_controller_provenance(root, run, provider, receipt)
            self.assertIs(caught.exception, error)
            refusal = json.loads((root/'controller-output-provenance-refusal.json').read_bytes())
            self.assertEqual(refusal['terminal_lineage_status'], 'unavailable')
            self.assertIsNone(refusal['terminal_lineage_file_sha256'])
            self.assertFalse((root/'controller-terminal-lineage.json').exists())
            self.assertEqual((run/'receipt.json').read_bytes(), original)

    def test_existing_terminal_sidecar_is_never_overwritten_or_reused(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run, receipt, original, provider, value = self.terminal_unit_fixture(root)
            path = root/'controller-terminal-lineage.json'; path.write_bytes(b'old-public-unit-evidence\n')
            error = ExecutionContractError('original-public-unit-refusal')
            with patch.object(provider, 'provenance', side_effect=error), \
                    patch.object(provider, 'retained_terminal_lineage', return_value=value):
                with self.assertRaises(ExecutionContractError) as caught:
                    _retain_controller_provenance(root, run, provider, receipt)
            self.assertIs(caught.exception, error)
            self.assertEqual(path.read_bytes(), b'old-public-unit-evidence\n')
            refusal = json.loads((root/'controller-output-provenance-refusal.json').read_bytes())
            self.assertEqual(refusal['terminal_lineage_status'], 'unavailable')
            self.assertIsNone(refusal['terminal_lineage_file_sha256'])

    def test_successful_live_provenance_does_not_call_terminal_fallback(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run, receipt, original, provider, value = self.terminal_unit_fixture(root)
            live_result = dict(public_unit_fixture=True, controller_origin_verified=False)
            with patch.object(provider, 'provenance', return_value=live_result), \
                    patch.object(provider, 'retained_terminal_lineage', side_effect=AssertionError('unexpected fallback')) as terminal:
                self.assertIs(_retain_controller_provenance(root, run, provider, receipt), live_result)
            terminal.assert_not_called()
            expected = (json.dumps(live_result, sort_keys=True, separators=(',', ':'))+'\n').encode()
            self.assertEqual((root/'controller-output-provenance.json').read_bytes(), expected)
            self.assertFalse((root/'controller-output-provenance-refusal.json').exists())
            self.assertFalse((root/'controller-terminal-lineage.json').exists())
