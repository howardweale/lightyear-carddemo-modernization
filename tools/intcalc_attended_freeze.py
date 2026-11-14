"""Public C2 attended-freeze admission and deterministic asset builder.

The generated entry contains verifier-only code: publish its hash, not its bytes.
This module contains no case definitions, oracle results or frozen answers.
"""
import argparse
import ast
from contextlib import contextmanager
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import signal
import stat
import subprocess
import sys
import time
import traceback
import zipfile

BUNDLE_HASH = '6936f0cfbad8925098ff8068d7b79a18f3a9a8d58ccc6b2d8c93c5c6d3f18e33'
CORE_HASH = 'dc642acc18e7e07663016c28780b075f3fcaf2415d4f8c6158e2cee8aa4420ee'
GUARD = '    if os.environ.get("GITHUB_ACTIONS")!="true":\n        raise ValueError("ci-only-oracle-freezing")\n'
ENTRY_MARKER = '# PUBLIC_COMMAND_ENTRY\n'
RECEIPT_FIELDS = {'schema', 'source_commit', 'source_tree', 'bundle_sha256',
                  'controller_sha256', 'entry_sha256', 'case_manifest_sha256',
                  'outputs_sha256', 'equal', 'candidate_executed', 'model_calls', 'source_event', 'source_ref'}
REFUSAL_CODES = frozenset({
    'python-version', 'platform', 'standard-account', 'path-form', 'path-symlink',
    'path-kind', 'path-owner-mode', 'private-mode', 'file-size', 'json-duplicate',
    'json-number', 'json-format', 'receipt-schema', 'source-identity', 'receipt-hash',
    'receipt-result', 'receipt-origin', 'source-git', 'source-inventory-size',
    'source-commit', 'source-tree', 'source-dirty', 'source-untracked', 'source-kind',
    'source-bytes', 'source-empty', 'bundle-hash', 'bundle-inventory', 'bundle-entry',
    'bundle-length', 'core-hash', 'bundle-schema', 'bundle-member', 'core-guard-shape',
    'core-delta', 'controller-shape', 'entry-core', 'extracted-hash', 'destination-exists',
    'freeze-findings', 'source-changed', 'bundle-changed', 'isolated-entry', 'worker-channel',
    'worker-size', 'worker-schema', 'manifest-mismatch', 'template-hash', 'template-schema',
    'freeze-exit', 'freeze-child-fault', 'operator-interrupted', 'freeze-timeout',
    'operator-terminal', 'receipt-pin', 'controller-hash', 'entry-hash', 'fresh-destination',
    'operator-confirmation', 'arguments', 'attended-freeze-fault', 'equivalence-refused',
    'ci-only-equivalence', 'scratch-exists', 'fetch-hash', 'original-freeze-exit',
    'equivalence-difference', 'output-symlink', 'output-empty'})
CHILD_TOKEN = b'C2_FREEZE_REFUSED:'


class Refused(ValueError):
    pass


def public_code(error, fallback):
    code = str(error)
    return code if code in REFUSAL_CODES else fallback


def child_refusal(code):
    code = public_code(code, 'freeze-child-fault')
    print(CHILD_TOKEN.decode('ascii') + code, file=sys.stderr, flush=True)
    raise SystemExit(2)


@contextmanager
def private_parent_diagnosis(run_root):
    """Best-effort private traceback after exclusive run-root creation only."""
    try:
        yield
    except BaseException as exc:
        if not isinstance(exc, (Refused, KeyboardInterrupt, SystemExit, subprocess.TimeoutExpired)):
            try:
                checked_path(str(run_root), directory=True, private=True)
                fd = os.open(run_root / 'parent-private.log', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                    traceback.print_exc(file=stream)
            except Exception:
                # A log failure must not leak a traceback to the terminal or mask the original fault.
                pass
        raise


def log_end(fd):
    return os.fstat(fd).st_size


def read_child_refusal(fd, started_at):
    """Read only a bounded final token from this child's private log segment."""
    end = log_end(fd)
    size = min(max(0, end - started_at), 256)
    if not size:
        return 'freeze-exit'
    old = os.lseek(fd, 0, os.SEEK_CUR)
    try:
        os.lseek(fd, end - size, os.SEEK_SET)
        tail = os.read(fd, size)
    finally:
        os.lseek(fd, old, os.SEEK_SET)
    if not tail.endswith(b'\n'):
        return 'freeze-exit'
    last = tail.split(b'\n')[-2]
    if not last.startswith(CHILD_TOKEN):
        return 'freeze-exit'
    try:
        code = last[len(CHILD_TOKEN):].decode('ascii')
    except UnicodeDecodeError:
        return 'freeze-exit'
    return public_code(code, 'freeze-exit')


def need(ok, code):
    if not ok:
        raise Refused(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, 'json-duplicate')
            result[key] = value
        return result
    def refuse(_):
        raise Refused('json-number')
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
                          parse_float=refuse, parse_constant=refuse)
    except Refused:
        raise
    except Exception:
        raise Refused('json-format') from None


