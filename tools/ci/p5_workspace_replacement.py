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
