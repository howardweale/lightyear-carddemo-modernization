"""CI-only synthetic transport/account tests; no provider or account access."""
import copy
from decimal import Decimal
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lightyear_factory.contracts import ContractError, canonical_hash
from lightyear_factory.count_charge_account import CountChargeAccount, CountInputBound, CountChargeJournalError, replay_count_charges
from lightyear_factory.flex_billing import flex_billing_policy
from lightyear_factory.model_config import configured_models
from lightyear_factory.providers import OpenAIResponsesProvider


class FlexCountBillingTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')
        self.policy = flex_billing_policy()
        self.events = []
        self.other = Decimal('1')  # Synthetic generation exposure, not an account rate.
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.log = Path(self.temp.name)/'synthetic-count-events.jsonl'

        def append(event):
            with self.log.open('ab') as stream:
                stream.write((json.dumps(event, sort_keys=True)+'\n').encode())
                stream.flush(); os.fsync(stream.fileno())
            self.events.append(copy.deepcopy(event))

        self.append = append
        self.book = self.new_book(append)
        self.calls = []
        self.tier = 'flex'
        self.count = 17
        self.count_failure = None
        guard = patch('urllib.request.urlopen', side_effect=AssertionError('real network forbidden'))
        guard.start(); self.addCleanup(guard.stop)

    def new_book(self, append):
        return CountChargeAccount(self.policy, cap_usd='10', attempt_identity_sha256='a'*64,
            other_exposure_usd=lambda: self.other, durable_append=append)

    def bound(self, raw, tokens=100):
        return CountInputBound(hashlib.sha256(raw).hexdigest(), tokens, 'b'*64)

    def opener(self, request, **kwargs):
        body = json.loads(request.data)
        self.calls.append((request.full_url, body))
        if request.full_url.endswith('/input_tokens'):
            retained = [json.loads(line) for line in self.log.read_bytes().splitlines()]
            self.assertEqual(retained[-1]['kind'], 'count_charge_reserved')
            self.assertEqual(retained[-1]['request_sha256'], hashlib.sha256(request.data).hexdigest())
            self.assertNotIn('service_tier', body)  # No undocumented count-endpoint parameter.
            if self.count_failure:
                raise self.count_failure
            return io.BytesIO(json.dumps({'input_tokens': self.count}).encode())
        retained = [json.loads(line) for line in self.log.read_bytes().splitlines()]
        self.assertEqual(retained[-1]['kind'], 'count_charge_observed')
        self.assertEqual(body['service_tier'], 'flex')
        self.assertEqual(request.full_url, 'https://api.openai.com/v1/responses')
        return io.BytesIO(json.dumps(dict(model='gpt-5.4-2026-03-05', service_tier=self.tier,
            output=[{'content':[{'type':'output_text','text':'{"ok":true}'}]}],
            usage={'input_tokens':17,'output_tokens':4})).encode())

    def provider(self, **changes):
        args = dict(api_key='synthetic-credential', model='gpt-5.4-2026-03-05',
            opener=self.opener, input_usd_per_million=5.5, output_usd_per_million=24.75,
            max_retries=0, token_preflight=True, service_tier='flex', billing_policy=self.policy,
            count_account=self.book, count_bound_resolver=self.bound)
        args.update(changes)
        return OpenAIResponsesProvider(**args)

    def complete(self, provider):
        return provider.complete('planner', 'Return a public synthetic control.', {},
                                 {'type':'object','properties':{'ok':{'type':'boolean'}},'required':['ok']})

    def test_explicit_flex_wire_and_cited_receipt_with_durable_count_charge(self):
        result = self.complete(self.provider())
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(result.evidence['billing_policy']['rate_card_url'], self.policy['rate_card_url'])
        self.assertEqual(result.evidence['billing_policy']['observed_service_tier'], 'flex')
        self.assertIs(result.evidence['billing_policy']['billing_final'], False)
        self.assertEqual(self.book.snapshot()['count_exposure_usd'], str(Decimal(17)*Decimal('5.50')/1000000))
        self.assertEqual(self.events[1]['released_excess_usd'], str(Decimal(83)*Decimal('5.50')/1000000))
        self.assertIsNone(self.events[1]['provider_billed_cost_usd'])
        self.assertEqual(result.evidence['content_sha256'], canonical_hash(result.evidence, {'content_sha256'}))

    def test_wrong_tier_missing_policy_price_mutation_and_retry_refuse(self):
        for changes in ({'service_tier':'auto'}, {'service_tier':'priority'}, {'service_tier':None},
                        {'max_retries':1}, {'token_preflight':False}, {'input_usd_per_million':5},
                        {'output_usd_per_million':15}):
            with self.subTest(changes=changes), self.assertRaises(ContractError):
                self.provider(**changes)
        bad = copy.deepcopy(self.policy); bad['reasoning_included_in_output'] = 1
        with self.assertRaises(ContractError):
            self.provider(billing_policy=bad)
        self.assertEqual(self.calls, [])

    def test_configured_loader_keeps_binding_and_refuses_without_controller_sink(self):
        class SyntheticBroker:
            def read(self, name):
                return 'synthetic-credential'
        cfg = {'models':{'copau':dict(provider='openai',model='gpt-5.4-2026-03-05',
            input_usd_per_million=5.5,output_usd_per_million=24.75,max_output_tokens=25000,
            service_tier='flex',billing_policy=self.policy)}}
        provider = configured_models(cfg, secret_store=SyntheticBroker())['copau']
        provider.opener = lambda *a, **k: self.fail('must refuse before count transport')
        with self.assertRaisesRegex(ContractError, 'integration-required-before-send'):
            self.complete(provider)
        del cfg['models']['copau']['billing_policy']
        with self.assertRaises(ValueError):
            configured_models(cfg, secret_store=SyntheticBroker())

    def test_response_tier_mismatch_refuses_after_retaining_count_charge(self):
        self.tier = 'priority'
        with self.assertRaisesRegex(ContractError, 'response-tier-mismatch'):
            self.complete(self.provider())
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.book.snapshot()['calls'][0]['state'], 'counted-conservative-charge')

    def test_shared_cap_refuses_count_before_any_send(self):
        self.other = Decimal('9.9995')
        with self.assertRaisesRegex(ContractError, 'shared-cap'):
            self.complete(self.provider())
        self.assertEqual(self.calls, [])
        self.assertEqual(self.events, [])

    def test_reserve_fsync_failure_poisoning_prevents_transport_and_reuse(self):
        def fail(event):
            raise TimeoutError('synthetic fsync failure')
        self.book = self.new_book(fail)
        with self.assertRaises(CountChargeJournalError):
            self.complete(self.provider())
        with self.assertRaises(ContractError):
            self.book.reserve(b'count', self.bound(b'count'))
        self.assertEqual(self.calls, [])

    def test_unknown_failed_count_stays_held_without_retry_or_generation(self):
        self.count_failure = TimeoutError('synthetic count transport interruption')
        with self.assertRaises(ContractError):
            self.complete(self.provider())
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.book.snapshot()['calls'][0]['state'], 'observed-unknown-held')
        self.assertEqual(self.book.snapshot()['count_exposure_usd'], '0.00055')
        self.assertEqual(self.events[1]['released_excess_usd'], '0')
        self.assertIs(self.book.snapshot()['billing_final'], False)

    def test_bad_count_and_exceeded_bound_never_generate_or_erase_cost(self):
        self.count = True
        with self.assertRaises(ContractError):
            self.complete(self.provider())
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.book.snapshot()['count_exposure_usd'], '0.00055')
        self.calls.clear(); self.count = 101
        with self.assertRaisesRegex(ContractError, 'bound-or-cap-exceeded'):
            self.complete(self.provider())
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.book.snapshot()['calls'][-1]['charge_usd'], '0.0005555')
        self.assertTrue(self.book.snapshot()['stopped'])

    def test_replay_retains_unobserved_and_failed_holds_plus_completed_charge(self):
        first = self.book.reserve(b'one', self.bound(b'one'))
        self.book.observe(first, 20)
        second = self.book.reserve(b'two', self.bound(b'two'))
        self.book.observe(second, None)
        self.book.reserve(b'three', self.bound(b'three'))
        report = replay_count_charges(self.events, self.policy, cap_usd='10', attempt_identity_sha256='a'*64)
        self.assertEqual(report['count_exposure_usd'], str(Decimal(220)*Decimal('5.50')/1000000))
        self.assertEqual(report['calls'], self.book.snapshot()['calls'])
        self.assertIs(report['resume_authorized'], False)
        self.assertIs(report['billing_final'], False)

    def test_replay_tampered_rehashed_charge_binding_and_duplicate_refuse(self):
        ticket = self.book.reserve(b'one', self.bound(b'one')); self.book.observe(ticket, 20)
        for field, value in {'conservative_charge_usd':'0', 'released_excess_usd':'0',
                             'billing_final':True, 'attempt_identity_sha256':'c'*64,
                             'provider_billed_usage':20}.items():
            changed = copy.deepcopy(self.events); changed[1][field] = value
            changed[1]['content_sha256'] = canonical_hash(changed[1], {'content_sha256'})
            with self.subTest(field=field), self.assertRaises(ContractError):
                replay_count_charges(changed, self.policy, cap_usd='10', attempt_identity_sha256='a'*64)
        with self.assertRaises(ContractError):
            replay_count_charges(self.events+[self.events[1]], self.policy, cap_usd='10', attempt_identity_sha256='a'*64)

    def test_settlement_fsync_failure_does_not_release_in_memory(self):
        def fail_on_observe(event):
            if event['kind'] == 'count_charge_observed':
                raise OSError('synthetic settlement fsync error')
            self.append(event)
        book = self.new_book(fail_on_observe)
        ticket = book.reserve(b'one', self.bound(b'one'))
        with self.assertRaises(CountChargeJournalError):
            book.observe(ticket, 20)
        self.assertEqual(book.snapshot()['count_exposure_usd'], '0.00055')
        self.assertTrue(book.snapshot()['stopped'])


if __name__ == '__main__':
    unittest.main()