def is_hash(value, length=64):
    return isinstance(value, str) and len(value) == length and all(c in '0123456789abcdef' for c in value)


def posix():
    need(sys.version_info >= (3, 11), 'python-version')
    need(os.name == 'posix', 'platform')
    need(os.getuid() != 0, 'standard-account')


def checked_path(value, directory=False, private=False):
    posix()
    p = Path(value)
    need(p.is_absolute() and '..' not in p.parts, 'path-form')
    need(p.resolve(strict=True) == p, 'path-symlink')
    for part in (p, *p.parents):
        need(not part.is_symlink(), 'path-symlink')
    s = p.stat()
    need(stat.S_ISDIR(s.st_mode) if directory else stat.S_ISREG(s.st_mode), 'path-kind')
    need(s.st_uid == os.getuid() and not s.st_mode & 0o022, 'path-owner-mode')
    if private:
        need(stat.S_IMODE(s.st_mode) == (0o700 if directory else 0o600), 'private-mode')
    return p


def read_file(value, cap=1024 * 1024, private=False):
    p = checked_path(value, private=private)
    need(p.stat().st_size <= cap, 'file-size')
    with p.open('rb') as stream:
        raw = stream.read(cap + 1)
    need(len(raw) <= cap, 'file-size')
    return raw


def exclusive(path, raw):
    checked_path(str(path.parent), directory=True, private=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def validate_receipt(row, require_main=True):
    need(isinstance(row, dict) and set(row) == RECEIPT_FIELDS, 'receipt-schema')
    need(row['schema'] == 'c2-attended-freeze-equivalence/2', 'receipt-schema')
    need(row['source_event'] in ('push', 'pull_request') and isinstance(row['source_ref'], str), 'receipt-origin')
    if require_main:
        need(row['source_event'] == 'push' and row['source_ref'] == 'refs/heads/main', 'receipt-origin')
    need(is_hash(row['source_commit'], 40) and is_hash(row['source_tree'], 40), 'source-identity')
    for key in ('bundle_sha256', 'controller_sha256', 'entry_sha256', 'case_manifest_sha256', 'outputs_sha256'):
        need(is_hash(row[key]), 'receipt-hash')
    need(row['bundle_sha256'] == BUNDLE_HASH and row['equal'] is True
         and type(row['model_calls']) is int and row['model_calls'] == 0
         and row['candidate_executed'] is False, 'receipt-result')
    return row


def git(source, *args):
    result = subprocess.run(['/usr/bin/git', '-c', 'core.fsmonitor=false', '-C', str(source), *args],
                            capture_output=True, timeout=30,
                            env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'GIT_CONFIG_NOSYSTEM': '1',
                                 'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_OPTIONAL_LOCKS': '0'})
    need(result.returncode == 0, 'source-git')
    need(len(result.stdout) <= 16 * 1024 * 1024, 'source-inventory-size')
    return result.stdout


def source_admission(value, commit, tree):
    need(is_hash(commit, 40) and is_hash(tree, 40), 'source-identity')
    source = checked_path(value, directory=True)
    need(git(source, 'rev-parse', 'HEAD').decode().strip() == commit, 'source-commit')
    need(git(source, 'rev-parse', 'HEAD^{tree}').decode().strip() == tree, 'source-tree')
    need(not git(source, 'status', '--porcelain=v1', '--untracked-files=all'), 'source-dirty')
    # No exclude-standard: ignored untracked files can shadow imports too.
    need(not git(source, 'ls-files', '--others'), 'source-untracked')
    hashes = {}
    for item in git(source, 'ls-tree', '-rz', 'HEAD').split(b'\0'):
        if not item:
            continue
        metadata, raw_path = item.split(b'\t', 1)
        mode, kind, oid = metadata.decode().split()
        path = raw_path.decode('utf-8')
        if not (path.startswith(('src/', 'spec/', 'tools/')) or path == 'tests/fixtures/intcalc-c1/Main.java'):
            continue
        need(mode in ('100644', '100755') and kind == 'blob', 'source-kind')
        content = read_file(str(source / path), cap=16 * 1024 * 1024)
        need(hashlib.sha1(b'blob ' + str(len(content)).encode() + b'\0' + content).hexdigest() == oid, 'source-bytes')
        hashes[path] = sha(content)
    need(hashes, 'source-empty')
    return source, sha(canonical(hashes))


