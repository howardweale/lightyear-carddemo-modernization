"""Synthetic boundary tests only; these are never native qualification evidence."""
import copy
from datetime import datetime, timezone
import tempfile
from pathlib import Path
import unittest
from contextlib import ExitStack
from unittest.mock import patch

from lightyear_calibration.contracts import canonical, seal, read_json
from lightyear_calibration.ms94_v3_errors import BusinessViolation
from lightyear_control_tower.decisions import verify_envelope
from tests.test_ms94_a3_entry_v2 import test_signer
from tools.ms94_b06_admission import (EvidenceFailure, bound_file, sign_once, complete_tables,
                                     row_delta, replay_clocks, classify_failure, verify_inputs)
from tools.ms94_b06_footprint import validate, MATERIALS
from tools.ms94_b06_reconciliation import materials_rule
from tools.ms94_b06_native import execute_pair


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.signer = test_signer()

    def save(self, name, value):
        path = self.root / name; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(canonical(value))

    def test_signature_is_read_back_and_never_overwritten(self):
        path = self.root / 'entry.json'
        signed = sign_once(path, {'artifact_type': 'fixture'}, self.signer)
        self.assertTrue(verify_envelope(signed, self.signer.public))
        with self.assertRaises(EvidenceFailure):
            sign_once(path, {'artifact_type': 'replacement'}, self.signer)
        self.assertEqual(read_json(path), signed)

    def test_presigned_body_cannot_pass_unsealed_boundary(self):
        with self.assertRaises(EvidenceFailure):
            sign_once(self.root / 'entry.json', seal({'artifact_type': 'fixture'}), self.signer)

    def test_missing_table_is_rejected_before_reading_rows(self):
        with patch('tools.ms94_b06_admission.state', return_value={'tables': {'a': {}}}), \
             patch('tools.ms94_b06_admission.rows') as rows:
            with self.assertRaisesRegex(EvidenceFailure, 'incomplete-table-inventory'):
                complete_tables(self.root, 'oracle', {'a', 'unmentioned-business-table'})
            rows.assert_not_called()

    def test_all_tables_are_read_even_when_judge_does_not_use_them(self):
        with patch('tools.ms94_b06_admission.state', return_value={'tables': {'a': 1, 'b': 2}}), \
             patch('tools.ms94_b06_admission.rows', side_effect=[[{'id': 1}], [{'id': 2}]]) as rows:
            _, result = complete_tables(self.root, 'oracle', {'a', 'b'})
            self.assertEqual(set(result), {'a', 'b'}); self.assertEqual(rows.call_count, 2)

    def test_multiset_delta_preserves_duplicate_rows(self):
        self.assertEqual(row_delta([{'x': 1}, {'x': 1}], [{'x': 1}, {'x': 2}]),
                         ([{'x': 1}], [{'x': 2}]))

    def test_binding_cannot_escape_root_or_accept_changed_bytes(self):
        for name in ('../secret', str(self.root / 'absolute')):
            with self.assertRaises(EvidenceFailure): bound_file(self.root, name, '0'*64)
        (self.root / 'input').write_bytes(b'changed')
        with self.assertRaises(EvidenceFailure): bound_file(self.root, 'input', '0'*64)

    def test_j1_is_not_routed_through_the_new_gate(self):
        with self.assertRaisesRegex(EvidenceFailure, 'adapter-does-not-own-J1'):
            verify_inputs(self.root, seal({'artifact_type': 'ms94-b06-native-pair-plan/1', 'journey': 'J1'}))

    def test_typed_failures_are_distinct(self):
        self.assertEqual(classify_failure(BusinessViolation('closed')), 'business-failure')
        self.assertEqual(classify_failure(EvidenceFailure('closed')), 'insufficient-evidence')
        self.assertEqual(classify_failure(OSError()), 'equipment-failure')

    def test_unsigned_authorization_cannot_create_resources(self):
        from lightyear_calibration.journey_order import RUNS
        run = self.root / RUNS / 'journey-test'; run.mkdir(parents=True)
        plan = {'inputs_sha256': {'operations.java': 'h'}, 'harness_sha256': 'h', 'calendar': {},
                'implementation_sha256': {}, 'content_sha256': 'p'}
        (run / 'plan.json').write_bytes(canonical(plan))
        (run / 'authorization.json').write_bytes(canonical({'scope': 'zero-model-native-qualification'}))
        with patch('tools.ms94_b06_native.verify_inputs'), patch('tools.ms94_b06_native.guard'), \
             patch('tools.ms94_b06_native.NativeRunner') as runner:
            with self.assertRaises(EvidenceFailure): execute_pair(self.root, run, self.signer)
            runner.assert_not_called()
            self.assertFalse((run / 'started.json').exists())

    def test_failed_entry_prevents_candidate_and_still_records_cleanup(self):
        from lightyear_calibration.journey_order import RUNS
        run = self.root / RUNS / 'journey-entry-failure'; run.mkdir(parents=True)
        plan = {'inputs_sha256': {'operations.java': 'h'}, 'harness_sha256': 'h', 'calendar': {},
                'implementation_sha256': {}, 'content_sha256': 'p', 'journey': 'J3'}
        (run / 'plan.json').write_bytes(canonical(plan))
        (run / 'authorization.json').write_bytes(canonical(self.signer.sign({
            'scope': 'zero-model-native-qualification', 'run_id': run.name,
            'plan': {'plan_sha256': 'p'}})))
        with ExitStack() as stack:
            stack.enter_context(patch('tools.ms94_b06_native.verify_inputs'))
            stack.enter_context(patch('tools.ms94_b06_native.guard'))
            runner = stack.enter_context(patch('tools.ms94_b06_native.NativeRunner')).return_value
            stack.enter_context(patch('tools.ms94_b06_native.full_entry', side_effect=EvidenceFailure('entry-invalid')))
            cleanup = stack.enter_context(patch('tools.ms94_b06_native.cleanup_owned', return_value={'complete': True}))
            receipt = execute_pair(self.root, run, self.signer)
            runner.worker.assert_not_called(); cleanup.assert_called_once_with(runner)
            self.assertEqual(receipt['status'], 'insufficient-evidence')
            self.assertFalse(receipt['qualification_credit'])
            self.assertTrue(verify_envelope(read_json(run / 'cleanup.json'), self.signer.public))
            with self.assertRaisesRegex(EvidenceFailure, 'already-attempted'):
                execute_pair(self.root, run, self.signer)
            self.assertEqual(runner.prepare.call_count, 1)

    def clock_fixture(self):
        calendar = seal({'clock_mode': 'unmodified-real-time', 'period_start_utc': '2026-10-01T00:00:00Z',
                         'period_end_exclusive_utc': '2026-11-01T00:00:00Z'})
        plan = seal({'calendar': calendar, 'local': {'runner_image': 'image'},
                     'declaration': {'environment': {'engines': {l: {'image_digest': l} for l in ('oracle', 'postgresql')}}}})
        self.save('plan.json', plan)
        lanes = {}
        for lane in ('oracle', 'postgresql'):
            execution = seal({'native_clock_before': {'value': '2026-10-04T00:00:00Z'},
                              'native_clock_after': {'value': '2026-10-04T00:01:00Z'}})
            self.save('cases/operations/1/execution/' + lane + '/execution.json', execution)
            lanes[lane] = {'host_start_utc': '2026-10-04T00:00:00Z', 'host_end_utc': '2026-10-04T00:01:00Z',
                           'monotonic_seconds': 60, 'execution_sha256': execution['content_sha256']}
        return {'plan_sha256': plan['content_sha256'], 'lanes': lanes,
                'runtime': [{'container': str(i), 'image': 'image', 'clock_manipulation_environment': False,
                             'privileged': False, 'sys_time_capability': False} for i in range(5)]}

    def test_real_clock_replay_rejects_drift_manipulation_and_duplicate_runtime(self):
        body = self.clock_fixture()
        self.save('b06-clock-evidence.json', self.signer.sign(body))
        self.assertTrue(replay_clocks(self.root, self.signer.public)['clock_replayed'])
        for mutation in ('drift', 'privileged', 'duplicate', 'plan'):
            altered = copy.deepcopy(body)
            if mutation == 'drift': altered['lanes']['oracle']['monotonic_seconds'] = 0
            if mutation == 'privileged': altered['runtime'][0]['privileged'] = True
            if mutation == 'duplicate': altered['runtime'][1]['container'] = '0'
            if mutation == 'plan': altered['plan_sha256'] = 'different'
            self.save('b06-clock-evidence.json', self.signer.sign(altered))
            with self.assertRaises(EvidenceFailure): replay_clocks(self.root, self.signer.public)


