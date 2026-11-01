"""CI-only retention of synthetic-identity count/generation component exits.

These are original component journals, not an admitted controller run or receipt.
No signature, admission, live provider request or qualification is produced.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import stat
import subprocess
import sys

from lightyear_factory.contracts import ContractError, canonical_hash
from lightyear_factory.orchestrator import _reconcile_accounting_journal


MODES = {
    'before-count-reserve': (0, 0, 0),
    'after-count-reserve': (1, 0, 0),
    'before-generation-reserve': (1, 1, 1),
    'after-generation-reserve': (2, 1, 1),
    'generation-send': (2, 1, 2),
    'after-generation-observed': (2, 2, 2),
    'normal': (2, 2, 2),
}
FIXTURE = 'tests/test_p5_request_derived_count_bound.py'
SCOPE = 'controller journal and adapter component; synthetic identity and generation bounds; stub HTTP'
LIMIT = 2 * 1024 * 1024


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def validate(value):
    """Check retained original bytes and replay; no authority or origin inference."""
    def require(ok):
        if not ok:
            raise ValueError('p5-physical-retention-invalid')

    def unique(pairs):
        result = {}
        for key, item in pairs:
            require(key not in result)
            result[key] = item
        return result

    def parse(raw):
        return json.loads(raw, object_pairs_hook=unique,
                          parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))

    def raw(row):
        require(set(row) == {'utf8', 'sha256'})
        data = row['utf8'].encode('utf-8')
        require(0 < len(data) <= LIMIT and digest(data) == row['sha256'])
        return data

    try:
        require(value['schema'] == 'p5-physical-exit-retention/1' and value['scope'] == SCOPE)
        mode = value['mode']; require(mode in MODES)
        require(value['production_controller_receipt'] is False and value['admission_verified'] is False)
        require(value['signing'] is False and type(value['real_model_calls']) is int and value['real_model_calls'] == 0)
        require(value['synthetic_identity_sha256'] == 'a' * 64)
        require(re.fullmatch('[0-9a-f]{64}', value['fixture_sha256']) is not None)
        require(type(value['exit_code']) is int and value['exit_code'] == (0 if mode == 'normal' else 86))
        docs = value['documents']
        expected = {'attempt.jsonl', 'child-result.json'}
        if MODES[mode][2]: expected.add('stub-sends.jsonl')
        if mode == 'normal': expected.add('result.json')
        require(set(docs) == expected)
        child = parse(raw(docs['child-result.json']))
        require(child['status'] == 'completed' and child['exit_code'] == value['exit_code'])
        for key in ('stdout', 'stderr'):
            data = base64.b64decode(child[key]['base64'], validate=True)
            require(len(data) <= LIMIT and len(data) == child[key]['bytes'])
            require(digest(data) == child[key]['sha256'])
        ledger = raw(docs['attempt.jsonl']); require(ledger.endswith(b'\n'))
        events = [parse(line) for line in ledger.splitlines()]
        require(bool(events)); previous = None
        for sequence, event in enumerate(events, 1):
            require(type(event['sequence']) is int and event['sequence'] == sequence)
            require(event['previous_sha256'] == previous)
            require(event['event_sha256'] == canonical_hash(event, {'event_sha256'}))
            previous = event['event_sha256']
        require(events[0]['kind'] == 'model_reservations' and events[0]['payload']['protocol'] == 5)
        require(events[0]['payload']['count_bound_profile'] == 'request-bytes-v1')
        reservations = [e for e in events if e['kind'] == 'model_transport_reserved']
        observations = [e for e in events if e['kind'] == 'model_transport_observed']
        sent_raw = raw(docs['stub-sends.jsonl']) if 'stub-sends.jsonl' in docs else b''
        require(not sent_raw or sent_raw.endswith(b'\n'))
        sends = [parse(line) for line in sent_raw.splitlines()]
        require((len(reservations), len(observations), len(sends)) == MODES[mode])
        require([e['payload']['reservation']['transport_kind'] for e in reservations]
                == ['input-token-count', 'responses'][:len(reservations)])
        require([s['kind'] for s in sends] == ['input-token-count', 'responses'][:len(sends)])
        for sent, event in zip(sends, reservations):
            reservation = event['payload']['reservation']
            require(set(sent) == {'kind', 'request_sha256', 'reservation_event_sha256'})
            require(sent['reservation_event_sha256'] == event['event_sha256'])
            require(sent['request_sha256'] == reservation['request_sha256'])
        replay = _reconcile_accounting_journal(events, 'a' * 64)
        require(replay == value['replayed_accounting'] and replay['billing_final'] is False)
        require(canonical_hash(replay) == canonical_hash(value['replayed_accounting']))
        finance = replay['count_financial_accounting']
        require(finance['billing_final'] is False and finance['actual_provider_cost_usd'] is None)
        count = finance['count_account']['calls'][0]
        if mode in ('before-count-reserve', 'after-count-reserve'):
            require(count['state'] == 'reserved-unknown' and count['charge_usd'] == count['reserved_cost_usd'])
        else:
            require(count['state'] == 'counted-conservative-charge' and finance['count_account']['count_exposure_usd'] == '0.0000935')
        if mode in ('after-generation-reserve', 'generation-send'):
            require(replay['unresolved_model_transports'][-1]['reservation']['transport_kind'] == 'responses')
        if mode in ('after-generation-observed', 'normal'):
            require('unresolved_model_transports' not in replay)
            require(observations[-1]['payload']['observation']['response_usage'] == dict(input_tokens=17, output_tokens=1))
        if mode == 'normal': require(parse(raw(docs['result.json'])) == {'ok': True})
        return True
    except (KeyError, TypeError, ValueError, IndexError, AttributeError, UnicodeError, ContractError):
        raise ValueError('p5-physical-retention-invalid') from None


def observe(repository, directory, mode):
    """Run only the existing CI component child, retain its allowlisted public files."""
    if os.environ.get('GITHUB_ACTIONS') != 'true' or mode not in MODES:
        raise ValueError('p5-physical-retention-ci-only')
    repository = Path(repository).resolve(strict=True)
    directory = Path(directory)
    if directory.exists(): raise ValueError('p5-physical-retention-exclusive-output')
    fixture = repository / FIXTURE
    # run_name prevents unittest.main/child entry-point execution. No test suite
    # is invoked here: the fixed public child supplies the original fixture.
    definitions = runpy.run_path(str(fixture), run_name='p5_retention_child_definition')
    child = definitions['PhysicalCountGenerationExitTests'].CHILD
    directory.mkdir(parents=True)
    def output(raw):
        if len(raw) > LIMIT: raise ValueError('p5-physical-retention-output-size')
        return dict(base64=base64.b64encode(raw).decode('ascii'), sha256=digest(raw), bytes=len(raw))
    def diagnostics(status, code, stdout, stderr):
        (directory/'child-result.json').write_text(json.dumps(dict(status=status, exit_code=code,
            stdout=output(stdout), stderr=output(stderr)), sort_keys=True)+'\n', encoding='utf-8')
    try:
        result = subprocess.run([sys.executable, '-B', '-c', child, str(fixture), mode, str(directory.resolve())],
                                cwd=repository, capture_output=True, timeout=60, check=False)
    except subprocess.TimeoutExpired as error:
        diagnostics('timed-out', None, error.stdout or b'', error.stderr or b'')
        raise ValueError('p5-physical-retention-child-timeout') from None
    # Save diagnostics before any journal validation so unexpected exits are
    # retained as failures. This fixture contains public synthetic inputs only.
    diagnostics('completed', result.returncode, result.stdout, result.stderr)
    if result.returncode != (0 if mode == 'normal' else 86):
        raise ValueError('p5-physical-retention-child-exit')
    def retain(path):
        before = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= LIMIT:
            raise ValueError('p5-physical-retention-file')
        data = path.read_bytes(); after = path.lstat()
        fields = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
        if fields(before) != fields(after) or len(data) != before.st_size:
            raise ValueError('p5-physical-retention-changed')
        return dict(utf8=data.decode('utf-8'), sha256=digest(data))
    names = ('attempt.jsonl', 'stub-sends.jsonl', 'result.json', 'child-result.json')
    documents = {name: retain(directory/name) for name in names if (directory/name).exists()}
    events = [json.loads(line) for line in documents['attempt.jsonl']['utf8'].splitlines()]
    value = dict(schema='p5-physical-exit-retention/1', scope=SCOPE, mode=mode,
        fixture_sha256=digest(fixture.read_bytes()), synthetic_identity_sha256='a'*64,
        exit_code=result.returncode, documents=documents,
        replayed_accounting=_reconcile_accounting_journal(events, 'a'*64),
        production_controller_receipt=False, admission_verified=False, signing=False, real_model_calls=0)
    # Caller can preserve the directory even if validation fails. A wrong exit,
    # missing journal, unexpected send or replay failure is never an expectation pass.
    validate(value)
    return value
