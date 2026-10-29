"""CI-only, keyless real-file replacement controls and retained-evidence negatives."""
import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lightyear_factory.contracts import ContractError
from tools.ci import p5_workspace_replacement as probe


class WorkspaceReplacementTests(unittest.TestCase):
    def test_real_replacement_preserves_size_time_but_refuses_new_inode(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')
        rows = probe.observe()
        self.assertEqual([r['case'] for r in rows], list(probe.CASES))
        for row in rows:
            self.assertTrue(probe.validate(row))
            self.assertFalse(row['production_controller_receipt'])
        self.assertEqual(rows[1]['identity_before'][2:4], rows[1]['identity_after'][2:4])
        self.assertNotEqual(rows[1]['identity_before'][1], rows[1]['identity_after'][1])
        self.assertEqual(rows[1]['file_scan_sha256'], [])

    def test_evidence_corruption_and_wrong_refusal_do_not_pass(self):
        row = probe.observe()[1]
        variants = [dict(outcome='unrelated-error'), dict(replacements=0),
                    dict(identity_after=row['identity_before']), dict(read_closed_before_final_stat=False),
                    dict(file_scan_sha256=[row['read_sha256']]), dict(production_controller_receipt=True),
                    dict(source_after_sha256='0'*64), dict(after_hex=row['before_hex'])]
        for mutation in variants:
            bad = copy.deepcopy(row); bad.update(mutation)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): probe.validate(bad)

    def test_unrelated_scan_failure_is_not_replacement_evidence(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(probe.IsolatedWorkspace, 'scan_contents', side_effect=ContractError('unrelated')):
            with self.assertRaisesRegex(ValueError, 'p5-workspace-replacement-invalid'):
                probe.observe_case(Path(temp)/'negative', 'path-replacement')

    def test_non_ci_refuses_before_fixture_creation(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'GITHUB_ACTIONS': 'false'}):
            target = Path(temp)/'must-not-exist'
            with self.assertRaisesRegex(ValueError, 'ci-only'): probe.observe_case(target, 'clean')
            self.assertFalse(target.exists())

    def controller_row(self, case):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')
        with tempfile.TemporaryDirectory(prefix='p5-controller-replacement-test-') as temp:
            return probe.observe_controller_case(Path(temp)/case, case)

    def test_native_controller_replacement_refuses_before_builder(self):
        with patch('lightyear_factory.gates.GateRunner.run', side_effect=AssertionError('no gate execution in component control')):
            rows = [self.controller_row(case) for case in probe.CASES]
        for row in rows:
            self.assertTrue(probe.validate_controller_case(row))
            self.assertFalse(row['production_controller_receipt'])
            self.assertFalse(row['signing'])
            self.assertEqual(row['real_model_calls'], 0)
        self.assertEqual(rows[0]['scripted_roles'], ['planner', 'builder'])
        self.assertEqual(rows[1]['scripted_roles'], ['planner'])
        self.assertEqual(rows[1]['controller_error'], 'factory-isolation-run-refused')
        self.assertEqual(rows[1]['identity_before'][2:4], rows[1]['identity_after'][2:4])
        self.assertNotEqual(rows[1]['identity_before'][1], rows[1]['identity_after'][1])

    def test_controller_replacement_self_rehashed_false_receipt_and_bindings_refuse(self):
        import hashlib
        import json
        from lightyear_factory.contracts import canonical_hash
        row = self.controller_row('path-replacement')
        variants = []
        bad = copy.deepcopy(row)
        doc = json.loads(bad['receipt']['utf8']); doc['status'] = 'passed'
        doc['content_sha256'] = canonical_hash(doc, {'content_sha256'})
        raw = json.dumps(doc).encode()
        bad['receipt'] = dict(utf8=raw.decode(), sha256=hashlib.sha256(raw).hexdigest())
        variants.append(bad)
        for mutation in (dict(scripted_roles=['planner', 'builder']),
                         dict(controller_error='unrelated-refusal'), dict(production_controller_receipt=True),
                         dict(work_order_sha256='0'*64), dict(run_id='different-controller-run'),
                         dict(closed_before_final_stat=False), dict(artifacts=[]), dict(gates_executed=True)):
            bad = copy.deepcopy(row); bad.update(mutation); variants.append(bad)
        for bad in variants:
            with self.assertRaisesRegex(ValueError, 'p5-controller-replacement-invalid'):
                probe.validate_controller_case(bad)

    def test_controller_replacement_unrelated_scan_failure_does_not_pass(self):
        with tempfile.TemporaryDirectory() as temp, \
                patch.object(probe.IsolatedWorkspace, 'scan_contents', side_effect=ContractError('unrelated')):
            with self.assertRaisesRegex(ValueError, 'p5-controller-replacement-invalid'):
                probe.observe_controller_case(Path(temp)/'negative', 'path-replacement')

    def test_controller_replacement_non_ci_refuses_before_creation(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'GITHUB_ACTIONS': 'false'}):
            target = Path(temp)/'must-not-exist'
            with self.assertRaisesRegex(ValueError, 'p5-controller-replacement-ci-only'):
                probe.observe_controller_case(target, 'clean')
            self.assertFalse(target.exists())

    def test_controller_receipt_tail_requires_exact_scans_and_summary(self):
        import hashlib
        import json
        from lightyear_factory.contracts import canonical_hash
        row = self.controller_row('clean')
        variants = []
        for mutation in ('missing', 'extra', 'wrong-digest', 'wrong-kind'):
            bad = copy.deepcopy(row)
            events = [json.loads(line) for line in bad['ledger']['utf8'].splitlines()]
            if mutation == 'missing': events.pop()
            elif mutation == 'extra': events.append(copy.deepcopy(events[-1]))
            elif mutation == 'wrong-digest': events[-1]['payload']['scanned'][0]['sha256'] = '0'*64
            else: events[-1]['kind'] = 'unrelated'
            previous = None
            for index, event in enumerate(events, 1):
                event['sequence'] = index; event['previous_sha256'] = previous
                event['event_sha256'] = canonical_hash(event, {'event_sha256'})
                previous = event['event_sha256']
            raw = ''.join(json.dumps(event)+'\n' for event in events).encode()
            bad['ledger'] = dict(utf8=raw.decode(), sha256=hashlib.sha256(raw).hexdigest())
            variants.append(bad)
        bad = copy.deepcopy(row)
        summary = json.loads(bad['summary']['utf8']); summary['receipt_sha256'] = '0'*64
        raw = json.dumps(summary).encode()
        bad['summary'] = dict(utf8=raw.decode(), sha256=hashlib.sha256(raw).hexdigest())
        variants.append(bad)
        for bad in variants:
            with self.assertRaisesRegex(ValueError, 'p5-controller-replacement-invalid'):
                probe.validate_controller_case(bad)

    def test_baseline_gate_without_container_still_refuses_before_builder(self):
        from lightyear_factory.gates import GateRunner
        real_init = GateRunner.__init__
        refusals = []
        def checked_init(runner, *args, **kwargs):
            try:
                return real_init(runner, *args, **kwargs)
            except ContractError as error:
                refusals.append(str(error))
                raise
        with tempfile.TemporaryDirectory() as temp, patch.object(GateRunner, '__init__', checked_init):
            with self.assertRaisesRegex(ValueError, 'p5-controller-replacement-invalid'):
                probe.observe_controller_case(Path(temp)/'negative', 'clean', baseline_first=True)
        self.assertEqual(refusals, ['isolation-breach: candidate-container-required'])
