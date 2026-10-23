"""Howard-only held-out COPAU preparation. No signing, models or Tower access.

Private inputs and output fragments never cross this CLI's public boundary.
A separately reviewed public corpus closure index is mandatory. Its digest is
an approval input, not a claim that a directory listing proves completeness.
"""
import argparse
from datetime import datetime, timezone
import getpass
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import zipfile

from lightyear_factory import isolation_scan
from lightyear_factory.contracts import ContractError
from tools.copau_private_prerequisites import (
    ROOT, FREEZE_SHA, AMENDMENT_SHA, Store, Refused, require, load_json,
    encoded, bundle_info, no_links, windows_host,
)
from tools.copau_heldout_reference import run_session

SCANNER_SHA = '0f887ad5865655d4d12f08278a2339a57a1546b1e2feb6d9e3dd7b7aa4bcfa25'
WORKER_SHA = 'bb11b3644a6070d7176767d82826d451e0b5055a6ce3e5eda0495c45591b0771'
CORPORA = {'worker', 'public', 'history', 'graph'}
# Scanner plumbing only. These are public and NOT the held-out answer values.
CANARIES = {name: hashlib.sha256(('public-synthetic-scanner-probe:' + name).encode()).hexdigest()
            for name in isolation_scan.CLASSES}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def windows(values):
    result = set()
    for value in values:
        for text in (value, isolation_scan._normalized(value)):
            result.update(isolation_scan._normalized(text[i:i+40]) for i in range(max(0, len(text)-39)))
    result.discard('')
    return result