def bundle_files(value):
    raw = read_file(value, private=True)
    need(sha(raw) == BUNDLE_HASH, 'bundle-hash')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = archive.infolist()
        need(len(entries) == 3 and {e.filename for e in entries} == {'BUNDLE.json', 'cases.json', 'freeze.py'}, 'bundle-inventory')
        files = {}
        for entry in entries:
            need(not entry.is_dir() and not entry.flag_bits & 1 and 0 <= entry.file_size <= 128 * 1024, 'bundle-entry')
            files[entry.filename] = archive.read(entry)
            need(len(files[entry.filename]) == entry.file_size, 'bundle-length')
    need(sha(files['freeze.py']) == CORE_HASH, 'core-hash')
    manifest = strict_json(files['BUNDLE.json'])
    need(manifest['model_context_eligible'] is False and set(manifest['files']) == {'cases.json', 'freeze.py'}, 'bundle-schema')
    for name, row in manifest['files'].items():
        need(sha(files[name]) == row['sha256'] and len(files[name]) == row['bytes'], 'bundle-member')
    return files


def core_text(raw):
    """Replace only the exact legacy environment guard in the NEW private asset."""
    need(sha(raw) == CORE_HASH, 'core-hash')
    source = raw.decode('utf-8')
    need(source.count(GUARD) == 1, 'core-guard-shape')
    result = source.replace(GUARD, '    pass  # Separate attended source admission precedes imports.\n')
    before, after = ast.parse(source), ast.parse(result)
    original = next(n for n in before.body if isinstance(n, ast.FunctionDef) and n.name == 'prepare')
    revised = next(n for n in after.body if isinstance(n, ast.FunctionDef) and n.name == 'prepare')
    need(isinstance(original.body[0], ast.If) and isinstance(revised.body[0], ast.Pass), 'core-guard-shape')
    original.body[0] = ast.Pass()
    need(ast.dump(before, include_attributes=False) == ast.dump(after, include_attributes=False), 'core-delta')
    return result


def build_entry(core, controller):
    text = controller.decode('utf-8')
    need(text.count('\n' + ENTRY_MARKER) == 1, 'controller-shape')
    prefix = text.split('\n' + ENTRY_MARKER)[0]
    # repr embeds the verifier-only source without importing or executing it.
    return (prefix + '\n\ntry:\n    worker(' + repr(core_text(core)) + ')\n'
            'except Refused as exc:\n    child_refusal(public_code(exc, "freeze-child-fault"))\n'
            'except KeyboardInterrupt:\n    child_refusal("operator-interrupted")\n'
            'except BaseException:\n    traceback.print_exc(file=sys.stderr)\n    child_refusal("freeze-child-fault")\n').encode('utf-8')


def run_core(text, source, archive, output, commit, tree):
    root, fingerprint = source_admission(str(source), commit, tree)
    files = bundle_files(str(archive))
    need(text == core_text(files['freeze.py']), 'entry-core')
    verifier = archive.parent
    for name, raw in files.items():
        need(read_file(str(verifier / name), private=True) == raw, 'extracted-hash')
    checked_path(str(output.parent), directory=True, private=True)
    need(not os.path.lexists(output), 'destination-exists')
    sys.path[:] = [str(root / 'src'), str(root)] + [p for p in sys.path if p and p not in (str(verifier), str(Path.cwd()))]
    scope = {'__name__': 'c2_attended_freezing_core', '__file__': str(verifier / 'freeze.py')}
    exec(compile(text, '<verified-freezing-core>', 'exec'), scope)
    need(scope['prepare'](root, output), 'freeze-findings')
    need(source_admission(str(root), commit, tree)[1] == fingerprint, 'source-changed')
    for name, raw in files.items():
        need(read_file(str(verifier / name), private=True) == raw, 'bundle-changed')


def worker(text):
    posix()
    need(sys.flags.isolated and sys.dont_write_bytecode, 'isolated-entry')
    need(stat.S_ISFIFO(os.fstat(0).st_mode), 'worker-channel')
    raw = sys.stdin.buffer.read(16385)
    need(len(raw) <= 16384, 'worker-size')
    row = strict_json(raw)
    need(isinstance(row, dict) and set(row) == {'source', 'archive', 'output', 'commit', 'tree'}, 'worker-schema')
    run_core(text, Path(row['source']), Path(row['archive']), Path(row['output']), row['commit'], row['tree'])


def manifest_matches(output, receipt):
    actual = sha(read_file(str(output / 'case-manifest.json'), private=True))
    need(actual == receipt['case_manifest_sha256'], 'manifest-mismatch')
    return actual


def bind(output, run_root, template, template_hash, receipt):
    manifest = manifest_matches(output, receipt)
    raw = read_file(str(template), private=True)
    need(sha(raw) == template_hash, 'template-hash')
    value = strict_json(raw)
    need(value.get('schema') == 'full-intcalc-c1/2' and value.get('runtime_platform') == 'linux/arm64'
         and value.get('artifact') == {'path': None, 'sha256': None} and 'byte_policy' not in value, 'template-schema')
    value['case_manifest'] = {'path': 'intcalc-frozen/case-manifest.json', 'sha256': manifest}
    exclusive(run_root / 'verifier-binding.json', canonical(value))


