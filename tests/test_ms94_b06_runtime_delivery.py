"""Synthetic terminal/delivery mutants; never native qualification evidence."""
import copy
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from lightyear_calibration.contracts import canonical, read_json, seal
from lightyear_calibration.journey_order import file_hash
from tests.test_ms94_a3_entry_v2 import test_signer
from tests.test_ms94_b06_posting_controls import write_stream, frame
from tools.ms94_b06_admission import EvidenceFailure
from tools.ms94_b06_posting_replay import CANDIDATE, SUPPORT, TERMINAL, TERMINAL_SIGNATURE, replay_stream
from tools.ms94_b06_runtime_delivery import POLICY, terminal_projection, route, record_zero_model_delivery, replay_delivery

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
    def test_J1_offline_observer_to_B05_shaped_inbox_and_independent_replay(self):
        # Synthetic native-admission and class-file seams only. The stream chain,
        # terminal root binding, paired projection, signatures, actual inbox and
        # delivery replay are real code. This grants no native qualification.
        for origin in (CANDIDATE, SUPPORT, 'outside.Helper'):
            with self.subTest(origin=origin), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); run = root/'j1'; (run/'inputs').mkdir(parents=True)
                (run/'inputs/operations.java').write_text(SOURCE, encoding='utf-8')
                policy = root/POLICY; policy.parent.mkdir(parents=True)
                policy.write_bytes(canonical({'direct_categories': ['candidate-runtime-exception'],
                                             'runtime_origin_required': 'candidate'}))
                signer = test_signer()
                spec = {'class_files_sha256': {'Observer.class': 'a'*64},
                        'java_binary_sha256': 'b'*64, 'target_class_files_sha256': {}}
                plan = seal({'journey': 'J1', 'model_calls': 0, 'qualification_only': True,
                             'implementation_sha256': {}, 'posting_observer': spec,
                             'local': {'runner_image': 'sha256:'+'c'*64},
                             'harness_sha256': file_hash(run/'inputs/operations.java'),
                             'runtime_delivery': {'policy_sha256': file_hash(policy),
                                                  'consumer': 'zero-model-preflight-inbox/1'}})
                (run/'plan.json').write_bytes(canonical(plan))
                (run/'authorization.json').write_bytes(canonical(signer.sign({
                    'run_id': run.name, 'scope': 'zero-model-native-qualification',
                    'plan': {'plan_sha256': plan['content_sha256']}})))
                event, terminal = runtime_fixture(origin)
                classes = {f['class']: {'constant_pool_sha256': f['constant_pool_sha256'],
                    'methods': {f['method']+f['signature']: f['method_sha256']}}
                    for f in event['frames']+terminal['frames']}
                for lane in ('oracle', 'postgresql'):
                    folder = run/'posting-observer'/lane; folder.mkdir(parents=True)
                    exdir = run/'cases/operations/1/execution'/lane; exdir.mkdir(parents=True)
                    execution = seal({'exit_code': 1})
                    (exdir/'execution.json').write_bytes(canonical(execution))
                    receipt = write_stream(folder, lane, [
                        {'kind': 'ready', 'checkpoint': False, 'sequence': 1}, event, terminal,
                        {'kind': 'vm-death', 'checkpoint': False, 'sequence': 4}])
                    receipt.pop('content_sha256', None)
                    receipt.update(artifact_type='ms94-b06-posting-collector-receipt/1', lane=lane,
                        plan_sha256=plan['content_sha256'], execution_sha256=execution['content_sha256'],
                        complete=True, observer_class_files_sha256=spec['class_files_sha256'],
                        target={'image': plan['local']['runner_image'], 'ports_published': False,
                                'observer_private_mount_absent': True, 'jvm': {
                                'java_binary_sha256': spec['java_binary_sha256'], 'arguments': [
                                '-agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=*:5005']}})
                    (folder/'receipt.json').write_bytes(canonical(signer.sign(receipt)))
                with patch('tools.ms94_b06_posting_replay.replay_entry', return_value=seal({'fixture': 'entry'})), \
                     patch('tools.ms94_b06_posting_replay.replay_clocks', return_value={'fixture': 'clocks'}), \
                     patch('tools.ms94_b06_posting_replay.catalog', return_value=classes):
                    delivered = record_zero_model_delivery(root, run, signer)
                    replayed = replay_delivery(root, run, signer.public)
                    self.assertTrue(replayed['runtime_origin_replayed'] and replayed['delivery_replayed'])
                    self.assertEqual(0, delivered['analyst_invocations'])
                    self.assertEqual(origin == CANDIDATE, replayed['delivered'])
                    self.assertEqual(origin != CANDIDATE, replayed['equipment_suspect'])
                    if origin == CANDIDATE:
                        inbox = read_json(run/'zero-model-builder-inbox.json')
                        self.assertEqual([{'id': 'runtime-1', 'category': 'candidate-runtime-exception',
                            'exception_class': 'NullPointerException', 'thrown_by': 'candidate',
                            'candidate_frame': {'method': 'test', 'line': 2}, 'lanes': 'both'}], inbox['diagnostics'])
                        # A still-signed altered payload cannot pass replay.
                        body = {k:v for k,v in inbox.items() if k not in ('signature', 'content_sha256')}
                        body['diagnostics'][0]['candidate_frame']['line'] = 3
                        (run/'zero-model-builder-inbox.json').write_bytes(canonical(signer.sign(body)))
                        with self.assertRaises(EvidenceFailure): replay_delivery(root, run, signer.public)
                    else:
                        self.assertFalse((run/'zero-model-builder-inbox.json').exists())

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
