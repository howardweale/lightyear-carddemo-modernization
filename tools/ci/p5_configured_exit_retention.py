"""Retain configured-loader CI components, never an admitted factory receipt."""
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
from lightyear_factory.flex_billing import flex_billing_policy

FIXTURE = 'tests/test_p5_configured_count_component.py'
MODES = {'before-count-reserve': (0, 0, 0), 'after-count-reserve': (1, 0, 0),
         'before-generation-reserve': (1, 1, 1), 'after-generation-reserve': (2, 1, 1),
         'normal': (2, 2, 2)}
SCOPE = 'configured loader and snapshot adapter; synthetic identity and generation bounds; stub HTTP'
LIMIT = 2 * 1024 * 1024


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def validate(value):
    def require(ok):
        if not ok:
            raise ValueError('configured-exit-retention-invalid')
    def unique(pairs):
        result = {}
        for key, item in pairs:
            require(key not in result); result[key] = item
        return result
    def parse(raw):
        return json.loads(raw, object_pairs_hook=unique,
                          parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    def document(name):
        row = value['documents'][name]
        require(set(row) == {'base64', 'sha256', 'bytes'})
        raw = base64.b64decode(row['base64'], validate=True)
        require(type(row['bytes']) is int and 0 < len(raw) <= LIMIT and len(raw) == row['bytes'])
        require(digest(raw) == row['sha256'])
        return raw
    try:
        require(value['schema'] == 'p5-configured-exit-retention/1' and value['scope'] == SCOPE)
        require(all(value[k] is False for k in ('admission_verified', 'production_controller_receipt', 'strict_qualified', 'signing')))
        require(type(value['real_model_calls']) is int and value['real_model_calls'] == 0)
        require(value['synthetic_identity_sha256'] == 'a'*64)
        require(type(value['fixture_sha256']) is str and re.fullmatch('[0-9a-f]{64}', value['fixture_sha256']) is not None)
        mode = value['mode']; require(mode in MODES)
        expected = {'attempt.jsonl', 'child-result.json', 'models.json'}
        if MODES[mode][2]: expected.add('stub-sends.jsonl')
        require(set(value['documents']) == expected)
        code = 0 if mode == 'normal' else 86
        require(type(value['exit_code']) is int and value['exit_code'] == code)
        child = parse(document('child-result.json'))
        require(child['status'] == 'completed' and type(child['exit_code']) is int and child['exit_code'] == code)
        for name in ('stdout', 'stderr'):
            row = child[name]; data = base64.b64decode(row['base64'], validate=True)
            require(type(row['bytes']) is int and len(data) == row['bytes'] and len(data) <= LIMIT)
            require(digest(data) == row['sha256'])
        config = parse(document('models.json'))
        require(set(config) == {'default', 'models'})
        require(config['default'] == 'public-fixture' and set(config['models']) == {'public-fixture'})
        model = config['models']['public-fixture']
        require(set(model) == {'provider', 'model', 'input_usd_per_million',
                              'output_usd_per_million', 'max_output_tokens',
                              'service_tier', 'billing_policy'})
        require(model['billing_policy'] == flex_billing_policy())
        require(model['provider'] == 'openai' and model['model'] == 'gpt-5.4-2026-03-05')
        require(model['service_tier'] == 'flex' and model['max_output_tokens'] == 16)
        require(model['input_usd_per_million'] == 5.5 and model['output_usd_per_million'] == 24.75)
        ledger = document('attempt.jsonl'); require(ledger.endswith(b'\n'))
        events = [parse(line) for line in ledger.splitlines()]; require(bool(events))
        previous = None
        for sequence, event in enumerate(events, 1):
            require(type(event['sequence']) is int and event['sequence'] == sequence)
            require(event['previous_sha256'] == previous)
            require(event['event_sha256'] == canonical_hash(event, {'event_sha256'}))
            previous = event['event_sha256']
        require(events[0]['kind'] == 'model_reservations' and events[0]['payload']['protocol'] == 5)
        require(events[0]['payload']['count_bound_profile'] == 'request-bytes-v1')
        reserved = [e['payload']['reservation'] for e in events if e['kind'] == 'model_transport_reserved']
        observed = [e['payload']['observation'] for e in events if e['kind'] == 'model_transport_observed']
        sent_raw = document('stub-sends.jsonl') if MODES[mode][2] else b''
        require(not sent_raw or sent_raw.endswith(b'\n'))
        sent = [parse(line) for line in sent_raw.splitlines()]
        require((len(reserved), len(observed), len(sent)) == MODES[mode])
        require([r['transport_kind'] for r in reserved] == ['input-token-count', 'responses'][:len(reserved)])
        for index, row in enumerate(sent):
            require(set(row) == {'kind', 'request_sha256'})
            require(row['kind'] == reserved[index]['transport_kind'])
            require(row['request_sha256'] == reserved[index]['request_sha256'])
        replay = _reconcile_accounting_journal(events, 'a'*64)
        require(replay == value['replayed_accounting'] and replay['billing_final'] is False)
        finance = replay['count_financial_accounting']
        require(finance['billing_final'] is False and finance['actual_provider_cost_usd'] is None)
        count = finance['count_account']['calls'][0]
        if not sent:
            require(count['state'] == 'reserved-unknown' and count['charge_usd'] == count['reserved_cost_usd'])
        else:
            require(count['state'] == 'counted-conservative-charge')
            require(finance['count_account']['count_exposure_usd'] == '0.0000935')
        if mode == 'after-generation-reserve':
            require(replay['unresolved_model_transports'][-1]['reservation']['transport_kind'] == 'responses')
        if mode == 'normal':
            require('unresolved_model_transports' not in replay)
            require(observed[-1]['response_usage'] == dict(input_tokens=17, output_tokens=1))
        require(value['content_sha256'] == canonical_hash(value, {'content_sha256'}))
        return True
    except (KeyError, TypeError, ValueError, IndexError, AttributeError, UnicodeError, ContractError):
        raise ValueError('configured-exit-retention-invalid') from None


def observe(repository, directory, mode):
    if os.environ.get('GITHUB_ACTIONS') != 'true' or mode not in MODES:
        raise ValueError('configured-exit-retention-ci-only')
    repository = Path(repository).resolve(strict=True); directory = Path(directory)
    if directory.exists(): raise ValueError('configured-exit-retention-exclusive-output')
    fixture = repository/FIXTURE
    child = runpy.run_path(str(fixture), run_name='configured_retention_definition')['ConfiguredCountExitTests'].CHILD
    directory.mkdir(parents=True)
    def packed(raw):
        if len(raw) > LIMIT: raise ValueError('configured-exit-retention-size')
        return dict(base64=base64.b64encode(raw).decode('ascii'), bytes=len(raw), sha256=digest(raw))
    def diagnostics(status, code, stdout, stderr):
        with (directory/'child-result.json').open('x', encoding='utf-8', newline='\n') as stream:
            json.dump(dict(status=status, exit_code=code, stdout=packed(stdout), stderr=packed(stderr)), stream, sort_keys=True)
            stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
    try:
        result = subprocess.run([sys.executable, '-B', '-c', child, str(fixture), mode, str(directory.resolve())],
                                cwd=repository, capture_output=True, timeout=60, check=False)
    except subprocess.TimeoutExpired as error:
        diagnostics('timed-out', None, error.stdout or b'', error.stderr or b'')
        raise ValueError('configured-exit-retention-timeout') from None
    diagnostics('completed', result.returncode, result.stdout, result.stderr)
    if result.returncode != (0 if mode == 'normal' else 86):
        raise ValueError('configured-exit-retention-child-exit')
    documents = {}
    for name in ('attempt.jsonl', 'stub-sends.jsonl', 'models.json', 'child-result.json'):
        path = directory/name
        if not path.exists(): continue
        before = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= LIMIT:
            raise ValueError('configured-exit-retention-file')
        raw = path.read_bytes(); after = path.lstat()
        identity = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
        if identity(before) != identity(after) or len(raw) != before.st_size:
            raise ValueError('configured-exit-retention-changed')
        documents[name] = packed(raw)
    events = [json.loads(line) for line in base64.b64decode(documents['attempt.jsonl']['base64']).splitlines()]
    value = dict(schema='p5-configured-exit-retention/1', scope=SCOPE, mode=mode,
                 fixture_sha256=digest(fixture.read_bytes()), synthetic_identity_sha256='a'*64,
                 exit_code=result.returncode, documents=documents,
                 replayed_accounting=_reconcile_accounting_journal(events, 'a'*64),
                 admission_verified=False, production_controller_receipt=False,
                 strict_qualified=False, signing=False, real_model_calls=0)
    value['content_sha256'] = canonical_hash(value)
    validate(value)
    return value
