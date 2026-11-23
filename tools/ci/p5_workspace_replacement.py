"""Keyless CI component probe: real path replacement after close, before final stat."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import patch

from lightyear_factory.contracts import ContractError
from lightyear_factory.workspace import IsolatedWorkspace

CASES = ('clean', 'path-replacement')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def identity(info):
    return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_nlink]


def validate(value):
    def require(ok):
        if not ok:
            raise ValueError('p5-workspace-replacement-invalid')
    try:
        require(value['schema'] == 'p5-keyless-workspace-replacement/1')
        require(value['scope'] == 'real workspace scan component; no controller admission or production receipt')
        require(value['case'] in CASES)
        require(value['source_before_sha256'] == value['source_after_sha256'])
        before = bytes.fromhex(value['before_hex']); after = bytes.fromhex(value['after_hex'])
        require(0 < len(before) == len(after) < 1024)
        require(digest(before) == value['source_before_sha256'])
        require(digest(after) == value['workspace_after_sha256'])
        require(value['read_sha256'] == digest(before))
        require(value['read_closed_before_final_stat'] is True)
        old, new = value['identity_before'], value['identity_after']
        require(len(old) == len(new) == 5 and all(type(i) is int for i in old + new))
        require(old[2] == new[2] == len(before) and old[3] == new[3] and old[4] == new[4] == 1)
        if value['case'] == 'clean':
            require(value['replacements'] == 0 and old == new and before == after)
            require(value['outcome'] == 'passed' and value['file_scan_sha256'] == [digest(before)])
            require(value['scan_result']['files'] == 1 and value['scan_result']['bytes'] == len(before))
        else:
            require(value['replacements'] == 1 and old[1] != new[1] and before != after)
            require(value['outcome'] == 'workspace-isolation-refused')
            require(value['file_scan_sha256'] == [] and value['scan_result'] is None)
        require(value['production_controller_receipt'] is False)
        return True
    except (KeyError, TypeError, ValueError, IndexError):
        raise ValueError('p5-workspace-replacement-invalid') from None


def observe_case(parent, case):
    if os.environ.get('GITHUB_ACTIONS') != 'true' or case not in CASES:
        raise ValueError('p5-workspace-replacement-ci-only')
    parent = Path(parent); parent.mkdir()
    # IsolatedWorkspace resolves its root. Use the same canonical path for the
    # interception target, including Windows short-name and lexical aliases.
    parent = parent.resolve(strict=True)
    source = parent/'source'; root = parent/'workspace'
    source.mkdir(); root.mkdir()
    original = b'print("original")\n'; replacement = b'print("replaced")\n'
    assert len(original) == len(replacement)
    (source/'worker.py').write_bytes(original)
    target = root/'worker.py'; target.write_bytes(original)
    old = target.stat()
    staging = parent/'replacement.py'; staging.write_bytes(replacement)
    os.utime(staging, ns=(old.st_atime_ns, old.st_mtime_ns))
    workspace = IsolatedWorkspace(source, root, ('worker.py',), {'worker.py': digest(original)})
    # Prebuilt public fixture avoids authority/keys/canary creation. The scan itself is unchanged.
    real_open, real_stat = Path.open, Path.stat
    opened = closed = checked = False
    reads = []; replacements = []; file_scans = []
    handle_identities = []

    class ReadWindow:
        def __init__(self, handle): self.handle = handle
        def __enter__(self): self.handle.__enter__(); return self
        def __exit__(self, *args):
            nonlocal closed
            result = self.handle.__exit__(*args); closed = True
            return result
        def fileno(self):
            descriptor = self.handle.fileno()
            handle_identities.append(identity(os.fstat(descriptor)))
            return descriptor
        def read(self, *args):
            raw = self.handle.read(*args); reads.append(digest(raw)); return raw

    def open_window(path, *args, **kwargs):
        nonlocal opened
        handle = real_open(path, *args, **kwargs)
        mode = args[0] if args else kwargs.get('mode', 'r')
        if path == target and mode == 'rb' and not opened:
            opened = True
            return ReadWindow(handle)
        return handle

    def final_stat(path, *args, **kwargs):
        nonlocal checked
        if path == target and closed and not checked and kwargs.get('follow_symlinks', True):
            checked = True
            if case == 'path-replacement':
                os.replace(staging, target)
                replacements.append(identity(real_stat(target)))
        return real_stat(path, *args, **kwargs)

    def scanner(surface, raw):
        if surface.endswith('-file'): file_scans.append(digest(raw))

    outcome = 'passed'; result = None
    with patch.object(Path, 'open', open_window), patch.object(Path, 'stat', final_stat):
        try:
            result = workspace.scan_contents(scanner, 'replacement-probe')
        except ContractError as error:
            outcome = str(error)
    value = dict(schema='p5-keyless-workspace-replacement/1', case=case,
        scope='real workspace scan component; no controller admission or production receipt',
        source_before_sha256=digest(original), source_after_sha256=digest((source/'worker.py').read_bytes()),
        before_hex=original.hex(), after_hex=target.read_bytes().hex(),
        workspace_after_sha256=digest(target.read_bytes()), read_sha256=reads[0] if len(reads) == 1 else None,
        read_closed_before_final_stat=closed and checked, replacements=len(replacements),
        identity_before=identity(old), identity_after=identity(target.stat()),
        file_scan_sha256=file_scans, outcome=outcome, scan_result=result, production_controller_receipt=False)
    try:
        validate(value)
    except ValueError as error:
        # Retain the failed observation, including the clean control. Never change
        # identity values, relax validation, skip a platform, or relabel a refusal.
        diagnostic = dict(observation=value, handle_identities=handle_identities,
                          opened=opened, closed=closed, final_stat_checked=checked,
                          read_sha256s=reads, replacement_identities=replacements)
        failure = ValueError('p5-workspace-replacement-invalid: '+json.dumps(diagnostic, sort_keys=True))
        failure.observation = diagnostic
        raise failure from error
    return value


def observe():
    with tempfile.TemporaryDirectory(prefix='p5-keyless-replacement-') as temp:
        rows = [observe_case(Path(temp)/case, case) for case in CASES]
    return rows


def validate_controller_case(value):
    """Validate a keyless controller experiment, never production admission."""
    from lightyear_factory.contracts import canonical_hash

    def require(ok):
        if not ok:
            raise ValueError('p5-controller-replacement-invalid')

    def original(row):
        raw = row['utf8'].encode('utf-8')
        require(0 < len(raw) <= 2 * 1024 * 1024 and digest(raw) == row['sha256'])
        return raw

    try:
        require(value['schema'] == 'p5-keyless-controller-replacement/1')
        require(value['case'] in CASES)
        require(value['scope'] == 'native scripted controller workspace scan; no admission or production receipt')
        require(value['production_controller_receipt'] is False and value['signing'] is False)
        require(type(value['real_model_calls']) is int and value['real_model_calls'] == 0)
        require(value['source_before_sha256'] == value['source_after_sha256'])
        order = json.loads(original(value['work_order']))
        require(canonical_hash(order) == value['work_order_sha256'])
        require(order['acceptance']['baseline_first'] is False)
        require(value['gates_executed'] is False)
        receipt = json.loads(original(value['receipt']))
        require(receipt['content_sha256'] == canonical_hash(receipt, {'content_sha256'}))
        require(receipt['status'] == 'blocked' and receipt['attempts'] == 1)
        require(receipt['work_order_sha256'] == value['work_order_sha256'])
        require(receipt.get('qualifies_for_factory_receipt') is not True)
        require('factory_build_receipt' not in receipt)
        events_raw = original(value['ledger'])
        require(events_raw.endswith(b'\n'))
        events = [json.loads(line) for line in events_raw.splitlines()]
        require(bool(events))
        previous = None
        for sequence, event in enumerate(events, 1):
            require(type(event['sequence']) is int and event['sequence'] == sequence)
            require(event['previous_sha256'] == previous)
            require(event['event_sha256'] == canonical_hash(event, {'event_sha256'}))
            previous = event['event_sha256']
        summary = json.loads(original(value['summary']))
        require(summary['receipt_sha256'] == receipt['content_sha256'])
        snapshots = [i for i, event in enumerate(events)
                     if event['event_sha256'] == receipt['ledger_head_sha256']]
        require(len(snapshots) == 1)
        tail = events[snapshots[0]+1:]
        if value['case'] == 'clean':
            require(receipt['event_count'] == snapshots[0]+1)
            before = {key: item for key, item in receipt.items() if key != 'content_sha256'}
            expected_tail = [('run-receipt-before-memory', before),
                             ('run-receipt', receipt), ('run-summary', summary)]
            require(len(tail) == len(expected_tail))
            for event, (name, document) in zip(tail, expected_tail):
                raw = json.dumps(document, sort_keys=True, ensure_ascii=False).encode('utf-8')
                require(event['kind'] == 'model_isolation_scan_passed')
                require(event['payload']['status'] == 'passed')
                require(event['payload']['scanned'] == [dict(artifact=name, sha256=digest(raw))])
        else:
            require(tail == [])
        require(any(e['kind'] == 'work_order_accepted' and
                    e['payload']['work_order_sha256'] == value['work_order_sha256'] for e in events))
        require(not any(e['kind'] == 'hardened_admission_bound' for e in events))
        require(not any(e['kind'] in ('baseline_verified', 'candidate_verified', 'acceptance_gates_passed') for e in events))
        refs = [e['payload'] for e in events if isinstance(e['payload'].get('path'), str)
                and e['payload']['path'].startswith('artifacts/')]
        retained = value['artifacts']
        require([r['path'] for r in refs] == [r['path'] for r in retained])
        require(len({r['path'] for r in retained}) == len(retained))
        roles = []
        for ref, row in zip(refs, retained):
            doc = json.loads(original(row))
            require(doc['run_id'] == value['run_id'])
            require(doc['content_sha256'] == canonical_hash(doc, {'content_sha256'}))
            require(doc['content_sha256'] == ref['content_sha256'])
            require(doc['artifact_type'] == ref['artifact_type'] and doc['role'] == ref['role'])
            require(doc['artifact_type'] != 'verification-report')
            if doc['artifact_type'] == 'model-call-evidence':
                content = doc['content']
                require(content['content_sha256'] == canonical_hash(content, {'content_sha256'}))
                require(content['role'] == doc['role'])
                roles.append(doc['role'])
        expected = ['planner'] + (['builder'] if value['case'] == 'clean' else [])
        require(roles == value['scripted_roles'] == expected)
        require(value['read_sha256s'] == [value['source_before_sha256']])
        require(value['opened'] is True and value['closed_before_final_stat'] is True)
        old, new = value['identity_before'], value['identity_after']
        require(len(old) == len(new) == 5 and all(type(x) is int for x in old + new))
        require(old[2:4] == new[2:4] and old[4] == new[4] == 1)
        builder = [row for row in value['boundaries'] if row['surface'] == 'builder-workspace']
        require(len(builder) == 1)
        if value['case'] == 'clean':
            require(value['replacements'] == 0 and old == new)
            require(value['workspace_after_sha256'] == value['source_before_sha256'])
            require(builder[0]['outcome'] == 'passed' and value['controller_error'] is None)
            require(any(e['kind'] == 'builder_blocked' for e in events))
            require(receipt['run_id'] == value['run_id'])
            require(receipt['execution_security']['production_ready'] is False)
        else:
            require(value['replacements'] == 1 and old[1] != new[1])
            require(value['workspace_after_sha256'] != value['source_before_sha256'])
            require(builder[0]['outcome'] == 'workspace-isolation-refused')
            require(value['controller_error'] == 'factory-isolation-run-refused')
            require(not any(e['kind'] in ('build_proposed', 'builder_blocked') for e in events))
            require(events[-1]['kind'] == 'controller_error')
            require(receipt['reason'] == 'factory-isolation-run-refused')
            require(receipt['failure_accounting']['calls'] == 1)
        return True
    except (KeyError, TypeError, ValueError, IndexError, AttributeError):
        raise ValueError('p5-controller-replacement-invalid') from None


def observe_controller_case(parent, case, *, baseline_first=False):
    """Actual builder read-window scan, with a no-edit scripted control.

    Baseline-first is false in this isolated component work order so no gate is
    executed. The builder returns no edits, and the controller remains blocked.
    baseline_first=True exists only for the negative regression proving that
    the unchanged container requirement refuses this keyless fixture.
    No Tower fixture, keys, signatures or production admission is created.
    """
    if os.environ.get('GITHUB_ACTIONS') != 'true' or case not in CASES:
        raise ValueError('p5-controller-replacement-ci-only')
    import sys
    from lightyear_factory.agents import ModelAgentSet
    from lightyear_factory.contracts import WorkOrder
    from lightyear_factory.orchestrator import FactoryOrchestrator
    from lightyear_factory.providers import ScriptedModelProvider

    parent = Path(parent); parent.mkdir(); parent = parent.resolve(strict=True)
    source = parent/'source'; source.mkdir()
    original = b'print("original")\n'; replacement = b'print("replaced")\n'
    assert len(original) == len(replacement)
    (source/'worker.py').write_bytes(original)
    staging = parent/'replacement.py'; staging.write_bytes(replacement)
    run_id = 'p5-keyless-controller-'+case
    runs = parent/'runs'; directory = runs/run_id
    target = directory/'workspace/worker.py'
    order = WorkOrder.from_dict(dict(schema_version='1.0', id='p5:controller-replacement',
        title='Public controller workspace replacement', goal='Refuse changed file identity before builder',
        scope=dict(allowed_paths=['worker.py'], graph_node_ids=[]),
        acceptance=dict(baseline_first=baseline_first, max_attempts=1,
            gates=[dict(id='public-expected-failure', command=[sys.executable, '-c', 'raise SystemExit(1)'],
                        timeout_seconds=5, expose_output_to_builder=False)]),
        policy=dict(allow_network=False, max_model_calls=3, max_elapsed_seconds=60, max_model_cost_usd=0), metadata={}))
    scripted = ScriptedModelProvider([
        dict(summary='Public plan', risks=[], tasks=[dict(id='scan', objective='Observe workspace refusal',
             paths=['worker.py'], graph_node_ids=[], evidence_capsule_ids=[])]),
        dict(summary='Public no-edit control', edits=[], blocked_reason='No edits authorized')])
    controller = FactoryOrchestrator(source, runs, ModelAgentSet(scripted),
        workspace_read_manifest={'worker.py': digest(original)})
    real_open, real_stat, real_scan = Path.open, Path.stat, IsolatedWorkspace.scan_contents
    active = None; opened = closed = checked = False
    old_identity = None; reads = []; replacements = []; boundaries = []

    class Window:
        def __init__(self, handle): self.handle = handle
        def __enter__(self): self.handle.__enter__(); return self
        def __exit__(self, *args):
            nonlocal closed
            result = self.handle.__exit__(*args); closed = True; return result
        def fileno(self): return self.handle.fileno()
        def read(self, *args):
            raw = self.handle.read(*args); reads.append(digest(raw)); return raw

    def open_window(path, *args, **kwargs):
        nonlocal opened
        handle = real_open(path, *args, **kwargs)
        mode = args[0] if args else kwargs.get('mode', 'r')
        if active == 'builder-workspace' and path == target and mode == 'rb' and not opened:
            opened = True
            return Window(handle)
        return handle

    def final_stat(path, *args, **kwargs):
        nonlocal checked
        if active == 'builder-workspace' and path == target and closed and not checked and kwargs.get('follow_symlinks', True):
            checked = True
            if case == 'path-replacement':
                os.replace(staging, target)
                replacements.append(identity(real_stat(target)))
        return real_stat(path, *args, **kwargs)

    def boundary(workspace, scanner, surface):
        nonlocal active, old_identity
        previous = active; active = surface
        if surface == 'builder-workspace':
            info = real_stat(target); old_identity = identity(info)
            os.utime(staging, ns=(info.st_atime_ns, info.st_mtime_ns))
        try:
            result = real_scan(workspace, scanner, surface)
        except ContractError as exc:
            boundaries.append(dict(surface=surface, outcome=str(exc))); raise
        else:
            boundaries.append(dict(surface=surface, outcome='passed')); return result
        finally:
            active = previous

    error = None
    with patch.object(Path, 'open', open_window), patch.object(Path, 'stat', final_stat), \
            patch.object(IsolatedWorkspace, 'scan_contents', boundary):
        try:
            controller.run(order, run_id)
        except ContractError as exc:
            error = str(exc)

    def retain(path):
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise ValueError('p5-controller-replacement-invalid') from exc
        if not 0 < len(raw) <= 2 * 1024 * 1024:
            raise ValueError('p5-controller-replacement-size')
        return dict(utf8=raw.decode('utf-8'), sha256=digest(raw))

    ledger = retain(directory/'events.jsonl')
    events = [json.loads(line) for line in ledger['utf8'].splitlines()]
    artifacts = []
    for event in events:
        relative = event['payload'].get('path')
        if isinstance(relative, str) and relative.startswith('artifacts/'):
            path = Path(relative); resolved = (directory/path).resolve()
            if path.is_absolute() or '..' in path.parts or directory not in resolved.parents:
                raise ValueError('p5-controller-replacement-artifact-path')
            artifacts.append(dict(path=relative, **retain(resolved)))
    value = dict(schema='p5-keyless-controller-replacement/1',
        scope='native scripted controller workspace scan; no admission or production receipt',
        case=case, run_id=run_id, work_order_sha256=order.content_sha256,
        source_before_sha256=digest(original), source_after_sha256=digest((source/'worker.py').read_bytes()),
        workspace_after_sha256=digest(target.read_bytes()), identity_before=old_identity,
        identity_after=identity(target.stat()), opened=opened, closed_before_final_stat=closed and checked,
        read_sha256s=reads, replacements=len(replacements), boundaries=boundaries,
        controller_error=error, scripted_roles=[r['role'] for r in scripted.requests],
        work_order=retain(directory/'work-order.json'), gates_executed=False,
        receipt=retain(directory/'receipt.json'), summary=retain(directory/'summary.json'),
        ledger=ledger, artifacts=artifacts,
        production_controller_receipt=False, real_model_calls=0, signing=False)
    validate_controller_case(value)
    return value
