"""Portable synthetic tests. No provider, compiler, Docker or hidden generator."""
import copy
from pathlib import Path
import unittest
from unittest.mock import patch

from lightyear_factory import public_repair_controller as c
from lightyear_factory import public_repair_staged as s
from test_public_repair_controller import binding as base_binding, Clock, CONTEXT, Ports

H = 'a' * 64
JAR = b'PUBLIC SYNTHETIC JAR BYTES (not executable)'


def binding():
    commitment = dict(schema='heldout-pre-run-commitment/1',
        committed_at='2026-11-17T18:00:00-08:00', commitment_sha256=H,
        publication_receipt_sha256='b'*64)
    row = base_binding()
    row.update(schema='staged-public-binding/1', mode='STAGED_PUBLIC',
        pre_run_commitment=commitment, heldout_commitment_sha256=c.digest(commitment),
        approval_timestamp='2026-11-18T03:00:00+00:00', public_answer_key_sha256='1'*64,
        staged_policy_sha256=s.POLICY_HASH, worker_source_sha256=c.sha(Path(__file__).read_bytes()),
        build_profile=dict(cli_sha256=H, helper_sha256=H, jdk_sha256=H, jre_sha256=H))
    return row


def descriptor(selected, row, closure):
    return dict(schema='retained-selected-jar/1', binding_sha256=c.digest(row),
        source_sha256=selected['artifact_sha256'], jar_sha256=c.sha(JAR), jar_bytes=len(JAR),
        build_receipt_sha256=selected['build_receipt_sha256'],
        public_receipt_sha256=selected['public_receipt_sha256'], retained_leaf=s.LEAF,
        readback_sha256=c.sha(JAR), runtime_profile_sha256=row['runtime_profile_sha256'],
        worker_source_sha256=row['worker_source_sha256'], closure_record_sha256=closure,
        heldout_commitment_sha256=row['heldout_commitment_sha256'])


class StagedPorts(Ports):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.retained = []

    def retain_selected_jar(self, selected, row, closure, deadline):
        assert self.closed
        assert 'models-closed' in self.records
        self.retained.append(copy.deepcopy(selected))
        return descriptor(selected, row, closure)

    def evaluate_hidden(self, *args):
        raise AssertionError('hidden executor must not be reachable')


