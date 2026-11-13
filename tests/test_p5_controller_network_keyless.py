"""CI regression for the real controller/gate receipt; no authority or keys."""
import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lightyear_execution.backend import ExecutionResult, OCIContainerBackend
from lightyear_execution.contracts import ExecutionPolicy, canonical_hash
from lightyear_factory.contracts import GateContract
from lightyear_factory.gates import GateRunner
from tools.ci import p5_controller_network as probe

ROOT = Path(__file__).resolve().parents[1]


class KeylessControllerNetworkTests(unittest.TestCase):
    def test_real_gate_result_has_a_verifiable_execution_hash(self):
        policy = ExecutionPolicy.load(ROOT/'factory/execution/policy.json')
        backend = OCIContainerBackend(policy, 'docker', execute=False)
        with tempfile.TemporaryDirectory() as temp:
            report = GateRunner(Path(temp), backend=backend).run((
                GateContract.from_dict(dict(id='hash-control', command=['python3', '-c', 'pass'], timeout_seconds=5, expose_output_to_builder=False)),))
        execution = report['gates'][0]['execution']
        # This must fail on the current double-hashed production result, not be waived.
        self.assertEqual(execution['content_sha256'], canonical_hash(execution, {'content_sha256'}))

    def test_controller_retains_failed_gate_and_blocks_without_fabricating_admission(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')
        policy = ExecutionPolicy.load(ROOT/'factory/execution/policy.json')
        command = ('python3', '-c', 'raise SystemExit(42)', '172.17.0.1', '12345')
        def observed(backend, command, root, environment, timeout):
            _, plan = backend.build_invocation(command, root, environment)
            return ExecutionResult(42, False, 1, b'', b'', {**plan, 'enforced': True, 'runtime_binary_sha256': '2'*64})
        with tempfile.TemporaryDirectory() as temp, patch.object(OCIContainerBackend, 'execute', observed):
            value = probe.observe(Path(temp)/'controller', policy, command)
        self.assertEqual(value['scripted_roles'], ['planner', 'failure_analyst', 'builder'])
        self.assertFalse(value['production_controller_receipt'])
        # Real controller/runner path; only OCI process output is synthetic in this unit test.
        self.assertTrue(probe.validate(value))
        wrong = copy.deepcopy(value); wrong['scripted_roles'] = ['builder']
        with self.assertRaises(ValueError): probe.validate(wrong)

    def test_non_ci_refuses_before_any_execution_or_creation(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'GITHUB_ACTIONS': 'false'}):
            target = Path(temp)/'untouched'
            with self.assertRaisesRegex(ValueError, 'ci-only'): probe.observe(target, None, ())
            self.assertFalse(target.exists())
