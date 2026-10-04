"""PR241 fault mutants. Synthetic boundary tests, not native qualification."""
import copy
from contextlib import ExitStack
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lightyear_calibration.contracts import canonical, seal
from lightyear_calibration.ms94_v3_errors import BusinessViolation
from lightyear_calibration.journey_runtime import JourneyAbort
from tools.ms94_b06_admission import EvidenceFailure, classify_failure
from tools.ms94_b06_candidate_result import CandidateTimeout, candidate_trace, trace_shape
from tools.ms94_b06_footprint import MATERIALS, PURCHASING
from tools.ms94_b06_native import NativeRunner
from tools.ms94_b06_native_gate import evaluate
from tools.ms94_b06_runtime_contract import runtime_contract, admit_contract, verify_runtime, clock_record


class ReviewMutants(unittest.TestCase):
    def test_missing_invalid_trace_fields_never_become_equipment(self):
        for journey, stages in (('J2', PURCHASING), ('J3', MATERIALS)):
            for stage in stages:
                for value in (None, '', 'not-an-id', '-1', '0', '2147483648', True, '1.1'):
                    trace = {s + '.id': '1' for s in stages}
                    for s in stages:
                        trace.update({s + '.uuid': '12345678-1234-1234-1234-123456789012', s + '.saved': 'true'})
                    if value is None:
                        del trace[stage + '.id']
                    else:
                        trace[stage + '.id'] = value
                    with self.subTest(journey=journey, stage=stage, value=value):
                        with self.assertRaises(BusinessViolation) as caught:
                            trace_shape(trace, journey)
                        self.assertEqual(classify_failure(caught.exception), 'business-failure')

    def test_xml_boundary_does_not_swallow_equipment_io_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'journey.xml'
            with self.assertRaisesRegex(BusinessViolation, 'trace-file-missing'):
                candidate_trace(p, 'J3')
            p.write_bytes(b'<broken')
            with self.assertRaisesRegex(BusinessViolation, 'trace-format-invalid'):
                candidate_trace(p, 'J3')
            with patch('tools.ms94_b06_candidate_result.read_trace', side_effect=PermissionError()):
                with self.assertRaises(PermissionError): candidate_trace(p, 'J3')

    def test_timeout_is_candidate_but_controller_deadline_is_not(self):
        runner = object.__new__(NativeRunner)
        for reason in ('application-timeout', 'operator-cancelled', 'calendar-boundary', 'hard-deadline'):
            with patch('tools.ms94_calendar_runner.CalendarRunner.worker', side_effect=JourneyAbort(reason)):
                with self.assertRaises(Exception) as caught: runner.worker('execute', {}, 1)
            self.assertEqual(classify_failure(caught.exception),
                             'candidate-timeout' if reason == 'application-timeout' else 'equipment-failure')
        with patch('tools.ms94_calendar_runner.CalendarRunner.worker', side_effect=JourneyAbort('application-timeout')):
            with self.assertRaises(JourneyAbort): runner.worker('capture', {}, 1)

    def test_timeout_retains_cleanup_and_cleanup_failure_overrides_candidate(self):
        from tools.ms94_b06_native import execute_pair
        from lightyear_calibration.journey_order import RUNS
        from tests.test_ms94_a3_entry_v2 import test_signer
        signer = test_signer()
        for clean in (True, False):
            with tempfile.TemporaryDirectory() as tmp, ExitStack() as mocks:
                root = Path(tmp); run = root / RUNS / 'timeout-control'; run.mkdir(parents=True)
                plan = {'inputs_sha256': {'operations.java': 'h'}, 'harness_sha256': 'h', 'calendar': {},
                        'implementation_sha256': {}, 'content_sha256': 'p', 'journey': 'J3',
                        'candidate_timeout_seconds': 1, 'declaration': {'application': {'source_commit': 'c'}}}
                (run / 'plan.json').write_bytes(canonical(plan))
                (run / 'authorization.json').write_bytes(canonical(signer.sign({
                    'scope': 'zero-model-native-qualification', 'run_id': run.name, 'plan': {'plan_sha256': 'p'}})))
                mocks.enter_context(patch('tools.ms94_b06_native.verify_inputs'))
                mocks.enter_context(patch('tools.ms94_b06_native.guard'))
                mocks.enter_context(patch('tools.ms94_b06_native.full_entry'))
                runner = mocks.enter_context(patch('tools.ms94_b06_native.NativeRunner')).return_value
                runner.worker.side_effect = CandidateTimeout()
                cleanup = mocks.enter_context(patch('tools.ms94_b06_native.cleanup_owned', return_value={'complete': clean}))
                receipt = execute_pair(root, run, signer)
                cleanup.assert_called_once()
                self.assertEqual(receipt['status'], 'candidate-timeout' if clean else 'equipment-failure')
                self.assertEqual(receipt['equipment_suspect'], not clean)
                self.assertFalse(receipt['qualification_credit'])
                self.assertTrue((run / 'cleanup.json').is_file())

    def test_plan_bound_observer_runtime_not_literal_five(self):
        plan = {'local': {'runner_image': 'app'}, 'posting_observer': {},
                'declaration': {'environment': {'engines': {l: {'image_digest': l} for l in ('oracle', 'postgresql')}}}}
        spec = {'clock_stages': ['before', 'after'], 'runtime': runtime_contract(plan, 'run-1')}
        plan['evidence_contract'] = spec
        admit_contract(plan, 'run-1')
        records = [{**v, 'privileged': False, 'sys_time_capability': False,
                    'clock_manipulation_environment': False} for v in spec['runtime'].values()]
        self.assertEqual(len(records), 7)
        verify_runtime(records, spec)
        for mutant in ('missing', 'extra', 'duplicate', 'wrong-role-image', 'wrong-container'):
            rows = copy.deepcopy(records)
            if mutant == 'missing': rows.pop()
            elif mutant == 'extra': rows.append({**rows[0], 'container': 'extra'})
            elif mutant == 'duplicate': rows[-1] = rows[0]
            elif mutant == 'wrong-role-image': rows[0]['image'] = 'postgresql'
            else: rows[0]['container'] = 'other-slot'
            with self.subTest(mutant=mutant), self.assertRaises(EvidenceFailure): verify_runtime(rows, spec)
        del spec['runtime']['observer-oracle']
        with self.assertRaisesRegex(EvidenceFailure, 'runtime-plan-invalid'): admit_contract(plan, 'run-1')

    def test_clock_sample_mutants_are_typed_evidence(self):
        stamp = '2026-10-04T00:00:00Z'
        execution = {'content_sha256': 'e', **{'native_clock_' + s: {'value': stamp} for s in ('before', 'after')}}
        samples = [{'stage': s, 'host_before_utc': stamp, 'host_after_utc': stamp,
                    'value': stamp, 'monotonic': 0} for s in ('before', 'after')]
        clock_record(samples, execution, ['before', 'after'])
        for mutant in ([], samples[:1], samples + samples[:1], list(reversed(samples)),
                       [{**samples[0], 'value': 'different'}, samples[1]],
                       [{k: v for k, v in samples[0].items() if k != 'monotonic'}, samples[1]]):
            with self.assertRaises(EvidenceFailure): clock_record(mutant, execution, ['before', 'after'])

    def test_business_record_binds_read_evidence_and_actual_progress(self):
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as mocks:
            run = Path(tmp)
            def save(name, data):
                p = run / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(canonical(data))
            save('plan.json', {'journey': 'J3', 'content_sha256': 'plan', 'harness_sha256': 'h',
                               'declaration': {'application': {'source_commit': 'source'}}})
            save('authorization.json', {'run_id': run.name, 'content_sha256': 'auth',
                 'plan': {'plan_sha256': 'plan'}, 'scope': 'zero-model-native-qualification'})
            save('inputs/datatype-inventory.json', {'columns': []})
            save('inputs/comparison-register.json', {'timestamp_decision': {}})
            save('cases/operations/1/execution/oracle/execution.json', seal({'harness_sha256': 'h',
                 'application_source_commit': 'source', 'exit_code': 0}))
            bindings = {l: {'before_sha256': l + '-old', 'after_sha256': l + '-new', 'all_tables_replayed': 915}
                        for l in ('oracle', 'postgresql')}
            mocks.enter_context(patch('tools.ms94_b06_native_gate.verify_inputs', return_value={}))
            mocks.enter_context(patch('tools.ms94_b06_native_gate.verify_envelope', return_value=True))
            mocks.enter_context(patch('tools.ms94_b06_native_gate.replay_entry', return_value={'content_sha256': 'entry'}))
            mocks.enter_context(patch('tools.ms94_b06_native_gate.replay_clocks', return_value={'clock_sha256': 'clock'}))
            mocks.enter_context(patch('tools.ms94_b06_native_gate.native_pair_tables', return_value=({}, {}, bindings)))
            mocks.enter_context(patch('tools.ms94_b06_expectations.verify_private_derivation'))
            mocks.enter_context(patch('tools.ms94_b06_native_gate.read_capture', return_value={'results': {
                'identity': {'rows': [{'time_zone': 'UTC'}]}, 'settings': {'rows': [{'name': 'TimeZone', 'setting': 'UTC'}]}}}))
            mocks.enter_context(patch('tools.ms94_b06_native_gate.assess', return_value={'columns': []}))
            result = evaluate(run, b'unused')  # Real missing candidate trace boundary.
            self.assertEqual(result['closed_reason'], 'trace-file-missing')
            self.assertEqual(result['evidence_bindings']['entry_sha256'], 'entry')
            self.assertEqual(result['evidence_bindings']['clock'], {'clock_sha256': 'clock'})
            self.assertEqual(result['evidence_bindings']['capture_bindings'], bindings)
            self.assertEqual(result['gate_progress']['failed'], 'oracle:trace')
            self.assertIn('postgresql:business', result['gate_progress']['not_executed'])
            self.assertEqual(result['gate_progress']['completed'][-1], 'oracle:execution')
            self.assertTrue(result['full_entry_replayed'])
            self.assertFalse(result['complete_gate_replayed'])
            self.assertEqual(evaluate(run, b'unused'), result)


if __name__ == '__main__': unittest.main()
