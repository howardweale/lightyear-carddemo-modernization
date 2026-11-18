"""Explicit two-source PUBLIC freeze entry; never handles a held-out set.

Run this file with Python -I -B. Historical validation code is loaded only from
the separately verified qualification checkout. CI identity is never spoofed.
"""
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import urllib.request
import zipfile
import io

QUALIFICATION_COMMIT = '71a18164612ce574d889a39ceb335c5643721fc6'
QUALIFICATION_TREE = '7316662cb5cc52d5361ad1954c417b37e1e18fe5'
QUALIFICATION_SHA = '934457b92d24dfc330e078420b14cb529fa6478c6799347b53857e74af98784b'
EVIDENCE_MANIFEST_SHA = 'a489a3e66e556946827b20f53395847b290e1f61eafda78bbd0eef4fd225964f'
ARCHIVE_SHA = 'e81cc0f0c6a77a57c00ea258e8a4f7b66c6da690f8bc081097da9b1b6d4129b3'
BINDING_SHA = 'bb8b956a122c44ea70047848f56a2688f28071f2901df3b093a2af0e3ff758cb'
SUITE_SHA = '6da875e28f95409290f77363c135ef98af395fe3448c9bf3e3da28b4cad370b2'
REPOSITORY = 'howardweale/lightyear-carddemo-modernization'
RELEASE = 'https://github.com/' + REPOSITORY + '/releases/download/full-intcalc-reference-qualification-results-20261117-r1/'
WORKFLOW = '.github/workflows/intcalc-public-reference-freeze.yml'
TOOL = 'tools/intcalc_public_freeze_wrapper.py'
MAX_BYTES = 32 * 1024 * 1024
CODES = frozenset(('freeze-json', 'freeze-approval', 'freeze-ci', 'freeze-source',
                   'freeze-source-dirty', 'freeze-path', 'freeze-fetch', 'freeze-hash',
                   'freeze-archive', 'freeze-reference', 'freeze-criterion',
                   'freeze-reference-hand', 'freeze-readback', 'freeze-write',
                   'freeze-unexpected-fault'))


class Refused(ValueError):
    pass