def stable_read(path, limit):
    no_links(path)
    before = path.stat()
    require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_size <= limit)
    with path.open('rb') as stream:
        raw = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns))
    last = path.stat()
    require((last.st_dev, last.st_ino, last.st_size, last.st_mtime_ns) ==
            (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            and len(raw) == before.st_size)
    no_links(path)
    return raw


def member_name(name):
    path = PurePosixPath(name)
    require(name and '\\' not in name and not path.is_absolute() and ':' not in name
            and all(p not in ('', '.', '..') for p in name.rstrip('/').split('/')))
    return path


def views(raw, archive, depth=0):
    """No extraction or execution. Unsupported/overlarge content is an error."""
    require(depth <= 3)
    if not archive:
        require(len(raw) <= isolation_scan.MAX_BYTES)
        yield raw
        return
    require(len(raw) <= 256 * 1024 * 1024)
    with zipfile.ZipFile(io.BytesIO(raw)) as zipped:
        members = zipped.infolist()
        require(len(members) <= 20000)
        names = set(); total = 0
        for item in members:
            member_name(item.filename)
            require(item.filename not in names and not item.flag_bits & 1)
            names.add(item.filename)
            mode = item.external_attr >> 16
            require(not stat.S_ISLNK(mode))
            if item.is_dir():
                continue
            require(stat.S_IFMT(mode) in (0, stat.S_IFREG))
            total += item.file_size
            require(total <= 512 * 1024 * 1024 and item.file_size <= 256 * 1024 * 1024)
            data = zipped.read(item)
            require(len(data) == item.file_size)
            # Include member names in the scan; they are public output too.
            yield item.filename.encode()
            yield from views(data, item.filename.lower().endswith(('.zip', '.jar', '.whl')), depth+1)


def scan_bytes(raw, values):
    try:
        isolation_scan.scan([('public-corpus-record', raw)], CANARIES, values)
        return 0, 0
    except ContractError as error:
        if str(error) == 'isolation-breach':
            return 1, 0
        return 0, 1


def directory_records(root, rows):
    require(root.is_absolute())
    no_links(root)
    expected = set()
    for row in rows:
        path = member_name(row['path'])
        require(str(path) not in expected)
        expected.add(str(path))
    actual = set()
    for path in root.rglob('*'):
        no_links(path)
        if path.is_file():
            actual.add(path.relative_to(root).as_posix())
    require(actual == expected)
    for row in rows:
        raw = stable_read(root / row['path'], 256 * 1024 * 1024)
        require(sha(raw) == row['sha256'] and len(raw) == row['size_bytes'])
        yield row, raw


def git_bytes(root, *args, data=None):
    result = subprocess.run(['git', '-C', str(root), *args], input=data,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
    require(result.returncode == 0)
    return result.stdout


def history_records(root, row):
    # The reviewed index binds the exact locally retained public ref inventory.
    # Deleted/unavailable history must be listed in index.unavailable, never omitted.
    require(git_bytes(root, 'rev-parse', '--is-shallow-repository').strip() == b'false')
    refs = git_bytes(root, 'show-ref').splitlines()
    require(sha(b'\n'.join(sorted(refs)) + b'\n') == row['refs_sha256'])
    objects = git_bytes(root, 'rev-list', '--objects', '--all').splitlines()
    ids = sorted({line.split(b' ', 1)[0] for line in objects})
    require(sha(b'\n'.join(ids) + b'\n') == row['objects_sha256'] and len(ids) == row['object_count'])
    for oid in ids:
        kind = git_bytes(root, 'cat-file', '-t', oid.decode()).strip()
        if kind != b'blob':
            continue
        size = int(git_bytes(root, 'cat-file', '-s', oid.decode()))
        require(size <= 256 * 1024 * 1024)
        raw = git_bytes(root, 'cat-file', 'blob', oid.decode())
        require(len(raw) == size)
        yield dict(sha256=sha(raw), size_bytes=size, archive=zipfile.is_zipfile(io.BytesIO(raw))), raw


def validate_index(index):
    require(set(index) == {'schema', 'captured_at', 'corpora', 'unavailable', 'closure_review'})
    require(index['schema'] == 'copau-public-corpus-index/1' and set(index['corpora']) == CORPORA)
    require(datetime.fromisoformat(index['captured_at']).utcoffset() is not None)
    require(index['closure_review']['status'] == 'reviewed-complete'
            and len(index['closure_review']['reference']) > 0)
    require(isinstance(index['unavailable'], list))
    # Only public identifiers may be disclosed for unavailable material.
    for item in index['unavailable']:
        require(set(item) == {'corpus', 'kind', 'id'} and item['corpus'] in CORPORA
                and item['kind'] in ('artifact', 'release-asset', 'git-object', 'graph-snapshot', 'unknown-history')
                and ((type(item['id']) is int and item['id'] > 0) or
                     (isinstance(item['id'], str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', item['id']))))
    worker = index['corpora']['worker']
    manifest = stable_read(Path(worker['manifest']), 2 * 1024 * 1024)
    require(sha(manifest) == WORKER_SHA)
    bindings = load_json(manifest)
    require(len(bindings) == 403 and len(worker['files']) == 403)
    require({r['path']: r['sha256'] for r in worker['files']} == bindings)
    for name in ('public', 'graph'):
        corpus = index['corpora'][name]
        require(corpus['files'] and corpus['records'] > 0 and corpus['inventory_complete'] is True)
        require(corpus['inventory_sha256'] == sha(encoded(corpus['files'])))
    public = index['corpora']['public']
    require(set(public['observed_ids']) == {r['public_id'] for r in public['files']} |
            {str(r['kind']) + ':' + str(r['id']) for r in index['unavailable']
             if r['corpus'] == 'public' and r['kind'] in ('artifact', 'release-asset')})
    require(len(public['observed_ids']) == len(set(public['observed_ids'])))
    require(re.fullmatch(r'[0-9a-f]{64}', index['corpora']['graph']['query_boundary_sha256']) and
            index['corpora']['graph']['all_queryable_snapshots_included'] is True)
    return index


def scan_corpora(index, values):
    validate_index(index)
    require(all(isinstance(v, str) and len(v) == 40 and not any(c.isspace() for c in v) for v in values))
    require(len(windows(values)) == len(values))
    report = dict(schema='copau-public-collision-report/1', corpus_index_sha256=sha(encoded(index)),
                  scanner_sha256=SCANNER_SHA, window_count=len(windows(values)), corpora={},
                  unavailable=index['unavailable'], qualified=False)
    for name in sorted(CORPORA):
        corpus = index['corpora'][name]
        row = dict(file_count=0, record_count=0, window_count=len(windows(values)), match_count=0,
                   missing_count=sum(x['corpus'] == name for x in index['unavailable']), error_count=0)
        inventory = []
        try:
            records = (history_records(Path(corpus['root']), corpus) if name == 'history'
                       else directory_records(Path(corpus['root']), corpus['files']))
            for meta, raw in records:
                row['file_count'] += 1
                inventory.append([sha(raw), len(raw)])
                try:
                    for content in views(raw, meta.get('archive', False)):
                        row['record_count'] += 1
                        matches, errors = scan_bytes(content, values)
                        row['match_count'] += matches; row['error_count'] += errors
                except Exception:
                    row['error_count'] += 1
        except Exception:
            row['error_count'] += 1
        row['corpus_sha256'] = sha(encoded(sorted(inventory)))
        report['corpora'][name] = row
    report['qualified'] = all(row['file_count'] > 0 and row['record_count'] > 0 and
                              row['match_count'] == row['missing_count'] == row['error_count'] == 0
                              for row in report['corpora'].values())
    return report


def prepare(store, root, seed, index):
    store.absent('heldout-provenance.json', 'heldout-collision-report.json', 'expected-source.json',
                 'copau-expected-values.json', 'bundle-binding.json', 'heldout-bundle-attestation.json')
    require(sha((root / 'src/lightyear_factory/isolation_scan.py').read_bytes()) == SCANNER_SHA)
    values, provenance = run_session(root, seed)
    # Prevent accidental acceptance of the public synthetic CI seed.
    require(seed not in (bytes(range(32)), bytes(reversed(range(32))), bytes(32)))
    report = scan_corpora(index, values)
    provenance.update(created_at=datetime.now(timezone.utc).isoformat(), private_seed_hex=seed.hex(),
                      values=values, corpus_index_sha256=sha(encoded(index)))
    store.write('heldout-provenance.json', encoded(provenance))
    store.write('heldout-collision-report.json', encoded(report))
    if not report['qualified']:
        return report, None
    source = dict(schema='copau-private-source/1', freeze_sha256=FREEZE_SHA, amendment_sha256=AMENDMENT_SHA,
                  source_reference='heldout-provenance.json',
                  coverage_description='Original COPAU authorization/fraud session; selected 40-character returned COMMAREA fragments. Does not detect isolated short display-field leakage. Corpus closure bound to reviewed public index.',
                  approved_expected_state_source=True, values=values)
    raw = encoded(dict(schema='factory-private-expected-values/1', values=values))
    info = bundle_info(raw)
    store.write('expected-source.json', encoded(source))
    store.write('copau-expected-values.json', raw)
    store.write('bundle-binding.json', encoded(info))
    store.write('heldout-bundle-attestation.json', encoded(info))
    return report, info


def main():
    try:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument('--reviewed-commit', required=True)
        parser.add_argument('--corpus-index', type=Path, required=True)
        parser.add_argument('--reviewed-corpus-sha256', required=True)
        parser.add_argument('--exposed-root', action='append', required=True)
        args = parser.parse_args()
        require(windows_host())
        root = Path(__file__).resolve().parents[1]
        require(Path.cwd().resolve() == root)
        require(git_bytes(root, 'rev-parse', 'HEAD').decode().strip() == args.reviewed_commit)
        require(not git_bytes(root, 'status', '--porcelain', '--untracked-files=all').strip())
        raw = stable_read(args.corpus_index.resolve(strict=True), 16 * 1024 * 1024)
        require(sha(raw) == args.reviewed_corpus_sha256)
        index = validate_index(load_json(raw))
        roots = [root, Path.cwd(), *args.exposed_root, *(Path(x['root']) for x in index['corpora'].values())]
        store = Store(ROOT, roots); store.check()
        seed_text = getpass.getpass('Private 64-hex-digit seed (never paste into chat): ')
        require(len(seed_text) == 64)
        seed = bytes.fromhex(seed_text)
        report, info = prepare(store, root, seed, index)
        # Closed public serialization: no seed, paths, output strings or matches.
        print(json.dumps(report, sort_keys=True))
        if info is not None:
            print(json.dumps(info, sort_keys=True))
            return 0
        return 2
    except Exception:
        print('REFUSED: preserve private files; inspect privately. No automatic retry.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
