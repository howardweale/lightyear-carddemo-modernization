"""Synthetic terminal/delivery mutants; never native qualification evidence."""
import copy
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from lightyear_calibration.contracts import canonical, read_json, seal
from tests.test_ms94_a3_entry_v2 import test_signer
from tests.test_ms94_b06_posting_controls import write_stream, frame
from tools.ms94_b06_admission import EvidenceFailure
from tools.ms94_b06_posting_replay import CANDIDATE, SUPPORT, TERMINAL, TERMINAL_SIGNATURE, replay_stream
from tools.ms94_b06_runtime_delivery import terminal_projection, route, record_zero_model_delivery, replay_delivery

SOURCE = 'class LightyearOperationsTest { void test() {\n throw new NullPointerException();\n}}\nfinal class JourneySupport {}'
ENGINE = 'org.junit.platform.engine.support.hierarchical.NodeTestTask'


def runtime_fixture(origin=CANDIDATE):
    throwing = frame(origin); throwing['line'] = 2
    candidate = frame(CANDIDATE); candidate['line'] = 2
    event = {'kind': 'exception', 'checkpoint': True, 'thread': 1, 'sequence': 2,
             'exception_id': 99, 'exception_class': 'java.lang.NullPointerException',
             'exception_ancestry': ['java.lang.NullPointerException', 'java.lang.RuntimeException',
                                    'java.lang.Exception', 'java.lang.Throwable', 'java.lang.Object'],
             'frames': [throwing] if origin == CANDIDATE else [throwing, candidate],
             'caught': True, 'catch_location': {'class': ENGINE}, 'unwound_calls': []}
    terminal_frame = frame(TERMINAL)
    terminal_frame.update(method='executionFinished', signature=TERMINAL_SIGNATURE)
    terminal = {'kind': 'test-terminal', 'checkpoint': True, 'sequence': 3, 'thread': 1,
                'frames': [terminal_frame, frame(ENGINE)], 'descriptor_id': 123,
                'descriptor_class': 'org.junit.jupiter.engine.descriptor.TestMethodTestDescriptor',
                'test_class': CANDIDATE, 'test_method': 'test', 'status': 'FAILED', 'exception_id': 99}
    return event, terminal


