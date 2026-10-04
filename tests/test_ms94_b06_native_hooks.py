"""Host-owned hook tests only; no database/container is started or stopped."""
import copy
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from lightyear_calibration.contracts import canonical, read_json, seal
from tests.test_ms94_a3_entry_v2 import test_signer
from tools.ms94_b06_admission import EvidenceFailure
from tools.ms94_b06_fault_hook import inject, TRIGGER
from tools.ms94_b06_control_sources import j1, CONTROLS

ROOT = Path(__file__).resolve().parents[1]


class NativeHookTests(unittest.TestCase):
    def test_database_hook_exact_owned_id_only_once_and_keeps_intent(self):
        for lane in ('oracle', 'postgresql'):
            for variant in ('valid', 'other-owner', 'wrong-image', 'stop-failed'):
                with self.subTest(lane=lane, variant=variant), tempfile.TemporaryDirectory() as tmp:
                    run = Path(tmp) / 'journey-test'; run.mkdir(); signer = test_signer()
                    plan = seal({'native_fault_hook': {'kind': 'owned-database-stop', 'lane': lane, 'trigger': TRIGGER},
                        'qualification_only': True, 'model_calls': 0,
                        'declaration': {'environment': {'engines': {lane: {'image_digest': 'sha256:expected'}}}}})
                    runner = SimpleNamespace(plan=plan, run=run, owner=run.name)
                    info = {'Name': '/' + run.name + '-operations-1-' + lane, 'Id': 'actual-container-id',
                            'Image': 'sha256:expected', 'State': {'Running': True},
                            'Config': {'Labels': {'lightyear.journey': run.name}}}
                    if variant == 'other-owner': info['Config']['Labels']['lightyear.journey'] = 'unrelated'
                    if variant == 'wrong-image': info['Image'] = 'wrong'
                    stopped = copy.deepcopy(info); stopped['State']['Running'] = False
                    item = seal({'event': {'kind': 'method-entry', 'sequence': 7, 'document': [318, 1],
                        'frames': [{'class': 'org.compiere.util.DB', 'method': 'executeUpdate'},
                                   {'class': 'org.compiere.acct.Doc', 'method': 'post'}]}, 'readback_sha256': 'a'*64})
                    with patch('tools.ms94_b06_fault_hook.inspect', side_effect=[info, stopped]), \
                         patch('tools.ms94_b06_fault_hook.docker') as stop:
                        if variant == 'stop-failed': stop.side_effect = RuntimeError('test transport failure')
                        if variant != 'valid':
                            with self.assertRaises((EvidenceFailure, RuntimeError)): inject(runner, lane, item, signer)
                            if variant != 'stop-failed': stop.assert_not_called()
                            else: self.assertTrue((run / 'database-failure-intent.json').exists())
                        else:
                            value = inject(runner, lane, item, signer)
                            self.assertTrue(value['stopped'])
                            self.assertEqual(inject(runner, lane, item, signer), value)
                            stop.assert_called_once_with('stop', '--time', '2', 'actual-container-id')

    def test_other_lane_nonposting_and_unapproved_hook_never_stop_database(self):
        with tempfile.TemporaryDirectory() as tmp, patch('tools.ms94_b06_fault_hook.docker') as stop:
            runner = SimpleNamespace(plan={'native_fault_hook': {'lane': 'oracle'}}, run=Path(tmp))
            self.assertIsNone(inject(runner, 'postgresql', {'event': {}}, None))
            self.assertIsNone(inject(runner, 'oracle', {'event': {}}, None))
            stop.assert_not_called()

    def test_six_J1_controls_are_deterministic_without_editing_reference(self):
        path = ROOT / 'factory/idempiere/qualification-ms94-v5/references/retained/LightyearOperationsTest.java'
        base = path.read_bytes()
        for control in CONTROLS:
            raw, record = j1(base, control)
            self.assertEqual(j1(base, control), (raw, record))
            self.assertFalse(record['compiled']); self.assertFalse(record['J1_predicates_changed'])
            if control == 'genuine-equipment-fault': self.assertEqual(raw, base)
            else: self.assertNotEqual(raw, base)
        self.assertEqual(path.read_bytes(), base)
        with self.assertRaises(EvidenceFailure): j1(b'invalid source', 'prior-lock')

    def test_J1_bridge_calls_original_judge_after_entry_clocks_and_capture(self):
        from tools.ms94_b06_j1_bridge import evaluate
        with patch('tools.ms94_b06_j1_bridge.replay_entry') as entry, \
             patch('tools.ms94_b06_admission.replay_clocks') as clocks, \
             patch('tools.ms94_b06_admission.native_pair_tables') as tables, \
             patch('tools.ms94_v6_gate.evaluate', return_value={'passed': False, 'status': 'business-failure'}) as judge:
            self.assertEqual(evaluate(Path('fixture'), b'key')['status'], 'business-failure')
            entry.assert_called_once(); clocks.assert_called_once(); tables.assert_called_once(); judge.assert_called_once()


if __name__ == '__main__': unittest.main()
