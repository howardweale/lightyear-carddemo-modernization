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


def match(equal, check, index, evidence):
    if not equal:
        raise _Mismatch(check, index, evidence)


def response_shape(actual, expected):
    """Validate an arrived response; exchange failures are handled separately."""
    contract.require(type(actual) is dict and type(actual.get('screen')) is dict
        and type(actual.get('ended')) is bool)
    token = actual.get('token')
    # SEND TEXT and raw source faults have no proved RETURN envelope.
    if expected['ended'] or expected.get('source_fault'):
        return token, None, None
    contract.require(type(token) is str)
    envelope = token.split('.')[0]
    value = contract.decoded(base64.b64decode(
        envelope + '=' * (-len(envelope) % 4), altchars=b'-_', validate=True))
    contract.require(type(value) is dict and type(value.get('program')) is str
        and type(value.get('commarea')) is str)
    area = base64.b64decode(value['commarea'], validate=True).hex()
    return token, value['program'], area


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
    observed, outcome, failure = [], 'FAULT', None
    failed_check, failing_index = None, None
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
        actual_initial = full_snapshot(snapshot)
        match(actual_initial == initial, 'initial', None,
              dict(initial=deepcopy(actual_initial)))
        previous, token, session, observed = initial, None, None, []
        for index, row in enumerate(rows):
            contract.require(row['case'] == contract.SESSION and
                row['before_sha256'] == producer.digest(previous))
            actual_before = full_snapshot(snapshot)
            evidence = dict(index=index, before=deepcopy(actual_before))
            match(actual_before == previous, 'before', index, evidence)
            if row['session'] != session:
                contract.require(row['aid'] == 'INITIAL')
                token, session = None, row['session']
            request = dict(token=token, aid=row['aid'], fields=deepcopy(row['fields']))
            sent = contract.encoded(request)
            actual = exchange(request)
            contract.require(contract.encoded(request) == sent, 'request-mutated')
            # Retain the failing interaction, not merely its matched prefix.
            # These bytes stay in the private store, never the public result.
            evidence.update(request_sha256=contract.sha(sent), response=deepcopy(actual))
            actual_state = full_snapshot(snapshot)
            evidence['after'] = deepcopy(actual_state)
            expected = row['expected']
            try:
                token, program, area = response_shape(actual, expected)
            except Exception:
                raise _Mismatch('response-shape', index, evidence) from None
            try:
                producer.compare_frame(actual['screen'], expected)
            except AssertionError:
                raise _Mismatch('frame', index, evidence) from None
            except Exception:
                raise _Mismatch('response-shape', index, evidence) from None
            match(actual['ended'] == expected['ended'], 'ended', index, evidence)
            if not expected['ended'] and not expected.get('source_fault'):
                match(program == expected['program'] and area == expected['commarea'],
                      'commarea', index, evidence)
            file = row['database_file']
            digest, after = states[file['path']]
            contract.require(digest == file['sha256'] and
                row['after_sha256'] == producer.digest(after))
            match(actual_state == after, 'after', index, evidence)
            observed.append(evidence)
            contract.require(len(contract.encoded(observed)) <= contract.LIMIT)
            previous = after
        outcome = 'MATCH'
    except _Mismatch as mismatch:
        failed_check, failing_index, failure = mismatch.args
        outcome = 'MISMATCH'
    except BaseException:
        # Timeout, interruption, malformed snapshot, storage/DB or adapter
        # errors are FAULT, never evidence of behavioral inequality or equality.
        outcome = 'FAULT'
    try:
        digest = contract.put_blob(store, 'n1-candidate-observations', contract.encoded(observed))
        failure_digest = contract.put_blob(store, 'n1-candidate-failure', contract.encoded(failure))
        result = dict(binding, observations_sha256=digest, interactions=len(observed),
            failure_sha256=failure_digest, failed_check=failed_check,
            failing_index=failing_index, outcome=outcome,
            status='FULL_SESSION_COMPARISON_ONLY', qualified=False,
            candidate_ownership_verified=False, transaction_binding_verified=False,
            browser_replayed=False, result_authenticated=False)
        store.write('n1-replay-complete.json', contract.encoded(result))
        return result
    except BaseException:
        raise contract.Refused('candidate-result-write-failed-consumed') from None
