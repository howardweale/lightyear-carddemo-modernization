"""CI-only semantic replay tests; hash-valid synthetic journals, no transports."""
import copy
import os
from pathlib import Path
import tempfile
import unittest

from lightyear_factory.contracts import ContractError
from lightyear_factory.ledger import RunLedger
from lightyear_factory.orchestrator import _reconcile_accounting_journal

IDENTITY = 'a' * 64


def snapshot(calls=0, request='c' * 64):
    return dict(schema='factory-sanitized-accounting/1', calls=calls,
                input_tokens=7*calls, output_tokens=3*calls, estimated_cost_usd=.00022*calls,
                duration_ms=0, duration_basis='observed-through-checkpoint',
                call_hashes=[dict(request_sha256=request, response_sha256='e'*64)]*calls,
                scanned_transports=[], in_flight_final_usage='none', billing_final=False)


def reservation(call=1, attempt=1, kind='responses'):
    return dict(invocation=dict(call_sequence=call, invocation_sha256='b'*64),
                bounds=dict(input_tokens=999, output_tokens=16, estimated_cost_usd=.01079,
                            cost_estimate_available=True),
                provider='openai-responses', model='test-model', role='planner',
                transport_kind=kind, provider_attempt=attempt, request_sha256='d'*64,
                request_bytes=99, canonical_request_sha256='c'*64,
                pricing=dict(input_usd_per_million=10, output_usd_per_million=50))


def observation(failed=False, kind='responses'):
    counted = kind != 'input-token-count' and not failed
    return dict(outcome='failed' if failed else 'returned',
                response_usage=dict(input_tokens=7, output_tokens=3) if counted else None,
                estimated_cost_usd=.00022 if counted else None, cost_estimate_available=counted,
                failure_type='HTTPError' if failed else None)


class PhysicalReplayTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')
        self.temp = tempfile.TemporaryDirectory(prefix='p5-physical-replay-')
        self.addCleanup(self.temp.cleanup)
        self.serial = 0

    def journal(self, actions):
        self.serial += 1
        ledger = RunLedger(Path(self.temp.name)/str(self.serial))
        ledger.append('READY', 'model_reservations', dict(attempt_identity_sha256=IDENTITY, protocol=2))
        ledger.append('OBSERVED', 'sanitized_accounting', dict(attempt_identity_sha256=IDENTITY, accounting=snapshot()))
        ticket = None; sequence = 0
        for action, value in actions:
            value = copy.deepcopy(value)
            if action == 'reserve':
                sequence += 1
                event = ledger.append('RESERVED', 'model_transport_reserved',
                    dict(attempt_identity_sha256=IDENTITY, transport_sequence=sequence, reservation=value))
                ticket = dict(attempt_identity_sha256=IDENTITY, transport_sequence=sequence,
                              request_sha256=value['request_sha256'], reservation_event_sha256=event['event_sha256'])
            elif action in ('observe', 'wrong-ticket'):
                bound = copy.deepcopy(ticket)
                if action == 'wrong-ticket':
                    bound['request_sha256'] = 'f'*64
                ledger.append('OBSERVED', 'model_transport_observed',
                    dict(attempt_identity_sha256=IDENTITY, reservation_ticket=bound, observation=value))
            elif action == 'snapshot':
                ledger.append('OBSERVED', 'sanitized_accounting',
                    dict(attempt_identity_sha256=IDENTITY, accounting=value))
            elif action == 'logical':
                ledger.append('RESERVED', 'reserved', dict(attempt_identity_sha256=IDENTITY, reservation=value))
            else:
                state, kind, payload = value
                ledger.append(state, kind, payload)
        self.assertTrue(ledger.verify())
        return RunLedger(ledger.path).events

    def replay(self, actions):
        return _reconcile_accounting_journal(self.journal(actions), IDENTITY)

    def test_pending_transport_retains_bounds_and_completed_usage(self):
        result = self.replay([('reserve', reservation()), ('observe', observation()),
                             ('snapshot', snapshot(1)), ('reserve', reservation(call=2))])
        self.assertEqual(result['calls'], 1)
        self.assertEqual((result['input_tokens'], result['output_tokens'], result['estimated_cost_usd']), (7, 3, .00022))
        self.assertFalse(result['billing_final'])
        self.assertEqual(result['in_flight_final_usage'], 'unknown; reserved upper bound recorded')
        self.assertEqual(result['reserved_in_flight']['input_tokens'], 999)
        self.assertEqual(result['reserved_in_flight']['output_tokens'], 16)
        self.assertEqual(result['reserved_in_flight']['estimated_cost_usd'], .01079)
        self.assertEqual(result['reserved_in_flight']['reservation_ticket']['transport_sequence'], 2)
        self.assertEqual(result['model_transport_accounting'][0]['observation']['response_usage'], dict(input_tokens=7, output_tokens=3))
        self.assertEqual(len(result['unresolved_model_transports']), 1)
        self.assertEqual(result['invoice_reconciliation'], "The actual cost will be reconciled by Howard from the provider's invoice.")

    def test_unknown_retry_is_not_erased_by_success_or_snapshot(self):
        result = self.replay([('reserve', reservation()), ('observe', observation(failed=True)),
                             ('reserve', reservation(attempt=2)), ('observe', observation()),
                             ('snapshot', snapshot(1))])
        self.assertEqual(result['calls'], 1)
        self.assertEqual(result['estimated_cost_usd'], .00022)  # No double counting.
        self.assertEqual(result['in_flight_final_usage'], 'none')
        self.assertNotIn('reserved_in_flight', result)
        self.assertEqual(len(result['model_transport_accounting']), 2)
        unresolved = result['unresolved_model_transports']
        self.assertEqual(len(unresolved), 1)
        self.assertEqual(unresolved[0]['reservation_ticket']['transport_sequence'], 1)
        self.assertIsNone(unresolved[0]['observation']['response_usage'])
        self.assertEqual(unresolved[0]['reservation']['bounds']['estimated_cost_usd'], .01079)
        self.assertFalse(result['billing_final'])

    def test_completed_usage_survives_absent_logical_checkpoint(self):
        result = self.replay([('reserve', reservation()), ('observe', observation())])
        self.assertEqual(result['calls'], 0)
        self.assertEqual(result['estimated_cost_usd'], 0)
        self.assertEqual(result['uncheckpointed_model_transports'][0]['observation']['estimated_cost_usd'], .00022)
        self.assertEqual(result['in_flight_final_usage'], 'none')
        self.assertNotIn('unresolved_model_transports', result)

    def test_count_transport_and_generation_use_separate_tickets(self):
        result = self.replay([('reserve', reservation(kind='input-token-count')),
                             ('observe', observation(kind='input-token-count')),
                             ('reserve', reservation()), ('observe', observation()),
                             ('snapshot', snapshot(1))])
        rows = result['model_transport_accounting']
        self.assertEqual([x['reservation_ticket']['transport_sequence'] for x in rows], [1, 2])
        self.assertIsNone(rows[0]['observation']['estimated_cost_usd'])
        self.assertNotIn('unresolved_model_transports', result)

    def test_hash_valid_wrong_ticket_duplicate_missing_and_retry_order_rejected(self):
        cases = [
            [('reserve', reservation()), ('wrong-ticket', observation())],
            [('reserve', reservation()), ('observe', observation()), ('observe', observation())],
            [('reserve', reservation()), ('snapshot', snapshot(1))],
            [('reserve', reservation()), ('reserve', reservation(attempt=2))],
            [('reserve', reservation(attempt=2))],
            [('reserve', reservation()), ('observe', observation()), ('reserve', reservation(attempt=2))],
            [('reserve', reservation()), ('observe', observation(failed=True)),
             ('reserve', dict(reservation(attempt=2), request_sha256='f'*64))],
            [('snapshot', snapshot(1))],
        ]
        for actions in cases:
            with self.subTest(actions=actions), self.assertRaises(ContractError):
                self.replay(actions)

    def test_observation_and_reservation_cost_tampering_rejected(self):
        bad = reservation(); bad['bounds']['estimated_cost_usd'] = 0
        observed = observation(); observed['estimated_cost_usd'] = 0
        for actions in ([('reserve', bad)], [('reserve', reservation()), ('observe', observed)]):
            with self.subTest(actions=actions), self.assertRaises(ContractError):
                self.replay(actions)

    def test_snapshot_cannot_rewrite_completed_hashes_or_totals(self):
        prefix = [('reserve', reservation()), ('observe', observation()), ('snapshot', snapshot(1))]
        changed = snapshot(1); changed['estimated_cost_usd'] = 0
        for tail in (snapshot(1, request='f'*64), changed, snapshot(0)):
            with self.subTest(tail=tail), self.assertRaises(ContractError):
                self.replay(prefix + [('snapshot', tail)])

    def test_identity_unknown_event_and_protocol_rejected(self):
        for payload in (dict(attempt_identity_sha256='f'*64, accounting=snapshot()),
                        dict(attempt_identity_sha256=IDENTITY, accounting=snapshot(), extra=True)):
            with self.subTest(payload=payload), self.assertRaises(ContractError):
                self.replay([('raw', ('OBSERVED', 'sanitized_accounting', payload))])
        with self.assertRaises(ContractError):
            self.replay([('raw', ('READY', 'unrecognized', dict(attempt_identity_sha256=IDENTITY)))])
        events = self.journal([])
        events[0]['payload']['protocol'] = 3
        with self.assertRaises(ContractError):
            _reconcile_accounting_journal(events, IDENTITY)

    def test_matching_request_hash_cannot_hide_wrong_completed_usage_or_cost(self):
        prefix = [('reserve', reservation()), ('observe', observation())]
        for key in ('input_tokens', 'output_tokens', 'estimated_cost_usd'):
            changed = snapshot(1); changed[key] = 0
            with self.subTest(key=key), self.assertRaises(ContractError):
                self.replay(prefix + [('snapshot', changed)])
        with self.assertRaises(ContractError):
            self.replay([('reserve', reservation()), ('observe', observation(failed=True)),
                         ('snapshot', snapshot(1))])

    def test_managed_failed_charge_matches_existing_reserved_arithmetic(self):
        physical = reservation()
        logical = dict(call_sequence=1, role='planner', request_sha256='b'*64,
                       invocation_sha256='b'*64, input_tokens=999, output_tokens=16,
                       estimated_cost_usd=.01079)
        charged = snapshot(1, request='b'*64)
        charged.update(input_tokens=999, output_tokens=16, estimated_cost_usd=.01079)
        prefix = [('logical', logical), ('reserve', physical), ('observe', observation(failed=True))]
        result = self.replay(prefix + [('snapshot', charged)])
        self.assertEqual(result['estimated_cost_usd'], .01079)
        self.assertEqual(result['unresolved_model_transports'][0]['reservation']['bounds']['estimated_cost_usd'], .01079)
        self.assertFalse(result['billing_final'])
        bad = dict(charged, estimated_cost_usd=0)
        with self.assertRaises(ContractError):
            self.replay(prefix + [('snapshot', bad)])

    def test_unpriced_usage_retained_but_cannot_authorize_completed_snapshot(self):
        cases = [None, {}, dict(input_tokens='7', output_tokens='3'),
                 dict(input_tokens=True, output_tokens=False),
                 dict(input_tokens=7.9, output_tokens=3.1),
                 dict(input_tokens=-7, output_tokens=3),
                 dict(input_tokens=None, output_tokens=None), dict(input_tokens=7)]
        for usage in cases:
            with self.subTest(usage=usage):
                observed = observation()
                observed.update(response_usage=usage, estimated_cost_usd=None,
                                cost_estimate_available=False)
                actions = [('reserve', reservation()), ('observe', observed)]
                result = self.replay(actions)
                self.assertEqual(result['calls'], 0)
                self.assertEqual(result['estimated_cost_usd'], 0)
                self.assertFalse(result['billing_final'])
                unresolved = result['unresolved_model_transports']
                self.assertEqual(len(unresolved), 1)
                self.assertEqual(unresolved[0]['observation'], observed)
                self.assertEqual(unresolved[0]['reservation']['bounds']['estimated_cost_usd'], .01079)
                self.assertIsNone(unresolved[0]['observation']['estimated_cost_usd'])
                self.assertEqual(result['invoice_reconciliation'],
                                 "The actual cost will be reconciled by Howard from the provider's invoice.")
                # Coercible legacy usage is not proof of a completed, priced transport.
                with self.assertRaisesRegex(ContractError, 'reconciliation-observed-usage-required'):
                    self.replay(actions + [('snapshot', snapshot(1))])
