"""Configured-loader/transport components, not admitted Factory.run evidence."""
from decimal import Decimal
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import urllib.request

from lightyear_factory.contracts import ContractError, canonical_hash
from lightyear_factory.controller_count_accounting import bind_controller_counts
from lightyear_factory.count_request_bound import request_bound_basis
from lightyear_factory.flex_billing import flex_billing_policy
from lightyear_factory.ledger import RunLedger
from lightyear_factory.model_config import load_router
from lightyear_factory.orchestrator import FactoryOrchestrator, _reconcile_accounting_journal
from lightyear_factory.transport_journal import TransportJournalError


class ConfiguredCountComponentTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')
        no_network = patch('socket.create_connection', side_effect=AssertionError('network forbidden'))
        no_network.start(); self.addCleanup(no_network.stop)

    def fixture(self, returned_model='gpt-5.4-2026-03-05', directory=None):
        if directory is None:
            temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
            root = Path(temporary.name)
        else:
            root = Path(directory)
        config = dict(default='public-fixture', models={'public-fixture': dict(
            provider='openai', model='gpt-5.4-2026-03-05', input_usd_per_million=5.5,
            output_usd_per_million=24.75, max_output_tokens=16,
            service_tier='flex', billing_policy=flex_billing_policy())})
        config_path = root/'models.json'
        config_path.write_text(json.dumps(config), encoding='utf-8')
        leases = []
        class PublicSyntheticBroker:
            def read(self, name):
                if name != 'OPENAI_API_KEY':
                    raise AssertionError('unexpected fixture lease')
                leases.append(name)
                return 'public-synthetic-not-a-credential'
        router = load_router(config_path, secret_store=PublicSyntheticBroker())
        order = SimpleNamespace(metadata={}, max_model_cost_usd=10, max_elapsed_seconds=60)
        routed = router.bind_order(order)
        provider = router.providers['public-fixture']
        self.assertIs(provider._transport_opener, urllib.request.urlopen)
        self.assertEqual(provider.max_retries, 0)
        self.assertEqual(provider.service_tier, 'flex')
        self.assertTrue(provider.manage_failure_budget)
        self.assertEqual(leases, ['OPENAI_API_KEY'])
        controller = FactoryOrchestrator.__new__(FactoryOrchestrator)
        controller.agents = SimpleNamespace(bounded_provider=routed)
        controller._receipt_identity = {'content_sha256': 'a'*64}
        controller._receipt_journal = RunLedger(root/'attempt.jsonl')
        controller._receipt_started = time.monotonic()
        controller._receipt_transports = []; controller._receipt_pending = False
        header = bind_controller_counts(controller)
        controller._receipt_journal.append('READY', 'model_reservations', dict(
            attempt_identity_sha256='a'*64, protocol=5, **header))
        controller._checkpoint_accounting(); controller._bind_reservation_journal()
        instruction = 'Public configured component.'
        schema = dict(type='object', properties={'ok': {'type': 'boolean'}})
        digest = canonical_hash(dict(instruction=instruction, payload={}, schema=schema))
        controller._reserve_model_call(dict(call_sequence=1, role='planner', request_sha256=digest,
            invocation_sha256=digest, input_tokens=100, output_tokens=16,
            estimated_cost_usd=(100*5.5+16*24.75)/1000000))
        sends = []
        def opened(director, request, *args, **kwargs):
            journal = RunLedger(controller._receipt_journal.path)
            self.assertTrue(journal.verify())
            last = journal.events[-1]
            self.assertEqual(last['kind'], 'model_transport_reserved')
            physical = last['payload']['reservation']
            self.assertEqual(physical['request_sha256'], hashlib.sha256(request.data).hexdigest())
            sends.append(dict(url=request.full_url, reservation=physical))
            if request.full_url.endswith('/input_tokens'):
                rows = [e['payload']['event'] for e in journal.events if e['kind']=='count_financial']
                self.assertEqual(rows[-1]['kind'], 'count_charge_reserved')
                self.assertEqual(rows[-1]['bound_basis'], request_bound_basis(request.data))
                self.assertEqual(rows[-1]['reserved_input_tokens'], 2*len(request.data)+2048)
                value = dict(input_tokens=17)
            else:
                self.assertEqual(physical['input_token_preflight']['input_tokens'], 17)
                self.assertEqual(json.loads(request.data)['service_tier'], 'flex')
                value = dict(model=returned_model, status='completed', service_tier='flex',
                    output=[dict(content=[dict(type='output_text', text='{"ok":true}')])],
                    usage=dict(input_tokens=17, output_tokens=1))
            response = io.BytesIO(json.dumps(value).encode()); response.headers = {}; return response
        stub = patch.object(urllib.request.OpenerDirector, 'open', opened)
        stub.start(); self.addCleanup(stub.stop)
        invoke = lambda: routed.budget._complete_with_transport_journal(
            'planner', instruction, {}, schema, 100, 16, 5.5, 24.75)
        return controller, routed, sends, invoke, instruction, schema

    def test_configured_snapshot_adapter_retains_count_before_generation(self):
        controller, routed, sends, invoke, _, _ = self.fixture()
        result = invoke()
        self.assertEqual(result.content, {'ok': True})
        self.assertEqual([s['reservation']['transport_kind'] for s in sends],
                         ['input-token-count', 'responses'])
        report = _reconcile_accounting_journal(controller._receipt_journal.events, 'a'*64)
        self.assertEqual(report['count_financial_accounting']['count_account']['count_exposure_usd'], '0.0000935')
        self.assertFalse(report['billing_final'])
        self.assertNotIn('unresolved_model_transports', report)
        self.assertIs(routed.budget.provider._transport_opener, urllib.request.urlopen)

    def test_configured_physical_reservation_failure_sends_nothing(self):
        controller, routed, sends, invoke, _, _ = self.fixture()
        def fail(record):
            raise OSError('public synthetic journal failure')
        routed.budget.transport_reservation_checkpoint = fail
        with self.assertRaises(TransportJournalError):
            invoke()
        self.assertEqual(sends, [])
        self.assertFalse(any(e['kind']=='model_transport_reserved' for e in controller._receipt_journal.events))
        report = _reconcile_accounting_journal(controller._receipt_journal.events, 'a'*64)
        account = report['count_financial_accounting']['count_account']
        self.assertTrue(account['stopped'])
        self.assertGreater(Decimal(account['count_exposure_usd']), 0)
        self.assertEqual(account['calls'][0]['state'], 'observed-unknown-held')

    def test_snapshot_refusal_keeps_reported_usage_and_count_charge(self):
        controller, routed, sends, invoke, _, _ = self.fixture('gpt-5.4')
        with self.assertRaisesRegex(ContractError, 'response model snapshot differs'):
            invoke()
        self.assertEqual(len(sends), 2)
        observations = [e['payload']['observation'] for e in controller._receipt_journal.events
                        if e['kind']=='model_transport_observed']
        self.assertEqual(observations[-1]['outcome'], 'failed')
        self.assertEqual(observations[-1]['response_usage'], dict(input_tokens=17, output_tokens=1))
        report = _reconcile_accounting_journal(controller._receipt_journal.events, 'a'*64)
        self.assertEqual(report['count_financial_accounting']['count_account']['count_exposure_usd'], '0.0000935')
        self.assertFalse(report['billing_final'])

    def test_complete_routed_call_without_genuine_admission_refuses_before_transport(self):
        controller, routed, sends, invoke, instruction, schema = self.fixture()
        original = controller._receipt_journal.path.read_bytes()
        with self.assertRaisesRegex(ContractError, 'factory-model-approval-required'):
            routed.complete('planner', instruction, {}, schema)
        self.assertEqual(sends, [])
        self.assertEqual(controller._receipt_journal.path.read_bytes(), original)