def child(entry, payload, log_fd, timeout=595):
    posix()
    process = None
    started = time.monotonic()
    segment_start = log_end(log_fd)
    try:
        process = subprocess.Popen([sys.executable, '-I', '-B', str(entry)], stdin=subprocess.PIPE,
                                   stdout=log_fd, stderr=log_fd, start_new_session=True, cwd=entry.parent,
                                   env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'})
        process.communicate(canonical(payload), timeout=max(0.01, timeout - (time.monotonic() - started)))
        if process.returncode != 0:
            raise Refused(read_child_refusal(log_fd, segment_start))
    finally:
        if process is not None and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)


def attended(args):
    posix()
    need(sys.platform == 'darwin' and platform.machine() == 'arm64', 'platform')
    need(sys.flags.isolated and sys.dont_write_bytecode, 'isolated-entry')
    need(sys.stdin.isatty() and sys.stdout.isatty(), 'operator-terminal')
    raw = read_file(args.receipt, private=True)
    need(is_hash(args.receipt_sha256) and sha(raw) == args.receipt_sha256, 'receipt-pin')
    receipt = validate_receipt(strict_json(raw))
    controller = read_file(str(Path(__file__).resolve()))
    need(sha(controller) == receipt['controller_sha256'], 'controller-hash')
    source, fingerprint = source_admission(args.source, receipt['source_commit'], receipt['source_tree'])
    archive = checked_path(args.bundle, private=True)
    files = bundle_files(str(archive))
    entry_raw = build_entry(files['freeze.py'], controller)
    need(sha(entry_raw) == receipt['entry_sha256'], 'entry-hash')
    run_root = Path(args.run_root)
    checked_path(str(run_root.parent), directory=True, private=True)
    need(run_root.is_absolute() and not os.path.lexists(run_root), 'fresh-destination')
    need(input('Type ATTENDED-FREEZE to confirm this approved setup: ') == 'ATTENDED-FREEZE', 'operator-confirmation')
    os.umask(0o077)
    run_root.mkdir(mode=0o700)
    with private_parent_diagnosis(run_root):
        for name in ('control', 'use-ledger', 'run-ledger', 'builds'):
            (run_root / name).mkdir(mode=0o700)
        entry = run_root / 'attended-freeze-entry.py'
        exclusive(entry, entry_raw)
        output = run_root / 'intcalc-frozen'
        log = os.open(run_root / 'freeze-private.log', os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            child(entry, dict(source=str(source), archive=str(archive), output=str(output),
                              commit=receipt['source_commit'], tree=receipt['source_tree']), log)
        finally:
            os.close(log)
        need(source_admission(str(source), receipt['source_commit'], receipt['source_tree'])[1] == fingerprint, 'source-changed')
        manifest_matches(output, receipt)
        bind(output, run_root, Path(args.template), args.template_sha256, receipt)
        exclusive(run_root / 'control' / 'freeze-binding-hashes.json', canonical(dict(
            schema='full-intcalc-private-setup-hashes/1', bundle_sha256=BUNDLE_HASH,
            case_manifest_sha256=receipt['case_manifest_sha256'],
            verifier_binding_sha256=sha(read_file(str(run_root / 'verifier-binding.json'), private=True)),
            template_sha256=args.template_sha256, qualified=False, production_controller_receipt=False)))
        exclusive(run_root / 'attended-provenance.json', canonical(dict(
            schema='c2-attended-freeze-private/1', source_commit=receipt['source_commit'], source_tree=receipt['source_tree'],
            qualification_receipt_sha256=args.receipt_sha256, bundle_sha256=BUNDLE_HASH,
            case_manifest_sha256=receipt['case_manifest_sha256'], entry_sha256=receipt['entry_sha256'],
            mode='ATTENDED', qualified=False, model_calls=0)))
        print('attended-freeze-binding-match')


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Refused('arguments')


def main():
    parser = Parser()
    for name in ('source', 'bundle', 'run-root', 'receipt', 'receipt-sha256', 'template', 'template-sha256'):
        parser.add_argument('--' + name, required=True)
    attended(parser.parse_args())


# PUBLIC_COMMAND_ENTRY
if __name__ == '__main__':
    try:
        main()
    except Refused as exc:
        print(public_code(exc, 'attended-freeze-fault'))
        raise SystemExit(2)
    except KeyboardInterrupt:
        print('operator-interrupted')
        raise SystemExit(130)
    except SystemExit:
        raise
    except subprocess.TimeoutExpired:
        print('freeze-timeout')
        raise SystemExit(2)
    except BaseException:
        print('attended-freeze-fault')
        raise SystemExit(2)
