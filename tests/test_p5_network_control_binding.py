"""CI-only control/denial binding tests; OCI process result is synthetic here."""
import copy
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from lightyear_execution.backend import ExecutionResult, OCIContainerBackend
from lightyear_execution.contracts import ExecutionPolicy
from tools.ci import p5_additional_controller_drills as additional
from tools.ci import p5_controller_network as probe

ROOT = Path(__file__).resolve().parents[1]


class NetworkControlBindingTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')
        no_network = patch('socket.create_connection', side_effect=AssertionError('network forbidden'))
        no_network.start(); self.addCleanup(no_network.stop)

    def fixture(self):
        policy = ExecutionPolicy.load(ROOT/'factory/execution/policy.json')
        command = ('python3', '-c', 'raise SystemExit(42)', '172.17.0.1', '12345')
        def observed(backend, command, root, environment, timeout):
            _, plan = backend.build_invocation(command, root, environment)
            return ExecutionResult(42, False, 1, b'', b'',
                                   {**plan, 'enforced': True, 'runtime_binary_sha256': '2'*64})
        with tempfile.TemporaryDirectory() as temp, patch.object(OCIContainerBackend, 'execute', observed):
            controller = probe.observe(Path(temp)/'controller', policy, command)
        argv = ['docker', 'run', '--rm', '--network', 'bridge', '--read-only',
                '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true',
                '--user', policy.run_as_user, policy.image_reference, *command]
        completed = SimpleNamespace(args=argv, returncode=0, stdout=b'', stderr=b'')
        value = dict(controller=controller, positive_before=additional.retain_control(completed),
                     positive_after=additional.retain_control(completed))
        self.assertTrue(probe.validate(controller))
        return value, policy

    def test_same_controller_gate_and_both_controls_bind_without_qualification(self):
        value, policy = self.fixture()
        self.assertTrue(additional.network_controls_valid(value, policy))
        self.assertFalse(value['controller']['production_controller_receipt'])
        self.assertFalse(value['controller']['signing'])

    def test_successful_controls_with_different_experiment_or_security_flags_refuse(self):
        value, policy = self.fixture()
        for position, replacement in [(-1, '12346'), (-2, '127.0.0.1'),
                (-3, 'pass'), (-6, 'wrong-image'), (4, 'host'), (5, '--privileged'),
                (11, '0')]:
            for name in ('positive_before', 'positive_after'):
                with self.subTest(position=position, name=name):
                    wrong = copy.deepcopy(value)
                    wrong[name]['argv'][position] = replacement
                    self.assertFalse(additional.network_controls_valid(wrong, policy))
        wrong = copy.deepcopy(value)
        wrong['positive_after']['argv'].append('--unexpected')
        self.assertFalse(additional.network_controls_valid(wrong, policy))

    def test_bad_control_bytes_exit_and_controller_receipt_are_not_denial_proof(self):
        value, policy = self.fixture()
        for name in ('positive_before', 'positive_after'):
            for exit_code in (42, True, None):
                with self.subTest(name=name, exit_code=exit_code):
                    wrong = copy.deepcopy(value); wrong[name]['exit_code'] = exit_code
                    self.assertFalse(additional.network_controls_valid(wrong, policy))
            for stream in ('stdout', 'stderr'):
                wrong = copy.deepcopy(value); wrong[name][stream]['sha256'] = '0'*64
                self.assertFalse(additional.network_controls_valid(wrong, policy))
                wrong = copy.deepcopy(value); wrong[name][stream]['bytes'] = True
                self.assertFalse(additional.network_controls_valid(wrong, policy))
                wrong = copy.deepcopy(value); wrong[name][stream]['base64'] = '!'
                self.assertFalse(additional.network_controls_valid(wrong, policy))
        wrong = copy.deepcopy(value); wrong['controller']['receipt']['sha256'] = '0'*64
        self.assertFalse(additional.network_controls_valid(wrong, policy))
        wrong = copy.deepcopy(value); del wrong['positive_after']
        self.assertFalse(additional.network_controls_valid(wrong, policy))