class ConfiguredCountExitTests(unittest.TestCase):
    """Abrupt configured-adapter components; no admission or Factory.run."""
    CHILD = r'''
import hashlib, json, os, runpy, sys
from pathlib import Path
from unittest.mock import patch
import urllib.request
assert os.environ.get('GITHUB_ACTIONS') == 'true'
namespace = runpy.run_path(sys.argv[1], run_name='configured_count_child')
case = namespace['ConfiguredCountComponentTests'](); case.setUp()
mode, directory = sys.argv[2], Path(sys.argv[3])
assert mode in {'before-count-reserve','after-count-reserve',
                'before-generation-reserve','after-generation-reserve','normal'}
controller, routed, sends, invoke, _, _ = case.fixture(directory=directory)
original_reserve = routed.budget.transport_reservation_checkpoint
original_open = urllib.request.OpenerDirector.open

def reserved(record):
    label = 'count' if record['transport_kind']=='input-token-count' else 'generation'
    if mode=='before-'+label+'-reserve': os._exit(86)
    result = original_reserve(record)
    if mode=='after-'+label+'-reserve': os._exit(86)
    return result

def recorded_open(director, request, *args, **kwargs):
    row = dict(kind='input-token-count' if request.full_url.endswith('/input_tokens') else 'responses',
               request_sha256=hashlib.sha256(request.data).hexdigest())
    with (directory/'stub-sends.jsonl').open('ab') as stream:
        stream.write((json.dumps(row,sort_keys=True)+'\n').encode());stream.flush();os.fsync(stream.fileno())
    return original_open(director, request, *args, **kwargs)

routed.budget.transport_reservation_checkpoint = reserved
with patch.object(urllib.request.OpenerDirector, 'open', recorded_open):
    result = invoke()
assert mode=='normal' and result.content=={'ok':True}
case.doCleanups()
'''

    def child(self, mode):
        import subprocess
        import sys
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, '-B', '-c', self.CHILD,
                str(Path(__file__).resolve()), mode, directory], capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0 if mode=='normal' else 86,
                             result.stderr.decode(errors='replace'))
            path = Path(directory)/'attempt.jsonl'
            original = path.read_bytes(); journal = RunLedger(path)
            self.assertTrue(journal.verify())
            self.assertEqual(journal.events[0]['payload']['protocol'], 5)
            self.assertEqual(journal.events[0]['payload']['count_bound_profile'], 'request-bytes-v1')
            report = _reconcile_accounting_journal(journal.events, 'a'*64)
            self.assertEqual(path.read_bytes(), original)
            send_path = Path(directory)/'stub-sends.jsonl'
            sends = [json.loads(line) for line in send_path.read_bytes().splitlines()] if send_path.exists() else []
            reservations = [e['payload']['reservation'] for e in journal.events
                            if e['kind']=='model_transport_reserved']
            for index, sent in enumerate(sends):
                self.assertEqual(sent['kind'], reservations[index]['transport_kind'])
                self.assertEqual(sent['request_sha256'], reservations[index]['request_sha256'])
            self.assertFalse(report['billing_final'])
            return journal.events, report, sends

    def test_configured_abrupt_reservation_boundaries_preserve_holds_and_send_counts(self):
        cases = [('before-count-reserve',0,0,0), ('after-count-reserve',1,0,0),
                 ('before-generation-reserve',1,1,1), ('after-generation-reserve',2,1,1)]
        for mode, reserved_count, observed_count, send_count in cases:
            with self.subTest(mode=mode):
                events, report, sends = self.child(mode)
                self.assertEqual(len(sends), send_count)
                self.assertEqual(sum(e['kind']=='model_transport_reserved' for e in events), reserved_count)
                self.assertEqual(sum(e['kind']=='model_transport_observed' for e in events), observed_count)
                finance = report['count_financial_accounting']; row = finance['count_account']['calls'][0]
                if send_count == 0:
                    self.assertEqual(row['state'], 'reserved-unknown')
                    self.assertEqual(row['charge_usd'], row['reserved_cost_usd'])
                    self.assertGreater(Decimal(row['charge_usd']), 0)
                else:
                    self.assertEqual([x['kind'] for x in sends], ['input-token-count'])
                    self.assertEqual(row['state'], 'counted-conservative-charge')
                    self.assertEqual(finance['count_account']['count_exposure_usd'], '0.0000935')
                    self.assertGreater(Decimal(finance['pending_generation_reserve_usd']), 0)
                self.assertEqual(report['calls'], 0)

    def test_configured_normal_child_observes_both_sends_without_authority(self):
        events, report, sends = self.child('normal')
        self.assertEqual([x['kind'] for x in sends], ['input-token-count','responses'])
        self.assertEqual(sum(e['kind']=='model_transport_reserved' for e in events), 2)
        self.assertEqual(sum(e['kind']=='model_transport_observed' for e in events), 2)
        self.assertNotIn('unresolved_model_transports', report)
        self.assertEqual(report['count_financial_accounting']['count_account']['count_exposure_usd'], '0.0000935')
