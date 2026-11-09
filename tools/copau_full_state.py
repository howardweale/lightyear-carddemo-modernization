"""Full frozen N1 oracle capture, input-only staging and comparison primitives.

Library only. No private CLI, candidate launcher, transaction observer, signing,
result authentication or admission is supplied. CI uses public synthetic inputs.
"""
import ast
from copy import deepcopy
from datetime import date, datetime
from itertools import count
import json
from pathlib import Path
from types import SimpleNamespace

from lightyear_execution import copau_full_state_contract as contract
from tools import copau_heldout_reference as reference


def bindings():
    return dict(reference.PINNED, freeze=reference.FREEZE_SHA,
                amendment=reference.AMENDMENT_SHA)


def prepare_inputs(store, root, seed, *, context_sha256):
    # verify_producer imports definitions but does not construct/run Engine.
    _, helpers = reference.verify_producer(root)
    login, raw, _ = reference.fixture_inputs(seed, helpers)
    return contract.stage_inputs(store, dict(login=login, raw_fixture=raw),
            context_sha256=context_sha256, producer_bindings=bindings())


def _pg_input(value):
    # Preserve native numbers for Proof.expected_state's ordinal lookup.
    if isinstance(value, bytes):
        return '\\x' + value.hex()
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _pg_input(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_pg_input(v) for v in value]
    return value


def independent_initial(producer, entries, fixture, identity):
    """Project committed raw input, never use a candidate snapshot as baseline.

    The shared mapping/codec projection is the same disclosed dependency as the
    frozen judge. The independent loader must later produce this exact inventory,
    including empty quarantine/child tables and the fixture identity row.
    """
    lookup = {m['table']: (layout, m) for _, layout, m in entries}
    state = {'authfrds': [], 'slice_fixture_identity': [{'identity': identity}]}
    for _, _, m in entries:
        for table in [m['table'], 'quarantine_' + m['table'], *m['children']]:
            contract.require(table not in state)
            state[table] = []
    parents, seen = {}, set()
    for item in fixture['records']:
        identity = item['identity']
        contract.require(identity not in seen and item['table'] in lookup)
        seen.add(identity)
        table, ordinal = identity.split(':')
        contract.require(table == item['table'] and ordinal.isdigit() and int(ordinal) > 0)
        layout, mapping = lookup[table]
        parent = item.get('parent')
        contract.require(parent is None or parent in parents)
        # Existing session has keyed VSAM and explicit ordered IMS records.
        # Unsupported unkeyed positions are refused by Store, never invented.
        row, children = producer.Store(None, mapping, layout).project_rows(
            bytes.fromhex(item['raw']), int(ordinal),
            parent_path=parents.get(parent),
            twin_seq=int(ordinal) if mapping.get('segment') else None)
        if mapping.get('segment'):
            parents[identity] = row['path_key']
        state[table].append(_pg_input(row))
        for (child, _), values in children.items():
            state[child].append(_pg_input(values))
    return state


class _PrivateBlobs:
    """Only the frozen step's content-addressed Path operations, in private RAM."""
    def __init__(self, blobs=None, path=''):
        self.blobs = {} if blobs is None else blobs
        self.path = path

    def __truediv__(self, part):
        path = self.path + ('/' if self.path else '') + str(part)
        contract.require(path == 'expected-database' or
            (path.startswith('expected-database/') and path.endswith('.json')
             and contract.SHA.fullmatch(path[18:-5])))
        return _PrivateBlobs(self.blobs, path)

    @property
    def parent(self):
        return _PrivateBlobs(self.blobs, self.path.rsplit('/', 1)[0])

    def mkdir(self, **_):
        contract.require(self.path == 'expected-database')

    def exists(self):
        return self.path in self.blobs

    def write_bytes(self, raw):
        contract.require(not self.exists() and self.path[18:-5] == contract.sha(raw))
        contract.require(sum(map(len, self.blobs.values())) + len(raw) <= contract.LIMIT)
        self.blobs[self.path] = bytes(raw)

    def read_bytes(self):
        return self.blobs[self.path]


