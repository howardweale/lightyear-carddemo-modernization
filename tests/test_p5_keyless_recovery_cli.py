"""CI-only abrupt-kill regression for journal sinks and abort-only CLI.

Synthetic identity/ledger data grants no run authority. No keys, signing,
provider calls, Tower service, or admission bypass is used. This tests the
journal/recovery boundary, not a fully admitted controller execution.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

from lightyear_factory.contracts import canonical_hash
from lightyear_factory.ledger import RunLedger
from lightyear_factory.orchestrator import FactoryOrchestrator, _ControllerAttemptLease


RUN = 'keyless-recovery'
ORDER, NONCE, WORKSPACE = '1' * 64, '2' * 64, '3' * 64


def flush_file(path, raw):
    with path.open('wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def checkpoint(journal, identity, calls):
    value = dict(schema='factory-sanitized-accounting/1', calls=calls,
                 input_tokens=7*calls, output_tokens=3*calls,
                 estimated_cost_usd=.00022*calls, duration_ms=0,
                 duration_basis='observed-through-checkpoint',
                 call_hashes=[dict(request_sha256='c'*64, response_sha256='e'*64)]*calls,
                 scanned_transports=[], in_flight_final_usage='none', billing_final=False)
    journal.append('OBSERVED', 'sanitized_accounting',
                   dict(attempt_identity_sha256=identity, accounting=value))
    with journal.path.open('ab') as stream:
        os.fsync(stream.fileno())


def physical(call):
    return dict(invocation=dict(call_sequence=call, invocation_sha256='b'*64),
                bounds=dict(input_tokens=999, output_tokens=16, estimated_cost_usd=.01079,
                            cost_estimate_available=True),
                provider='openai-responses', model='synthetic-no-provider',
                role='planner' if call == 1 else 'builder', transport_kind='responses',
                provider_attempt=1, request_sha256='d'*64, request_bytes=99,
                canonical_request_sha256='c'*64,
                pricing=dict(input_usd_per_million=10, output_usd_per_million=50))


def child(root, stage):
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('CI only')
    root = Path(root)
    run = root / RUN
    run.mkdir(parents=True)
    with _ControllerAttemptLease(root, RUN, create=True):
        identity = dict(schema='factory-attempt-identity/1', attempt_id=RUN,
                        work_order_sha256=ORDER, consumed_nonce_sha256=NONCE,
                        sealed_workspace_sha256=WORKSPACE,
                        admission_receipt_sha256='4'*64, workspace_inventory_sha256='5'*64)
        identity['content_sha256'] = canonical_hash(identity)
        flush_file(run/'attempt-identity.json', json.dumps(identity).encode())
        flush_file(root/'admission-nonces.sha256', (NONCE+'\n').encode())
        events = RunLedger(run/'events.jsonl')
        events.append('READY', 'work_order_accepted', dict(work_order_sha256=ORDER))
        events.append('READY', 'hardened_admission_bound', dict(admission_receipt_sha256='4'*64))
        events.append('READY', 'workspace_read_manifest', dict(sha256='5'*64))
        controller = FactoryOrchestrator.__new__(FactoryOrchestrator)
        controller._receipt_identity = identity
        controller._receipt_journal = RunLedger(run/'attempt-accounting.jsonl')
        journal = controller._receipt_journal
        journal.append('READY', 'model_reservations',
                       dict(attempt_identity_sha256=identity['content_sha256'], protocol=2))
        checkpoint(journal, identity['content_sha256'], 0)
        if stage != 'before-reserve':
            first = controller._reserve_model_transport(physical(1))
            # Reload before the stub boundary; the real sink must have completed.
            assert RunLedger(journal.path).events[-1]['event_sha256'] == first['reservation_event_sha256']
            flush_file(root/'stub-sends.json', json.dumps([first]).encode())
            controller._observe_model_transport(first, dict(outcome='returned',
                response_usage=dict(input_tokens=7, output_tokens=3), estimated_cost_usd=.00022,
                cost_estimate_available=True, failure_type=None))
            checkpoint(journal, identity['content_sha256'], 1)
            second = controller._reserve_model_transport(physical(2))
            assert RunLedger(journal.path).events[-1]['event_sha256'] == second['reservation_event_sha256']
            if stage == 'after-send':
                flush_file(root/'stub-sends.json', json.dumps([first, second]).encode())
        flush_file(root/'ready', stage.encode())
        # Parent kills this process while the actual OS lease is held.
        while True:
            time.sleep(.05)


class KeylessRecoveryCLITests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')
        self.temp = tempfile.TemporaryDirectory(prefix='p5-keyless-recovery-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def kill_at(self, stage):
        process = subprocess.Popen([sys.executable, '-B', str(Path(__file__).resolve()),
                                    '--child', str(self.root), stage],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 20
            while not (self.root/'ready').exists():
                if process.poll() is not None:
                    self.fail(process.stderr.read().decode(errors='replace'))
                if time.monotonic() >= deadline:
                    self.fail('child did not reach requested boundary')
                time.sleep(.02)
            process.kill()
            process.wait(timeout=10)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)
            process.stderr.close()

    def recover(self, order=ORDER):
        return subprocess.run([sys.executable, '-B', '-m', 'lightyear_factory.cli',
            'reconcile-interrupted', '--runs-root', str(self.root), '--run-id', RUN,
            '--work-order-sha256', order, '--consumed-nonce-sha256', NONCE,
            '--sealed-workspace-sha256', WORKSPACE], text=True, capture_output=True, timeout=20)

    def test_kill_before_reservation_has_no_stub_send_and_no_invented_usage(self):
        self.kill_at('before-reserve')
        self.assertFalse((self.root/'stub-sends.json').exists())
        result = self.recover()
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        payload = json.loads(result.stdout)['payload']
        accounting = payload['accounting']
        self.assertEqual(accounting['calls'], 0)
        self.assertEqual(accounting['model_transport_accounting'], [])
        self.assertNotIn('reserved_in_flight', accounting)
        self.assertFalse(accounting['billing_final'])
        self.assertTrue(payload['unsigned'])
        self.assertFalse(payload['resume_allowed'])
        self.assertFalse(payload['retry_allowed'])

    def test_kill_after_reserve_before_stub_send_retains_completed_usage_and_bound(self):
        self.kill_at('after-reserve')
        self.check_pending(expected_sends=1)

    def test_kill_after_stub_send_before_response_retains_exact_ticket(self):
        self.kill_at('after-send')
        self.check_pending(expected_sends=2)

    def check_pending(self, expected_sends):
        run = self.root/RUN
        accounting_before = (run/'attempt-accounting.jsonl').read_bytes()
        nonce_before = (self.root/'admission-nonces.sha256').read_bytes()
        events_before = (run/'events.jsonl').read_bytes()
        refused = self.recover(order='f'*64)
        self.assertEqual(refused.returncode, 1)
        self.assertEqual((run/'events.jsonl').read_bytes(), events_before)
        result = self.recover()
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        payload = json.loads(result.stdout)['payload']
        value = payload['accounting']
        self.assertEqual(value['calls'], 1)
        self.assertEqual((value['input_tokens'], value['output_tokens'], value['estimated_cost_usd']), (7, 3, .00022))
        self.assertEqual(value['in_flight_final_usage'], 'unknown; reserved upper bound recorded')
        pending = value['reserved_in_flight']
        self.assertEqual((pending['input_tokens'], pending['output_tokens'], pending['estimated_cost_usd']), (999, 16, .01079))
        self.assertEqual(pending['reservation_ticket']['transport_sequence'], 2)
        self.assertEqual(pending['request_sha256'], 'd'*64)
        self.assertEqual(value['model_transport_accounting'][0]['observation']['response_usage'], dict(input_tokens=7, output_tokens=3))
        self.assertEqual(value['invoice_reconciliation'], "The actual cost will be reconciled by Howard from the provider's invoice.")
        self.assertFalse(value['billing_final'])
        self.assertTrue(payload['unsigned'])
        self.assertIsNone(payload['human_attestation'])
        for field in ('qualifies_for_factory_receipt', 'resume_allowed', 'retry_allowed', 'new_admission_allowed'):
            self.assertFalse(payload[field])
        self.assertEqual(len(json.loads((self.root/'stub-sends.json').read_bytes())), expected_sends)
        self.assertEqual((run/'attempt-accounting.jsonl').read_bytes(), accounting_before)
        self.assertEqual((self.root/'admission-nonces.sha256').read_bytes(), nonce_before)
        after = (run/'events.jsonl').read_bytes()
        self.assertTrue(after.startswith(events_before))
        self.assertEqual(self.recover().returncode, 1)
        self.assertEqual((run/'events.jsonl').read_bytes(), after)
        self.assertTrue(RunLedger(run/'events.jsonl').verify())


if __name__ == '__main__':
    if len(sys.argv) == 4 and sys.argv[1] == '--child':
        child(sys.argv[2], sys.argv[3])
    else:
        unittest.main()