class StagedTests(unittest.TestCase):
    def make(self, ports=None):
        ports = StagedPorts() if ports is None else ports
        return s.StagedController(ports, binding(), CONTEXT, Clock()), ports

    def test_public_perfect_is_pending_with_exact_descriptor(self):
        controller, ports = self.make()
        result = controller.run()
        self.assertEqual(result['status'], 'PUBLIC_COMPLETE_HIDDEN_PENDING')
        self.assertEqual(result['schema'], 'staged-public-result/1')
        self.assertEqual(result['hidden']['status'], 'PENDING')
        self.assertEqual(result['retained_jar']['jar_sha256'], c.sha(JAR))
        self.assertEqual(result['retained_jar']['source_sha256'], result['selected']['artifact_sha256'])
        self.assertNotEqual(result['retained_jar']['source_sha256'], c.sha(JAR))
        self.assertFalse(result['qualified'])
        self.assertFalse(result['hidden_execution_authorized'])
        self.assertNotIn('hidden-invocation', ports.records)
        self.assertEqual(len(ports.requests), 2)
        self.assertEqual(result['reserved_microdollars'], 4224000)

    def test_all_public_differences_are_not_hidden_pending(self):
        controller, ports = self.make(StagedPorts((1, 2, 3, 4, 5, 6)))
        result = controller.run()
        self.assertEqual(result['status'], 'PUBLIC_FAIL')
        self.assertEqual(result['hidden'], dict(status='NOT_RUN', reason='public-fail'))
        self.assertIsNone(result['retained_jar'])
        self.assertEqual(ports.retained, [])
        self.assertEqual(result['reserved_microdollars'], 37664000)

    def test_compile_only_failures_cannot_claim_pending(self):
        controller, ports = self.make(StagedPorts((), compile_fail=range(6)))
        result = controller.run()
        self.assertEqual(result['status'], 'CANDIDATE_FAIL')
        self.assertEqual(result['hidden']['reason'], 'no-evaluated-candidate')
        self.assertIsNone(result['retained_jar'])
        self.assertEqual(ports.retained, [])

    def test_repaired_perfect_candidate_is_the_retained_selection(self):
        controller, ports = self.make(StagedPorts((5, 4, 16)))
        result = controller.run()
        self.assertEqual(result['selected']['round'], 2)
        self.assertEqual(ports.retained, [result['selected']])
        self.assertEqual(len(ports.requests), 6)
        self.assertTrue(ports.closed)

    def test_closure_failure_does_not_retain_or_report_pending(self):
        controller, ports = self.make()
        ports.fail = 'close'
        with self.assertRaises(OSError):
            controller.run()
        self.assertEqual(ports.retained, [])
        self.assertNotIn('result', ports.records)

    def test_failed_durable_closure_record_stops_retention(self):
        controller, ports = self.make()
        original = ports.record
        def fail(name, row):
            if name == 'models-closed':
                raise OSError('private path deliberately absent')
            return original(name, row)
        ports.record = fail
        with self.assertRaises(OSError):
            controller.run()
        self.assertEqual(ports.retained, [])
        self.assertEqual(ports.records['stopped']['refusal_code'], 'port-fault')

    def test_retention_fault_is_terminal_without_repeat(self):
        controller, ports = self.make()
        def fail(*_):
            raise c.Refused('staged-jar')
        ports.retain_selected_jar = fail
        with self.assertRaisesRegex(c.Refused, 'staged-jar'):
            controller.run()
        self.assertEqual(ports.records['stopped']['refusal_code'], 'staged-jar')
        self.assertNotIn('result', ports.records)
        with self.assertRaisesRegex(c.Refused, 'controller-reused'):
            controller.run()

    def test_changed_descriptor_join_or_extra_field_refuses(self):
        for field in ('binding_sha256', 'source_sha256', 'build_receipt_sha256',
                      'public_receipt_sha256', 'readback_sha256', 'runtime_profile_sha256',
                      'worker_source_sha256', 'closure_record_sha256', 'heldout_commitment_sha256',
                      'unexpected'):
            controller, ports = self.make()
            original = ports.retain_selected_jar
            def changed(*args):
                row = original(*args)
                row[field] = '0'*64
                return row
            ports.retain_selected_jar = changed
            with self.subTest(field=field), self.assertRaisesRegex(c.Refused, 'staged-retention'):
                controller.run()
            self.assertNotIn('result', ports.records)

    def test_late_retention_cannot_extend_window(self):
        controller, ports = self.make()
        original = ports.retain_selected_jar
        def late(*args):
            result = original(*args)
            controller.clock.value = args[-1]
            return result
        ports.retain_selected_jar = late
        with self.assertRaisesRegex(c.Refused, 'deadline'):
            controller.run()
        self.assertNotIn('result', ports.records)

    def test_staged_binding_mandatory_closed_and_graph_off(self):
        for key, value in (('mode', 'LIVE'), ('graph_mode', 'on'), ('public_case_count', 15),
                           ('extra', 1), ('staged_policy_sha256', '0'*64),
                           ('worker_source_sha256', None), ('public_answer_key_sha256', None)):
            row = binding()
            row[key] = value
            with self.subTest(key=key), self.assertRaises(c.Refused):
                s.StagedController(StagedPorts(), row, CONTEXT, Clock())

    def test_commitment_hash_must_join_before_admission(self):
        row = binding()
        row['pre_run_commitment']['commitment_sha256'] = '0'*64
        ports = StagedPorts()
        with self.assertRaisesRegex(c.Refused, 'staged-commitment'):
            s.StagedController(ports, row, CONTEXT)
        self.assertEqual(ports.records, {})
        self.assertEqual(ports.requests, [])

    def test_late_equal_naive_or_invalid_commitment_time_refuses(self):
        for value in ('2026-11-18T04:00:00Z', '2026-11-18T03:00:00Z',
                      '2026-11-17T01:00:00', 'not-a-time'):
            row = binding()
            row['pre_run_commitment']['committed_at'] = value
            row['heldout_commitment_sha256'] = c.digest(row['pre_run_commitment'])
            with self.subTest(value=value), self.assertRaisesRegex(c.Refused, 'staged-time'):
                s.StagedController(StagedPorts(), row, CONTEXT)

    def test_commitments_and_descriptor_never_enter_model_projection(self):
        controller, ports = self.make(StagedPorts((2, 16)))
        controller.run()
        raw = c.canonical(ports.requests)
        for name in (b'heldout', b'pre_run_commitment', b'jar_sha256', b'closure_record'):
            self.assertNotIn(name, raw)

    def test_original_controller_retains_original_mode(self):
        ports = Ports()
        result = c.Controller(ports, base_binding(), CONTEXT, Clock()).run()
        self.assertEqual(result['schema'], 'public-repair-result/1')
        self.assertEqual(result['status'], 'CANDIDATE_PASS')
        self.assertEqual(len(ports.hidden_calls), 1)


class FakeWorker:
    pass