def canonical_state(producer, state):
    # Exact frozen timestamp/row-multiset normalization; no row/column exclusions.
    state = deepcopy(state)
    for row in state.get('authfrds', []):
        row['auth_ts'] = datetime.fromisoformat(row['auth_ts']).isoformat(
            timespec='microseconds').rstrip('0').rstrip('.')
    return {table: sorted([producer.canonical(row) for row in rows],
                key=lambda r: json.dumps(r, sort_keys=True)) for table, rows in state.items()}


def capture(store, root, *, acknowledgment_verifier):
    # Persist consumption before verify/import/Engine or any oracle step. A fault
    # leaves a consumed attempt, with no completion and no retry/reseed path.
    inputs, binding = contract.consume(store, verifier=acknowledgment_verifier,
                                      producer_bindings=bindings())
    try:
        producer, helpers = reference.verify_producer(root)
        _, entries = helpers.build(Path('spec/modernization/carddemo-data'))
        initial = independent_initial(producer, entries, inputs['raw_fixture'],
                                      contract.sha(contract.encoded(inputs)))
        proof = producer.Proof.__new__(producer.Proof)
        proof.args = SimpleNamespace(reference_only=True)
        proof.out = _PrivateBlobs()
        proof.fixture = inputs['login']
        proof.raw_fixture = inputs['raw_fixture']
        proof.engine = producer.Engine(proof.raw_fixture)
        proof.engine.store.fraud = deepcopy(initial['authfrds'])
        proof.initial = initial
        proof.entries = {m['table']: (layout, m) for _, layout, m in entries}
        proof.seen, proof.rows, proof.sessions = set(), [], count(1)
        proof.current, proof.token, proof.case_id, proof.session = None, None, '', 0
        source = (root / 'factory/carddemo-web/runtime/prove_slice.py').read_bytes()
        # verify_producer just checked this exact hash and the other 153 files.
        contract.require(contract.sha(source) == reference.PINNED[
            'factory/carddemo-web/runtime/prove_slice.py'])
        tree = ast.parse(source)
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Proof')
        run = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'run')
        session = [n for n in run.body if isinstance(n, ast.FunctionDef) and n.name == 'authorizations']
        contract.require(len(session) == 1)
        namespace = dict(self=proof, deepcopy=deepcopy)
        exec(compile(ast.Module(body=session, type_ignores=[]), '<frozen-N1-session>', 'exec'), namespace)
        namespace['authorizations']()
        # Proof.start/inputs/step/expected_state and all original assertions ran
        # unchanged. No Proof.__init__, candidate baseline or leakage-fragment path.
        before = canonical_state(producer, initial)
        initial_digest = contract.put_blob(store, 'n1-initial', contract.encoded(before))
        for row in proof.rows:
            expected = proof.out.blobs[row['database_file']['path']]
            contract.require(contract.sha(expected) == row['database_file']['sha256'])
            row['before_sha256'] = producer.digest(before)
            before = contract.decoded(expected)
            row['after_sha256'] = producer.digest(before)
        for i, (path, raw) in enumerate(sorted(proof.out.blobs.items())):
            contract.put_blob(store, f'n1-state-{i}', raw)
        artifact = dict(schema='copau-full-session-oracle/1', session=contract.SESSION,
            binding=binding, producer_bindings=bindings(), initial_sha256=initial_digest,
            rows=producer.canonical(proof.rows),
            states=[dict(path=path, blob=f'n1-state-{i}', sha256=contract.sha(raw))
                    for i, (path, raw) in enumerate(sorted(proof.out.blobs.items()))],
            reference_events=producer.canonical(proof.engine.store.events),
            transaction_observation='NOT_IMPLEMENTED', candidate_replay='NOT_RUN')
        artifact_sha = contract.put_blob(store, 'n1-oracle', contract.encoded(artifact))
        result = dict(binding, oracle_sha256=artifact_sha, interactions=len(proof.rows),
                      qualified=False, status='ORACLE_CAPTURE_ONLY')
        store.write('n1-complete.json', contract.encoded(result))
        return result
    except BaseException:
        # The original private exception/traceback must not leak through CLI/logs.
        raise contract.Refused('oracle-capture-failed-consumed') from None
