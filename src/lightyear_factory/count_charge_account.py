"""Count-call budget holds, conservative settlement and non-resuming replay.

The controller must supply an exact-reviewed input hold, the OTHER shared-budget
exposure (including the current generation reserve), and its existing durable
attempt-journal sink. The request-derived profile has an explicit unaccepted
provider limitation; this component cannot prove billing or synthesize a sink.
"""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import re
from threading import RLock

from .contracts import ContractError, canonical_hash
from .flex_billing import is_flex_billing_policy


class CountChargeJournalError(RuntimeError):
    """A failed durable append must never enter provider network retry handling."""


def _money(value):
    try:
        if type(value) not in (str, int, float, Decimal):
            raise ValueError('type')
        result = Decimal(str(value))
        if not result.is_finite() or result < 0:
            raise ValueError('range')
        return result
    except (ValueError, InvalidOperation):
        raise ContractError('count-account-money') from None


def _hash(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


@dataclass(frozen=True)
class CountInputBound:
    request_sha256: str
    input_tokens: int
    evidence_sha256: str
    basis_json: str | None = None

    def validate(self, raw):
        # Provenance is mandatory but a digest is NOT a mathematical proof.
        # The exact-reviewed resolver and its named limitation define the hold;
        # byte correspondence is not a proof of provider-side billing.
        if (not isinstance(raw, bytes) or not _hash(self.request_sha256)
                or self.request_sha256 != sha256(raw).hexdigest()
                or type(self.input_tokens) is not int or self.input_tokens < 0
                or not _hash(self.evidence_sha256)):
            raise ContractError('count-account-input-bound')
        if self.basis_json is not None:
            from .count_request_bound import request_bound_basis, validate_retained_basis
            basis = validate_retained_basis(json.loads(self.basis_json), self.request_sha256,
                                            self.input_tokens, self.evidence_sha256)
            if basis != request_bound_basis(raw):
                raise ContractError('count-account-input-basis')


class CountChargeAccount:
    def __init__(self, policy, *, cap_usd, attempt_identity_sha256,
                 other_exposure_usd, durable_append):
        if (not is_flex_billing_policy(policy) or not _hash(attempt_identity_sha256)
                or not callable(other_exposure_usd) or not callable(durable_append)):
            raise ContractError('count-account-controller-binding-required')
        self._policy = deepcopy(policy)
        self._cap = _money(cap_usd)
        if not 0 < self._cap <= 10:
            raise ContractError('count-account-cap')
        self._identity = attempt_identity_sha256
        self._other = other_exposure_usd
        self._append = durable_append
        self._events = []
        self._rows = []
        self._failed = False
        self._lock = RLock()

    @property
    def policy_sha256(self):
        return self._policy['content_sha256']

    def _cost(self, tokens):
        return Decimal(tokens) * Decimal('5.50') / Decimal(1000000)

    def _exposure(self):
        return sum((_money(row['charge_usd']) for row in self._rows), Decimal(0))

    def _write(self, event):
        event = dict(event, attempt_identity_sha256=self._identity,
                     billing_policy_sha256=self._policy['content_sha256'],
                     event_sequence=len(self._events)+1,
                     previous_count_event_sha256=(self._events[-1]['content_sha256'] if self._events else None))
        event['content_sha256'] = canonical_hash(event)
        try:
            # The controller sink must append to the existing attempt journal
            # and fsync before returning. A callback error poisons this account.
            self._append(deepcopy(event))
        except BaseException as exc:
            self._failed = True
            if isinstance(exc, Exception):
                raise CountChargeJournalError('count-account-durable-append-failed') from exc
            raise
        self._events.append(event)
        return event

    def reserve(self, raw, bound):
        with self._lock:
            if self._failed or type(bound) is not CountInputBound:
                raise ContractError('count-account-unavailable-or-unbound')
            if any('bound_basis' in row and row['state']=='reserved-unknown' for row in self._rows):
                raise ContractError('count-account-another-call-in-flight')
            bound.validate(raw)
            other = _money(self._other())
            cost = self._cost(bound.input_tokens)
            if other + self._exposure() + cost > self._cap:
                raise ContractError('count-account-cannot-admit-within-shared-cap')
            sequence = len(self._rows)+1
            basis_fields = ({'bound_basis': json.loads(bound.basis_json)}
                            if bound.basis_json is not None else {})
            event = self._write(dict(kind='count_charge_reserved', count_sequence=sequence,
                request_sha256=bound.request_sha256, bound_evidence_sha256=bound.evidence_sha256,
                reserved_input_tokens=bound.input_tokens, reserved_cost_usd=str(cost),
                other_exposure_usd=str(other), prior_count_exposure_usd=str(self._exposure()),
                cap_usd=str(self._cap), rate_card_url=self._policy['rate_card_url'], **basis_fields))
            ticket = dict(count_sequence=sequence, reservation_event_sha256=event['content_sha256'],
                          request_sha256=bound.request_sha256)
            self._rows.append(dict(ticket=ticket, reserved_input_tokens=bound.input_tokens,
                                   reserved_cost_usd=str(cost), counted_input_tokens=None,
                                   charge_usd=str(cost), state='reserved-unknown', billing_final=False,
                                   **deepcopy(basis_fields)))
            return deepcopy(ticket)

    def observe(self, ticket, count):
        with self._lock:
            if self._failed or not isinstance(ticket, dict):
                raise ContractError('count-account-unavailable')
            sequence = ticket.get('count_sequence')
            if type(sequence) is not int or not 1 <= sequence <= len(self._rows):
                raise ContractError('count-account-ticket')
            row = self._rows[sequence-1]
            if row['ticket'] != ticket or row['state'] != 'reserved-unknown':
                raise ContractError('count-account-reused-or-mismatched-ticket')
            known = type(count) is int and count >= 0
            charge = self._cost(count) if known else _money(row['reserved_cost_usd'])
            bound_exceeded = known and count > row['reserved_input_tokens']
            release = max(Decimal(0), _money(row['reserved_cost_usd'])-charge)
            other = _money(self._other())
            shared_exceeded = other + self._exposure()-_money(row['charge_usd'])+charge > self._cap
            self._write(dict(kind='count_charge_observed', ticket=deepcopy(ticket),
                counted_input_tokens=count if known else None,
                conservative_charge_usd=str(charge), released_excess_usd=str(release),
                bound_exceeded=bound_exceeded, shared_cap_exceeded=shared_exceeded,
                other_exposure_usd=str(other), billing_final=False,
                provider_billed_usage=None, provider_billed_cost_usd=None))
            row.update(counted_input_tokens=count if known else None, charge_usd=str(charge),
                       state='counted-conservative-charge' if known else 'observed-unknown-held')
            # New request-derived holds cannot proceed after an unknown result.
            # Older component/replay rows without this profile retain their semantics.
            if not known and 'bound_basis' in row:
                self._failed = True
            if bound_exceeded or shared_exceeded:
                self._failed = True
                raise ContractError('count-account-observed-bound-or-cap-exceeded')

    @contextmanager
    def transport(self, raw, bound):
        ticket = self.reserve(raw, bound)
        captured = [None]
        try:
            yield lambda count: captured.__setitem__(0, count)
        except BaseException:
            self.observe(ticket, None)
            raise
        else:
            self.observe(ticket, captured[0])

    def snapshot(self):
        with self._lock:
            result = dict(schema='factory-count-charge-account/1',
                attempt_identity_sha256=self._identity, billing_policy=deepcopy(self._policy),
                count_exposure_usd=str(self._exposure()), calls=deepcopy(self._rows),
                stopped=self._failed, billing_final=False,
                actual_billing='unknown; conservative count charge or reserved bound retained',
                last_count_event_sha256=self._events[-1]['content_sha256'] if self._events else None)
            result['content_sha256'] = canonical_hash(result)
            return result


def replay_count_charges(events, policy, *, cap_usd, attempt_identity_sha256):
    """Validate a retained count-event stream and report; never resume or send.

    The caller must first verify its enclosing RunLedger hash chain and verify
    other_exposure against that journal's generation accounting. This component
    alone cannot authenticate caller-supplied generation totals.
    """
    generated = []
    other = [Decimal(0)]
    book = CountChargeAccount(policy, cap_usd=cap_usd,
        attempt_identity_sha256=attempt_identity_sha256,
        other_exposure_usd=lambda: other[0], durable_append=generated.append)
    for event in events:
        if not isinstance(event, dict):
            raise ContractError('count-account-replay-shape')
        other[0] = _money(event.get('other_exposure_usd'))
        kind = event.get('kind')
        if kind == 'count_charge_reserved':
            # Request bytes are not stored. Validate the hash binding directly;
            # live reserve additionally hashes bytes before opening transport.
            bound = event.get('reserved_input_tokens')
            request_hash = event.get('request_sha256')
            evidence = event.get('bound_evidence_sha256')
            if type(bound) is not int or bound < 0 or not _hash(request_hash) or not _hash(evidence):
                raise ContractError('count-account-replay-bound')
            basis_fields = {}
            if 'bound_basis' in event:
                from .count_request_bound import validate_retained_basis
                basis_fields = dict(bound_basis=validate_retained_basis(
                    event['bound_basis'],request_hash,bound,evidence))
            if book._failed:
                raise ContractError('count-account-replay-after-stop')
            if any('bound_basis' in row and row['state']=='reserved-unknown' for row in book._rows):
                raise ContractError('count-account-replay-another-call-in-flight')
            cost = book._cost(bound)
            if other[0]+book._exposure()+cost > book._cap:
                raise ContractError('count-account-replay-cap')
            expected = book._write(dict(kind=kind, count_sequence=len(book._rows)+1,
                request_sha256=request_hash, bound_evidence_sha256=evidence,
                reserved_input_tokens=bound, reserved_cost_usd=str(cost),
                other_exposure_usd=str(other[0]), prior_count_exposure_usd=str(book._exposure()),
                cap_usd=str(book._cap), rate_card_url=policy['rate_card_url'], **basis_fields))
            ticket = dict(count_sequence=len(book._rows)+1,
                          reservation_event_sha256=expected['content_sha256'], request_sha256=request_hash)
            book._rows.append(dict(ticket=ticket, reserved_input_tokens=bound,
                reserved_cost_usd=str(cost), counted_input_tokens=None,
                charge_usd=str(cost), state='reserved-unknown', billing_final=False,
                **deepcopy(basis_fields)))
        elif kind == 'count_charge_observed':
            before = len(generated)
            try:
                book.observe(event.get('ticket'), event.get('counted_input_tokens'))
            except ContractError:
                # An over-bound charge is retained before the intentional stop.
                # All other refusals append nothing and are replay errors.
                if len(generated) != before+1 or not book._failed:
                    raise
        else:
            raise ContractError('count-account-replay-kind')
        if generated[-1] != event:
            raise ContractError('count-account-replay-event-mismatch')
    result = dict(book.snapshot(), replay_only=True, resume_authorized=False)
    result['content_sha256'] = canonical_hash(result, {'content_sha256'})
    return result