class FootprintTests(unittest.TestCase):
    def fixture(self):
        before, after, trace = {}, {}, {}
        for i, (stage, table) in enumerate(MATERIALS.items(), 10):
            before.setdefault(table, [])
            after.setdefault(table, []).append({table + '_id': i, 'ad_client_id': 1, 'ad_org_id': 2})
            trace[stage + '.id'] = str(i)
        before['unrelated_table'] = [{'id': 1, 'value': 'original'}]
        after['unrelated_table'] = copy.deepcopy(before['unrelated_table'])
        contract = {'journey': 'J3', 'client_id': 1, 'organization_id': 2,
                    'document_table_ids': {'m_inventory': 321, 'm_movement': 323}}
        return before, after, trace, contract

    def test_equal_unowned_writes_cannot_hide_in_cross_engine_comparison(self):
        before, after, trace, contract = self.fixture()
        self.assertTrue(validate(before, after, trace, contract)['passed'])
        after['unrelated_table'][0]['value'] = 'same-mutation-on-both-engines'
        with self.assertRaisesRegex(BusinessViolation, 'preexisting-row'):
            validate(before, after, trace, contract)

    def test_new_foreign_product_row_and_wrong_client_rejected(self):
        for mutation in ('product', 'client'):
            before, after, trace, contract = self.fixture()
            if mutation == 'product':
                before['m_cost'] = []
                after['m_cost'] = [{'m_product_id': 999, 'ad_client_id': 1, 'ad_org_id': 2}]
            else: after['m_product'][0]['ad_client_id'] = 999
            with self.assertRaises(BusinessViolation): validate(before, after, trace, contract)

    def test_material_rules_cannot_normalize_quantity_or_cost(self):
        for column in ('movementqty', 'currentcostprice', 'account_id'):
            self.assertIsNone(materials_rule('m_movementline', column, {'oracle': '1', 'postgresql': '2'},
                                            new_row=True, unique_uuid=False, windows={}))


if __name__ == '__main__': unittest.main()