class RuntimeDeliveryTests(unittest.TestCase):
    def test_terminal_binding_and_closed_B05_shape(self):
        event, terminal = runtime_fixture()
        stream = {'collection_complete': True, 'exceptions': [event], 'terminals': [terminal]}
        value, suspect = terminal_projection(stream, {'exit_code': 1}, SOURCE)
        self.assertFalse(suspect)
        self.assertEqual(value, {'category': 'candidate-runtime-exception', 'exception_class': 'NullPointerException',
                                'thrown_by': 'candidate', 'candidate_frame': {'method': 'test', 'line': 2}})
        for change in ('missing', 'different-object', 'later', 'different-thread', 'aborted', 'two-failed'):
            broken = copy.deepcopy(stream)
            if change == 'missing': broken['terminals'] = []
            elif change == 'different-object': broken['terminals'][0]['exception_id'] = 100
            elif change == 'later': broken['exceptions'][0]['sequence'] = 4
            elif change == 'different-thread': broken['terminals'][0]['thread'] = 2
            elif change == 'aborted': broken['terminals'][0]['status'] = 'ABORTED'
            else: broken['terminals'].append(copy.deepcopy(terminal))
            with self.subTest(change=change):
                self.assertEqual(terminal_projection(broken, {'exit_code': 1}, SOURCE), (None, True))

    def test_support_outside_equipment_caught_throws_and_private_prose_do_not_leak(self):
        for origin in (SUPPORT, 'outside.Helper', 'org.compiere.model.MOrder'):
            event, terminal = runtime_fixture(origin)
            self.assertEqual(terminal_projection({'collection_complete': True, 'exceptions': [event],
                'terminals': [terminal]}, {'exit_code': 1}, SOURCE), (None, True))
        event, terminal = runtime_fixture()
        caught = copy.deepcopy(event); caught.update(exception_id=100, sequence=1,
            exception_class='java.sql.SQLException', exception_ancestry=['java.sql.SQLException', 'java.lang.Object'])
        stream = {'collection_complete': True, 'exceptions': [caught, event], 'terminals': [terminal]}
        self.assertEqual(terminal_projection(stream, {'exit_code': 1}, SOURCE), (None, True))
        event['exception_message'] = 'PRIVATE-ACCOUNT-123'
        result = terminal_projection({**stream, 'exceptions': [event]}, {'exit_code': 1}, SOURCE)
        self.assertNotIn(b'PRIVATE', canonical(result))
        success = {**terminal, 'status': 'SUCCESSFUL', 'exception_id': None}
        self.assertEqual(terminal_projection({**stream, 'terminals': [success]}, {'exit_code': 0}, SOURCE), (None, False))

    def test_replay_real_stream_format_checks_terminal_framework_and_bytecode(self):
        for lane in ('oracle', 'postgresql'):
            for mutant in ('none', 'candidate-callback', 'bytecode', 'missing-engine', 'duplicate'):
                with self.subTest(lane=lane, mutant=mutant), tempfile.TemporaryDirectory() as tmp:
                    event, terminal = runtime_fixture()
                    classes = {f['class']: {'constant_pool_sha256': f['constant_pool_sha256'],
                        'methods': {f['method'] + f['signature']: f['method_sha256']}}
                        for f in event['frames'] + terminal['frames']}
                    if mutant == 'candidate-callback': terminal['frames'].append(frame(CANDIDATE))
                    if mutant == 'bytecode': terminal['frames'][0]['method_sha256'] = 'c' * 64
                    if mutant == 'missing-engine': terminal['frames'] = terminal['frames'][:1]
                    events = [{'kind': 'ready', 'checkpoint': False, 'sequence': 1}, event, terminal]
                    if mutant == 'duplicate': events.append({**terminal, 'sequence': 4})
                    events.append({'kind': 'vm-death', 'checkpoint': False, 'sequence': len(events) + 1})
                    receipt = write_stream(Path(tmp), lane, events)
                    if mutant == 'none':
                        value = replay_stream(Path(tmp), receipt, classes, lane)
                        self.assertFalse(terminal_projection(value, {'exit_code': 1}, SOURCE)[1])
                    else:
                        with self.assertRaises(EvidenceFailure): replay_stream(Path(tmp), receipt, classes, lane)

    def test_direct_route_bypasses_analyst_but_legacy_remains(self):
        value = terminal_projection({'collection_complete': True, 'exceptions': [runtime_fixture()[0]],
            'terminals': [runtime_fixture()[1]]}, {'exit_code': 1}, SOURCE)[0]
        policy = {'direct_categories': ['candidate-runtime-exception']}
        legacy = {'category': 'legacy'}
        self.assertEqual(route([value, legacy], policy, equipment_suspect=False),
                         {'direct': [value], 'analyst': [legacy], 'halt': False})
        self.assertEqual(route([value, legacy], policy, equipment_suspect=True),
                         {'direct': [], 'analyst': [], 'halt': True})

    def test_signed_delivery_actual_inbox_replay_no_support_delivery_no_overwrite(self):
        for suspect in (False, True):
            with self.subTest(suspect=suspect), tempfile.TemporaryDirectory() as tmp:
                run = Path(tmp); signer = test_signer()
                plan = seal({'model_calls': 0, 'qualification_only': True,
                             'runtime_delivery': {'consumer': 'zero-model-preflight-inbox/1'}})
                (run / 'plan.json').write_bytes(canonical(plan))
                diagnostics = [] if suspect else [{'id': 'runtime-1', **terminal_projection(
                    {'collection_complete': True, 'exceptions': [runtime_fixture()[0]],
                     'terminals': [runtime_fixture()[1]]}, {'exit_code': 1}, SOURCE)[0], 'lanes': 'both'}]
                projected = {'artifact_type': 'ms94-b06-runtime-projection/1', 'plan_sha256': plan['content_sha256'],
                    'diagnostics': diagnostics, 'equipment_suspect': suspect,
                    'route': 'halt-equipment-suspect' if suspect else 'direct-builder', 'model_calls': 0}
                with patch('tools.ms94_b06_runtime_delivery.project_pair', return_value=projected):
                    record_zero_model_delivery(run, run, signer)
                    self.assertTrue(replay_delivery(run, run, signer.public)['delivery_replayed'])
                    self.assertEqual((run / 'zero-model-builder-inbox.json').exists(), not suspect)
                    with self.assertRaises(EvidenceFailure): record_zero_model_delivery(run, run, signer)
                    record = read_json(run / 'runtime-delivery.json')
                    body = {k: v for k, v in record.items() if k not in ('content_sha256', 'signature')}
                    body['delivered'] = suspect
                    # Signature bytes alone cannot confer a delivery that did not happen.
                    (run / 'runtime-delivery.json').write_bytes(canonical(signer.sign(body)))
                    with self.assertRaises(EvidenceFailure): replay_delivery(run, run, signer.public)


if __name__ == '__main__': unittest.main()