def require(ok, code):
    if not ok:
        raise Refused(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    def walk(v):
        if type(v) in (str, int, bool) or v is None:
            return
        if type(v) is list:
            for item in v:
                walk(item)
            return
        require(type(v) is dict and all(type(k) is str for k in v), 'freeze-json')
        for item in v.values():
            walk(item)
    walk(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def strict(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'freeze-json')
            result[key] = value
        return result
    def invalid(_):
        raise Refused('freeze-json')
    try:
        value = json.loads(raw, object_pairs_hook=pairs,
                           parse_float=invalid, parse_constant=invalid)
        canonical(value)
        return value
    except (UnicodeError, json.JSONDecodeError, TypeError, RecursionError) as exc:
        raise Refused('freeze-json') from exc


def checked_file(path, limit=MAX_BYTES):
    require(not path.is_symlink() and path.is_file() and path.stat().st_size <= limit,
            'freeze-path')
    with path.open('rb') as stream:
        raw = stream.read(limit + 1)
    require(len(raw) <= limit, 'freeze-path')
    return raw


def safe_relative(name):
    require(type(name) is str and '\\' not in name and '\x00' not in name,
            'freeze-archive')
    path = PurePosixPath(name)
    require(name and not path.is_absolute() and str(path) == name
            and all(p not in ('', '.', '..') and ':' not in p for p in path.parts),
            'freeze-archive')
    return path


def git_identity(root):
    require(root.is_dir() and not root.is_symlink(), 'freeze-source')
    def git(*args):
        env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
        p = subprocess.run(['git', '-C', str(root), *args], stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=30, check=False, env=env)
        require(p.returncode == 0, 'freeze-source')
        return p.stdout.decode('ascii').strip()
    commit, tree = git('rev-parse', 'HEAD'), git('rev-parse', 'HEAD^{tree}')
    require(re.fullmatch('[a-f0-9]{40}', commit) is not None
            and re.fullmatch('[a-f0-9]{40}', tree) is not None, 'freeze-source')
    require(not git('status', '--porcelain', '--untracked-files=all'), 'freeze-source-dirty')
    return commit, tree


def approval(raw, expected_hash, wrapper_commit, wrapper_tree):
    require(len(raw) <= 65536 and re.fullmatch('[a-f0-9]{64}', expected_hash)
            and sha(raw) == expected_hash, 'freeze-approval')
    row = strict(raw)
    keys = ('schema authority authorize_public_freeze scope wrapper_commit wrapper_tree '
            'qualification_commit qualification_tree qualification_sha256 '
            'evidence_manifest_sha256 binding_sha256 public_suite_sha256')
    require(type(row) is dict and set(row) == set(keys.split()), 'freeze-approval')
    expected = dict(schema='reference-two-source-public-freeze-approval/1', authority='Howard',
                    authorize_public_freeze=True, scope='PC-01..PC-16 only; no hidden set',
                    wrapper_commit=wrapper_commit, wrapper_tree=wrapper_tree,
                    qualification_commit=QUALIFICATION_COMMIT, qualification_tree=QUALIFICATION_TREE,
                    qualification_sha256=QUALIFICATION_SHA, evidence_manifest_sha256=EVIDENCE_MANIFEST_SHA,
                    binding_sha256=BINDING_SHA, public_suite_sha256=SUITE_SHA)
    require(row == expected and row['authorize_public_freeze'] is True, 'freeze-approval')
    return row


def ci_identity(env, expected_commit):
    require(env.get('GITHUB_ACTIONS') == 'true'
            and env.get('GITHUB_EVENT_NAME') == 'workflow_dispatch'
            and env.get('GITHUB_REF') == 'refs/heads/main'
            and env.get('GITHUB_REPOSITORY') == REPOSITORY
            and env.get('GITHUB_SHA') == expected_commit
            and re.fullmatch('[a-f0-9]{40}', expected_commit), 'freeze-ci')
    require(re.fullmatch('[0-9]+', env.get('GITHUB_RUN_ID', ''))
            and re.fullmatch('[0-9]+', env.get('GITHUB_RUN_ATTEMPT', '')), 'freeze-ci')


def fetch_asset(name, expected_hash, limit):
    require(name in ('MANIFEST.json', 'reference-per-run-qualification.zip'), 'freeze-fetch')
    try:
        with urllib.request.urlopen(RELEASE + name, timeout=60) as response:
            raw = response.read(limit + 1)
    except (OSError, ValueError) as exc:
        raise Refused('freeze-fetch') from exc
    require(len(raw) <= limit and sha(raw) == expected_hash, 'freeze-hash')
    return raw


def unpack(raw, destination):
    require(not destination.exists() and not destination.is_symlink(), 'freeze-path')
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            entries = archive.infolist()
            require(0 < len(entries) <= 512, 'freeze-archive')
            names, planned, total = set(), [], 0
            for info in entries:
                name = info.orig_filename
                require(name == info.filename, 'freeze-archive')
                require(name not in names and not info.is_dir() and not info.flag_bits & 1,
                        'freeze-archive')
                names.add(name)
                path = safe_relative(name)
                mode = (info.external_attr >> 16) & 0o170000
                require(mode in (0, stat.S_IFREG) and info.file_size <= MAX_BYTES, 'freeze-archive')
                total += info.file_size
                require(total <= MAX_BYTES, 'freeze-archive')
                data = archive.read(info)
                require(len(data) == info.file_size, 'freeze-archive')
                planned.append((path, data))
    except (zipfile.BadZipFile, RuntimeError, OSError, NotImplementedError) as exc:
        raise Refused('freeze-archive') from exc
    destination.mkdir(mode=0o700)
    for relative, data in planned:
        path = destination.joinpath(*relative.parts)
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        exclusive(path, data)


def exclusive(path, data):
    require(not path.is_symlink(), 'freeze-write')
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as exc:
        raise Refused('freeze-write') from exc
    require(checked_file(path) == data, 'freeze-readback')


def historical_validator(source):
    # Invoke this script directly with -I -B, never import another tools package
    # and then mutate its search path. Historical modules keep their own ROOT.
    require('tools' not in sys.modules, 'freeze-reference')
    sys.path.insert(0, str(source / 'src'))
    sys.path.insert(0, str(source))
    q = importlib.import_module('tools.intcalc_reference_per_run')
    require(Path(q.__file__).resolve() == source / 'tools/intcalc_reference_per_run.py'
            and q.ref.ROOT.resolve() == source, 'freeze-reference')
    return q


def check_sources(wrapper, source):
    wrapper, source = wrapper.resolve(), source.resolve()
    wrapper_identity = git_identity(wrapper)
    require(wrapper_identity[0] == os.environ.get('GITHUB_SHA')
            and git_identity(source) == (QUALIFICATION_COMMIT, QUALIFICATION_TREE), 'freeze-source')
    q = historical_validator(source)
    row, binding_hash, _, _, _, _ = q.load_binding()
    require(binding_hash == BINDING_SHA and row['public_suite_sha256'] == SUITE_SHA, 'freeze-hash')
    require(git_identity(wrapper) == wrapper_identity
            and git_identity(source) == (QUALIFICATION_COMMIT, QUALIFICATION_TREE), 'freeze-source')


def revalidate(q, evidence):
    row, binding_hash, req, suite, probes, source = q.load_binding()
    raw = checked_file(evidence / 'qualification.json')
    require(sha(raw) == QUALIFICATION_SHA and binding_hash == BINDING_SHA
            and row['public_suite_sha256'] == SUITE_SHA, 'freeze-hash')
    receipt = strict(raw)
    require(receipt['source_commit'] == QUALIFICATION_COMMIT
            and receipt['source_tree'] == QUALIFICATION_TREE
            and receipt['schema'] == 'intcalc-reference-qualification/1'
            and receipt['comparison_criterion_met'] is True
            and receipt['status'] == 'CRITERION_MET'
            and receipt['named_limits'] == q.LIMITS, 'freeze-criterion')
    require(q.observation_inventory(evidence, suite, probes) == receipt['observations'], 'freeze-criterion')
    report = q.ref.strict(checked_file(evidence / 'report.json'))
    require(q.attest(report, row, row['request']['sha256'], suite, probes, source), 'freeze-criterion')
    require(q.provisional.inventory_digest(q.ref.strict(checked_file(evidence / 'inventory.json')))
            == row['package_library_sha256'], 'freeze-criterion')
    require(strict(checked_file(evidence / 'container-cleanup.json'))['removed_and_absent'] is True,
            'freeze-criterion')
    return row, req, suite


def public_outputs(q, evidence, req, suite):
    require([c['id'] for c in suite['cases']] == ['PC-%02d' % n for n in range(1, 17)], 'freeze-criterion')
    planned = []
    for case in suite['cases']:
        outputs = {}
        for channel, descriptor in case['hand_outputs'].items():
            safe_relative(channel)
            data = checked_file(evidence / 'public' / case['id'] / 'observations/reference' / channel)
            require(data == q.ref.joined((q.ref.ROOT / req['suite']['path']).parent, descriptor),
                    'freeze-reference-hand')
            relative = case['id'] + '/' + channel
            outputs[channel] = dict(path=relative, sha256=sha(data), bytes=len(data))
            planned.append((relative, data))
        planned.append((case['id'] + '/expected.json', canonical(dict(
            exit=case['hand_exit'], compare_output_files=q.ref.comparison_policy(case), outputs=outputs)) + b'\n'))
    return planned


def fresh_output(output, wrapper, source):
    require(output.is_absolute() and '..' not in output.parts and output.name not in ('', '.', '..'),
            'freeze-path')
    for parent in (output, *output.parents):
        require(not parent.is_symlink(), 'freeze-path')
    require(output.parent.is_dir() and output.parent.resolve() == output.parent
            and not output.exists(), 'freeze-path')
    require(not output.is_relative_to(wrapper) and not output.is_relative_to(source), 'freeze-path')
    return output


def answer_manifest(before, row, files, approval_hash, tool_hash, workflow_hash, env):
    return dict(schema='reference-public-answer-key/2', visibility='public',
                qualification_commit=QUALIFICATION_COMMIT, qualification_tree=QUALIFICATION_TREE,
                wrapper_commit=before[0], wrapper_tree=before[1],
                wrapper_tool_sha256=tool_hash, wrapper_workflow_sha256=workflow_hash,
                qualification_sha256=QUALIFICATION_SHA, evidence_manifest_sha256=EVIDENCE_MANIFEST_SHA,
                evidence_archive_sha256=ARCHIVE_SHA, binding_sha256=BINDING_SHA,
                public_suite_sha256=SUITE_SHA, approval_sha256=approval_hash,
                run_id=int(env['GITHUB_RUN_ID']), run_attempt=int(env['GITHUB_RUN_ATTEMPT']),
                named_limits=row['named_limits'], files=files)


def freeze(wrapper, source, output, raw_approval, approval_hash, expected_commit):
    require(os.name == 'posix' and sys.dont_write_bytecode, 'freeze-ci')
    wrapper, source = wrapper.resolve(), source.resolve()
    ci_identity(os.environ, expected_commit)
    before = git_identity(wrapper)
    require(before[0] == expected_commit and wrapper != source, 'freeze-source')
    require(git_identity(source) == (QUALIFICATION_COMMIT, QUALIFICATION_TREE), 'freeze-source')
    approval(raw_approval, approval_hash, *before)
    output = fresh_output(output, wrapper, source)
    output.mkdir(mode=0o700)
    manifest_raw = fetch_asset('MANIFEST.json', EVIDENCE_MANIFEST_SHA, 65536)
    manifest = strict(manifest_raw)
    rows = [r for r in manifest['files'] if r['name'] == 'reference-per-run-qualification.zip']
    require(len(rows) == 1 and rows[0]['sha256'] == ARCHIVE_SHA and rows[0]['bytes'] == 63315,
            'freeze-hash')
    raw = fetch_asset('reference-per-run-qualification.zip', ARCHIVE_SHA, 63315)
    evidence = output / 'qualification-evidence'
    unpack(raw, evidence)
    q = historical_validator(source)
    row, req, suite = revalidate(q, evidence)
    planned = public_outputs(q, evidence, req, suite)
    require(git_identity(wrapper) == before
            and git_identity(source) == (QUALIFICATION_COMMIT, QUALIFICATION_TREE), 'freeze-source')
    answer = output / 'public-answer-key'
    answer.mkdir(mode=0o700)
    files = []
    for relative, data in planned:
        path = answer.joinpath(*safe_relative(relative).parts)
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        exclusive(path, data)
        files.append(dict(path=relative, bytes=len(data), sha256=sha(data)))
    final = answer_manifest(before, row, files, approval_hash,
                            sha(checked_file(wrapper / TOOL)), sha(checked_file(wrapper / WORKFLOW)), os.environ)
    exclusive(answer / 'APPROVAL.json', raw_approval)
    require(git_identity(wrapper) == before
            and git_identity(source) == (QUALIFICATION_COMMIT, QUALIFICATION_TREE), 'freeze-source')
    exclusive(answer / 'MANIFEST.json', canonical(final) + b'\n')
    return final


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wrapper', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--check-sources', action='store_true')
    args = parser.parse_args()
    try:
        if args.check_sources:
            require(args.output is None, 'freeze-path')
            check_sources(args.wrapper, args.source)
            print('public-freeze-two-source-binding-match')
            return 0
        require(args.output is not None, 'freeze-path')
        freeze(args.wrapper, args.source, args.output,
               os.environ.get('PUBLIC_FREEZE_APPROVAL', '').encode('utf-8'),
               os.environ.get('PUBLIC_FREEZE_APPROVAL_SHA256', ''),
               os.environ.get('EXPECTED_WRAPPER_COMMIT', ''))
        print('public-reference-freeze-complete')
        return 0
    except Refused as exc:
        print(str(exc) if str(exc) in CODES else 'freeze-unexpected-fault')
        return 2
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception:
        print('freeze-unexpected-fault')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
