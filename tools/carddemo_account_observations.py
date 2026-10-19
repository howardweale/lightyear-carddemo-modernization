"""Reconcile retained screens, database snapshots and trace links without replaying applications."""
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
import json
import re
from tools.carddemo_account_evidence import json_document, json_rows, reference


def _canonical(value):
    if isinstance(value, bool) or value is None: return value
    if isinstance(value, (int, float)):
        return {'$number': format(Decimal(str(value)).normalize(), 'f')}
    if isinstance(value, dict): return {k: _canonical(v) for k, v in sorted(value.items())}
    if isinstance(value, list): return [_canonical(v) for v in value]
    return value


def _database(raw):
    value = json_document(raw)
    for item in value['authfrds']:
        item['auth_ts'] = datetime.fromisoformat(item['auth_ts']).isoformat(timespec='microseconds').rstrip('0').rstrip('.')
    return {table: sorted([_canonical(row) for row in rows], key=lambda row: json.dumps(row, sort_keys=True))
            for table, rows in value.items()}


def _attributes(frame):
    result = deepcopy(frame['attributes'])
    for value in result.values():
        value.setdefault('intensity', 'BRIGHT' if 'BRT' in value['basic'] else 'DARK' if value['hidden'] else 'NORMAL')
        value.setdefault('autoskip', 'ASKIP' in value['basic'])
    return result


def _screen(actual, expected):
    if actual['program'] != expected['program']: raise ValueError('account-observation-program')
    if expected.get('outside_slice'):
        if actual.get('endpoint') != '/not-in-this-slice': raise ValueError('account-observation-boundary')
    elif expected['ended']:
        if actual['message'] != expected['screen']['message']: raise ValueError('account-observation-text')
    elif (any(actual[key] != expected['screen'][key] for key in ('values', 'cursor', 'message'))
          or _attributes(actual) != _attributes(expected['screen'])):
        raise ValueError('account-observation-screen')


def verify_observations(archives, scopes, source):
    counts = {}; traces = {}
    for mode in ('api', 'browser', 'mutation'):
        files = archives['carddemo-proof-' + mode]; rows = json_rows(files['reference/cases.json'])
        frames = json_rows(files['browser/frames.json']) if mode == 'browser' else None
        if frames is not None and len(frames) != len(rows): raise ValueError('account-observation-frames')
        actual_states = {}; expected_states = {}; browser_states = {}
        if mode == 'api':
            for path, raw in files.items():
                if path.startswith('reference/database/') and path.endswith('.json'):
                    state = _database(raw)
                    digest = sha256(json.dumps(state, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
                    actual_states[digest] = state
        for index, row in enumerate(rows):
            path, digest = reference(row['database_file'])
            if path != 'expected-database/' + digest + '.json': raise ValueError('account-observation-database-path')
            if path not in expected_states:
                raw = files['reference/' + path]
                if sha256(raw).hexdigest() != digest: raise ValueError('account-observation-database-hash')
                expected_states[path] = json_document(raw)
            expected_db = expected_states[path]; expected = row['expected']
            area = expected.get('commarea')
            if area is not None and (not isinstance(area, str) or not re.fullmatch('(?:[0-9a-f]{2})*', area)):
                raise ValueError('account-observation-commarea')
            if mode == 'api':
                _screen(row['actual'], expected)
                if row['database_after_sha256'] != digest or actual_states.get(digest) != expected_db:
                    raise ValueError('account-observation-api-database')
            elif frames is not None:
                frame = frames[index]
                if any(frame[key] != row[key] for key in ('case', 'session', 'aid')):
                    raise ValueError('account-observation-frame-order')
                _screen(frame['screen'], expected)
                meta = frame['database_after']; name = meta['path']
                if not re.fullmatch('[0-9a-f]{64}\\.json', name): raise ValueError('account-observation-snapshot-path')
                if name not in browser_states:
                    actual = files['browser/database/' + name]
                    if sha256(actual).hexdigest() != name[:-5]: raise ValueError('account-observation-snapshot-hash')
                    browser_states[name] = _database(actual)
                if browser_states[name] != expected_db: raise ValueError('account-observation-browser-database')
        counts[mode] = len(rows)
    for key, scope in scopes.items():
        name = key.removeprefix('account_').removesuffix('_java').replace('_', '-')
        path = 'carddemo-web-bindings/account-' + name + '-trace.json'
        captures = [files[p] for files in archives.values() for p in (path, 'work/' + path) if p in files]
        hits = [json_document(raw) for raw in captures]
        if not hits or any(hit != hits[0] for hit in hits): raise ValueError('account-observation-trace-copies')
        trace = hits[0]; methods = trace['methods']
        if (trace['schema'] != 'carddemo-java-trace/1' or trace['program'] != 'COACTUPC'
                or trace['source'] != source or trace['remaining_statement_engine_programs'] != scope['remaining_statement_engine_programs']
                or {row['paragraph'] for row in methods} != set(scope['validation_paragraphs'])
                or {row['method'] for row in methods} != set(scope['rule_methods'])
                or {row['file'] for row in methods} != set(scope['java_files'])):
            raise ValueError('account-observation-trace-scope')
        traces[key] = {'path': path, 'sha256': sha256(captures[0]).hexdigest(),
                       'methods': methods}
    return {'retained_rows_verified': counts, 'trace_links': traces,
            'commarea': 'Exact returned COMMAREA comparisons are CI assertions in the bound Python/JavaScript proof sources; returned bytes are not separately retained for replay.',
            'database': 'Retained API and browser after-states reconciled against every expected table for all 678 rows.',
            'shared_dependencies': ['BMS parser', 'physical data plan and typed projection codec']}