class JarTests(unittest.TestCase):
    def setup_retainer(self):
        row = binding()
        worker = FakeWorker()
        worker.failed = False
        worker.root = Path('synthetic-public-root')
        cleanup = c.canonical(dict(cleanup=True, removed=[]))
        result = dict(exit_code=0, artifact_sha256='3'*64, jar_sha256=c.sha(JAR))
        receipt = dict(schema='public-worker-receipt/1', operation='compile',
            result=result, cleanup_sha256=c.sha(cleanup), public_only=True, **row['build_profile'])
        raw = c.canonical(receipt)
        key = c.sha(raw)
        jar = worker.root/'build-2'/'candidate.jar'
        worker.built = {key: ('3'*64, jar, c.sha(JAR))}
        selected = dict(round=2, artifact_sha256='3'*64, build_receipt_sha256=key,
                        public_receipt_sha256='4'*64)
        storage = s.StagedDurablePorts.__new__(s.StagedDurablePorts)
        self.written = []
        storage._operation = lambda operation: operation()
        def write(leaf, value):
            self.written.append((leaf, value))
            return c.sha(value)
        storage._write = write
        records = {jar: JAR, jar.parent/'receipt.json': raw, jar.parent/'cleanup.json': cleanup}
        return s.P5SelectedJarRetainer(worker, storage, clock=lambda: 1), selected, row, records

    def test_p5_registry_receipt_actual_jar_and_durable_readback_join(self):
        retainer, selected, row, records = self.setup_retainer()
        with patch.object(s, 'read_owned', side_effect=lambda path, cap: records[Path(path)]):
            result = retainer.retain_selected_jar(selected, row, H, 10)
        self.assertEqual(self.written, [(s.LEAF, JAR)])
        self.assertEqual(result['jar_sha256'], c.sha(JAR))
        self.assertEqual(result['build_receipt_sha256'], selected['build_receipt_sha256'])

    def test_no_second_retention_even_after_failure(self):
        retainer, selected, row, _ = self.setup_retainer()
        retainer.worker.failed = True
        with self.assertRaisesRegex(c.Refused, 'staged-worker'):
            retainer.retain_selected_jar(selected, row, H, 10)
        retainer.worker.failed = False
        with self.assertRaisesRegex(c.Refused, 'staged-retention'):
            retainer.retain_selected_jar(selected, row, H, 10)

    def test_unknown_or_mismatched_build_registry_refuses(self):
        for key, value in (('build_receipt_sha256', '0'*64), ('artifact_sha256', '0'*64), ('round', 3)):
            retainer, selected, row, _ = self.setup_retainer()
            selected[key] = value
            with self.subTest(key=key), self.assertRaisesRegex(c.Refused, 'staged-build-join'):
                retainer.retain_selected_jar(selected, row, H, 10)
            self.assertEqual(self.written, [])

    def test_changed_jar_or_receipt_or_cleanup_refuses(self):
        for leaf in ('candidate.jar', 'receipt.json', 'cleanup.json'):
            retainer, selected, row, records = self.setup_retainer()
            path = next(p for p in records if p.name == leaf)
            records[path] += b'changed'
            with patch.object(s, 'read_owned', side_effect=lambda p, cap: records[Path(p)]):
                with self.subTest(leaf=leaf), self.assertRaises(c.Refused):
                    retainer.retain_selected_jar(selected, row, H, 10)
            self.assertEqual(self.written, [])

    def test_profile_and_implementation_hashes_refuse(self):
        for key in ('worker_source_sha256', 'helper_sha256', 'jdk_sha256', 'jre_sha256', 'cli_sha256'):
            retainer, selected, row, records = self.setup_retainer()
            if key == 'worker_source_sha256':
                row[key] = '0'*64
            else:
                row['build_profile'][key] = '0'*64
            with patch.object(s, 'read_owned', side_effect=lambda p, cap: records[Path(p)]):
                with self.subTest(key=key), self.assertRaises(c.Refused):
                    retainer.retain_selected_jar(selected, row, H, 10)

    def test_durable_slot_size_and_byte_type(self):
        retainer, _, _, _ = self.setup_retainer()
        for value in (b'', 'not bytes', b'x'*(s.JAR_BYTES+1)):
            with self.subTest(size=len(value)), self.assertRaisesRegex(c.Refused, 'staged-jar'):
                retainer.storage.retain_jar(value)
        self.assertEqual(self.written, [])

    def test_duplicate_float_and_nonfinite_receipts_refuse(self):
        for raw in (b'{"a":1,"a":2}', b'{"a":0.0}', b'{"a":NaN}', b'{"a":Infinity}'):
            with self.subTest(raw=raw), self.assertRaisesRegex(c.Refused, 'staged-json'):
                s.strict(raw)

    def test_readback_mismatch_does_not_make_descriptor(self):
        retainer, selected, row, records = self.setup_retainer()
        retainer.storage._write = lambda *_: '0'*64
        with patch.object(s, 'read_owned', side_effect=lambda p, cap: records[Path(p)]):
            with self.assertRaisesRegex(c.Refused, 'staged-retention'):
                retainer.retain_selected_jar(selected, row, H, 10)

    def test_descriptor_caps_and_leaf_are_closed(self):
        _, selected, row, _ = self.setup_retainer()
        for key, value in (('jar_bytes', True), ('jar_bytes', 0), ('jar_bytes', s.JAR_BYTES+1),
                           ('retained_leaf', '../candidate.jar'), ('schema', 'wrong')):
            record = descriptor(selected, row, H)
            record[key] = value
            with self.subTest(key=key, value=value), self.assertRaisesRegex(c.Refused, 'staged-retention'):
                s.validate_descriptor(record, selected, row, H)


if __name__ == '__main__':
    unittest.main()
