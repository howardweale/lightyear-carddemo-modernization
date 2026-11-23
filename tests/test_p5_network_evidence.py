"""Network evidence retention and fail-closed collector controls; no socket/OCI in tests."""
import copy
import hashlib
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools.ci import p5_drills as drills
from tools.ci import p5_network_evidence as evidence


def result(command):
    plan = dict(backend='oci-docker', assurance='enforced', image='image@sha256:'+'1'*64,
                network_mode='none', command=list(command), read_only_root=True,
                workspace_read_only=True, cap_drop_all=True, no_new_privileges=True)
    plan['content_sha256'] = hashlib.sha256(evidence.canonical(plan)).hexdigest()
    plan.update(runtime_binary_sha256='2'*64, enforced=True)
    return SimpleNamespace(exit_code=42, timed_out=False, duration_ms=1, stdout=b'', stderr=b'', evidence=plan)


class NetworkEvidenceTests(unittest.TestCase):
    def packet(self):
        policy = SimpleNamespace(content_sha256='3'*64, image_reference='image@sha256:'+'1'*64)
        code = 'public synthetic test'; command = ['python3', '-c', code, '172.17.0.1', '12345']
        positive = SimpleNamespace(args=['docker', 'run', '--rm', '--network', 'bridge', '--read-only', policy.image_reference, *command], returncode=0, stdout=b'public-output', stderr=b'')
        return evidence.retain(positive, result(command), positive, policy, code, command[-2], 12345)

    def test_full_outputs_command_plan_and_two_controls_are_retained(self):
        packet = self.packet()
        self.assertTrue(evidence.validate(packet))
        self.assertEqual(packet['positive_before']['stdout']['sha256'], hashlib.sha256(b'public-output').hexdigest())
        self.assertEqual(packet['positive_before'], packet['positive_after'])
        self.assertFalse(packet['production_controller_receipt'])

    def test_wrong_failure_timeout_and_rehashed_false_plan_are_rejected(self):
        packet = self.packet()
        for mutation in ('before', 'after', 'exit', 'timeout', 'network', 'command', 'output', 'qualifies', 'plan'):
            bad = copy.deepcopy(packet)
            if mutation in ('before', 'after'): bad['positive_'+mutation]['exit_code'] = 42
            elif mutation == 'exit': bad['isolated']['exit_code'] = 127
            elif mutation == 'timeout': bad['isolated']['timed_out'] = True
            elif mutation == 'output': bad['isolated']['stdout']['sha256'] = '0'*64
            elif mutation == 'qualifies': bad['production_controller_receipt'] = True
            else:
                plan = bad['isolated']['evidence']
                if mutation == 'network': plan['network_mode'] = 'bridge'
                elif mutation == 'command': plan['command'][-1] = '12346'
                else: plan['content_sha256'] = '0'*64
                if mutation != 'plan':
                    content = {k:v for k,v in plan.items() if k not in ('content_sha256', 'enforced', 'runtime_binary_sha256')}
                    plan['content_sha256'] = hashlib.sha256(evidence.canonical(content)).hexdigest()
                bad['isolated']['evidence_sha256'] = hashlib.sha256(evidence.canonical(plan)).hexdigest()
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): evidence.validate(bad)

    def test_collector_runs_restored_control_and_retains_without_changing_gap(self):
        policy = SimpleNamespace(content_sha256='3'*64, image_reference='image@sha256:'+'1'*64, run_as_user='65534:65534')
        fixture = SimpleNamespace(runtime=lambda: None, verify_order=lambda: None, policy=policy, root='/unused-test-root')
        server = SimpleNamespace(server_address=('0.0.0.0', 12345), serve_forever=lambda: None, shutdown=lambda: None, server_close=lambda: None)
        backend = SimpleNamespace(execute=lambda command, *args: result(command))
        calls = []
        def completed(argv, **kwargs):
            calls.append(list(argv))
            return SimpleNamespace(args=argv, returncode=0, stdout=b'', stderr=b'')
        with patch.object(drills.socketserver, 'ThreadingTCPServer', return_value=server), patch.object(drills.threading, 'Thread'), patch.object(drills.subprocess, 'check_output', return_value=json.dumps([{'IPAM': {'Config': [{'Gateway': '172.17.0.1'}]}}]).encode()), patch.object(drills.subprocess, 'run', completed), patch.object(drills, 'OCIContainerBackend', return_value=backend):
            observed, matched, gaps = drills.worker_network(fixture)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0], calls[1])
        self.assertIs(matched, True)
        self.assertTrue(evidence.validate(observed['retained_network_evidence']))
        self.assertEqual(gaps, ['OCI denial is measured directly; the factory controller post-denial receipt path is not exercised.'])


    def test_positive_timeout_retains_only_stage_and_never_retries(self):
        import subprocess
        for stage in ('positive-before', 'positive-after'):
            failure = subprocess.TimeoutExpired(['private-command-not-retained'], 30,
                output=b'private-output-not-retained', stderr=b'private-stderr-not-retained')
            with self.subTest(stage=stage), patch.object(subprocess, 'run', side_effect=failure) as run:
                with self.assertRaises(evidence.NetworkControlTimeout) as caught:
                    evidence.run_positive_control(stage, ['public-fixture'])
                run.assert_called_once_with(['public-fixture'], stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, timeout=30, check=False)
                diagnostic = evidence.timeout_diagnostic(caught.exception)
                self.assertEqual(diagnostic, dict(schema='p5-network-timeout-diagnostic/1',
                    stage=stage, timeout_seconds=30, accepted_drill_result=False))
                self.assertNotIn('private', json.dumps(diagnostic))

    def test_timeout_diagnostic_refuses_untyped_or_mutated_errors(self):
        self.assertIsNone(evidence.timeout_diagnostic(TimeoutError('positive-before')))
        for stage in ('isolated-worker', '', None):
            with self.subTest(stage=stage), self.assertRaises(ValueError):
                evidence.NetworkControlTimeout(stage)
        error = evidence.NetworkControlTimeout('positive-before')
        error.stage = 'untrusted-message'
        self.assertIsNone(evidence.timeout_diagnostic(error))

    def test_timeout_collector_retains_failure_and_does_not_qualify(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'observations'
            class NoAuthorityFixture:
                def __init__(self, *args):
                    self.envelope = {'signature': {'value': 'synthetic-invalid'}}
                def verify_order(self, **kwargs):
                    raise drills.ExecutionContractError('synthetic-negative-control')
            def fail(fixture):
                raise evidence.NetworkControlTimeout('positive-after')
            with patch.object(drills, 'Fixture', NoAuthorityFixture), patch.object(
                    drills, 'FUNCTIONS', {name: fail for name in drills.DRILLS}):
                # Drive the collector's actual failure path without creating authority.
                self.assertFalse(drills.collect(Path(__file__).resolve().parents[1], output))
            summary = json.loads((output/'summary.json').read_bytes())
            self.assertTrue(summary['complete'])
            self.assertTrue(drills.inventory_ok(summary['drills']))
            row = next(row for row in summary['drills'] if row['id'] == 'worker-network')
            self.assertTrue(row['harness_error'])
            self.assertFalse(row['expectation_met'])
            self.assertEqual(row['gaps'], ['Harness incomplete; no accepted drill result.'])
            self.assertEqual(row['network_timeout_diagnostic']['stage'], 'positive-after')
            self.assertFalse(row['network_timeout_diagnostic']['accepted_drill_result'])
            self.assertTrue(all('network_timeout_diagnostic' not in other
                for other in summary['drills'] if other['id'] != 'worker-network'))
            self.assertFalse(drills.qualify(output))
