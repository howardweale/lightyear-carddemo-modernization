"""Consumed-once full N1 comparison using the unchanged frozen comparator.

Controller library only: exchange and snapshot are trusted caller capabilities,
not authenticated candidate/DB/browser bindings. No private CLI or launch path.
Never send expected frames, states or oracle artifacts through exchange.
"""
import base64
from copy import deepcopy
import sys

from lightyear_execution import copau_full_state_contract as contract
from tools import copau_full_state as capture


class _Mismatch(Exception):
    """Only an observed comparison inequality, never an operational fault."""


def match(equal):
    if not equal:
        raise _Mismatch


def full_snapshot(reader):
    state = reader()
    contract.require(type(state) is dict and all(type(name) is str and
        type(rows) is list and all(type(row) is dict for row in rows)
        for name, rows in state.items()), 'malformed-candidate-snapshot')
    contract.require(len(contract.encoded(state)) <= contract.LIMIT)
    return state


def replay(store, root, *, exchange, snapshot, candidate_sha256):
    """Compare every sealed interaction; no filtering, retries or fallback.

snapshot returns the complete canonical table inventory using the independent
reader. exchange receives only token/aid/fields. Production routing/isolation,
transaction ownership, browser rendering and result authentication remain open.
"""
    contract.require(not sys.flags.optimize, 'frozen-assertions-required')
    contract.require(isinstance(candidate_sha256, str) and
                     contract.SHA.fullmatch(candidate_sha256))
    contract.require(callable(exchange) and callable(snapshot))
    store.absent('n1-replay-consumed.json', 'n1-replay-complete.json')
    raw, commitment = contract._commitment(store)
    completed = contract.decoded(store.read('n1-complete.json'))
    loaded = contract.decoded(store.read('n1-load-complete.json'))
    oracle_raw = contract.get_blob(store, 'n1-oracle')
    contract.require(completed['status'] == 'ORACLE_CAPTURE_ONLY' and
        completed['commitment_sha256'] == contract.sha(raw) and
        completed['oracle_sha256'] == contract.sha(oracle_raw) and
        loaded['commitment_sha256'] == contract.sha(raw) and
        loaded['input_sha256'] == commitment['input_sha256'] and
        loaded['status'] == 'INITIAL_STATE_ONLY', 'replay-input-binding')
    binding = dict(commitment_sha256=contract.sha(raw),
        oracle_sha256=contract.sha(oracle_raw), candidate_sha256=candidate_sha256)
    store.write('n1-replay-consumed.json', contract.encoded(binding))
    observed, outcome = [], 'FAULT'
    try:
        producer, _ = capture.reference.verify_producer(root)
        oracle = contract.decoded(oracle_raw)
        contract.require(oracle['session'] == contract.SESSION and
            oracle['producer_bindings'] == capture.bindings() and
            oracle['binding']['commitment_sha256'] == binding['commitment_sha256'])
        rows = oracle['rows']
        contract.require(type(rows) is list and 0 < len(rows) <= 10000)
        initial = contract.decoded(contract.get_blob(store, 'n1-initial'))
        contract.require(oracle['initial_sha256'] ==
            contract.sha(contract.get_blob(store, 'n1-initial')) and
            loaded['full_state_sha256'] == producer.digest(initial))
        states = {}
        for item in oracle['states']:
            payload = contract.get_blob(store, item['blob'])
            contract.require(item['path'] not in states and
                item['sha256'] == contract.sha(payload))
            states[item['path']] = (item['sha256'], contract.decoded(payload))
        match(full_snapshot(snapshot) == initial)
        previous, token, session, observed = initial, None, None, []
        for row in rows:
            contract.require(row['case'] == contract.SESSION and
                row['before_sha256'] == producer.digest(previous))
            match(full_snapshot(snapshot) == previous)
            if row['session'] != session:
                contract.require(row['aid'] == 'INITIAL')
                token, session = None, row['session']
            request = dict(token=token, aid=row['aid'], fields=deepcopy(row['fields']))
            sent = contract.encoded(request)
            actual = exchange(request)
            contract.require(contract.encoded(request) == sent, 'request-mutated')
            contract.require(type(actual) is dict and type(actual['screen']) is dict
                and type(actual['token']) is str and type(actual['ended']) is bool)
            token = actual['token']
            expected = row['expected']
            try:
                producer.compare_frame(actual['screen'], expected)
            except AssertionError:
                raise _Mismatch from None
            match(actual['ended'] == expected['ended'])
            if not expected['ended'] and not expected.get('source_fault'):
                envelope = token.split('.')[0]
                value = contract.decoded(base64.urlsafe_b64decode(
                    envelope + '=' * (-len(envelope) % 4)))
                match(value['program'] == expected['program'] and
                    base64.b64decode(value['commarea'], validate=True).hex() ==
                    expected['commarea'])
            file = row['database_file']
            digest, after = states[file['path']]
            contract.require(digest == file['sha256'] and
                row['after_sha256'] == producer.digest(after))
            actual_state = full_snapshot(snapshot)
            match(actual_state == after)
            observed.append(dict(request_sha256=contract.sha(sent),
                response=deepcopy(actual), before=previous, after=deepcopy(actual_state)))
            contract.require(len(contract.encoded(observed)) <= contract.LIMIT)
            previous = after
        outcome = 'MATCH'
    except _Mismatch:
        outcome = 'MISMATCH'
    except BaseException:
        # Timeout, interruption, malformed input/response, storage/DB or adapter
        # errors are FAULT, never evidence of behavioral inequality or equality.
        outcome = 'FAULT'
    try:
        digest = contract.put_blob(store, 'n1-candidate-observations', contract.encoded(observed))
        result = dict(binding, observations_sha256=digest, interactions=len(observed),
            outcome=outcome,
            status='FULL_SESSION_COMPARISON_ONLY', qualified=False,
            candidate_ownership_verified=False, transaction_binding_verified=False,
            browser_replayed=False, result_authenticated=False)
        store.write('n1-replay-complete.json', contract.encoded(result))
        return result
    except BaseException:
        raise contract.Refused('candidate-result-write-failed-consumed') from None
