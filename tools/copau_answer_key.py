"""Howard-only held-out COPAU preparation. No signing, models or Tower access.

Private inputs and output fragments never cross this CLI's public boundary.
A separately reviewed public corpus closure index is mandatory. Its digest is
an approval input, not a claim that a directory listing proves completeness.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import io
from itertools import chain
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
from tools import copau_seed_custody as seed_custody

SCANNER_SHA = '0f887ad5865655d4d12f08278a2339a57a1546b1e2feb6d9e3dd7b7aa4bcfa25'
WORKER_SHA = 'bb11b3644a6070d7176767d82826d451e0b5055a6ce3e5eda0495c45591b0771'
EXPOSURE = {'worker', 'graph', 'prompts', 'contexts'}
BASELINE = {'main', 'worker', 'graph'}
CORPORA = EXPOSURE | BASELINE
HISTORICAL = 'not inspected; not relevant to freshly generated values'
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


def main_records(root, row):
    require(re.fullmatch(r'[0-9a-f]{40}', row['commit']))
    listing = git_bytes(root, 'ls-tree', '-rz', '--full-tree', row['commit'])
    require(sha(listing) == row['tree_listing_sha256'])
    for entry in listing.split(b'\0'):
        if not entry:continue
        meta, path = entry.split(b'\t', 1); mode, kind, oid = meta.split()
        # Gitlinks and symlinks are unscanned surfaces, never skipped success.
        require(kind == b'blob' and mode in (b'100644', b'100755'))
        member_name(path.decode('utf-8'))
        size = int(git_bytes(root, 'cat-file', '-s', oid.decode()))
        require(size <= 256 * 1024 * 1024)
        raw = git_bytes(root, 'cat-file', 'blob', oid.decode()); require(len(raw) == size)
        yield dict(path=path.decode('utf-8'), sha256=sha(raw), size_bytes=size,
                   archive=zipfile.is_zipfile(io.BytesIO(raw))), raw


def validate_index(index):
    require(set(index) == {'schema', 'captured_at', 'corpora', 'unavailable', 'closure_review', 'historical'})
    require(index['schema'] == 'copau-run-surface-index/2' and set(index['corpora']) == CORPORA)
    require(datetime.fromisoformat(index['captured_at']).utcoffset() is not None)
    require(index['closure_review']['status'] == 'reviewed-complete'
            and len(index['closure_review']['reference']) > 0)
    require(isinstance(index['unavailable'], list))
    # Only public identifiers may be disclosed for unavailable material.
    for item in index['unavailable']:
        require(set(item) == {'corpus', 'kind', 'id'} and item['corpus'] in CORPORA
                and item['kind'] in ('file', 'git-object', 'graph-snapshot', 'template')
                and ((type(item['id']) is int and item['id'] > 0) or
                     (isinstance(item['id'], str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', item['id']))))
    worker = index['corpora']['worker']
    manifest = stable_read(Path(worker['manifest']), 2 * 1024 * 1024)
    require(sha(manifest) == WORKER_SHA)
    bindings = load_json(manifest)
    require(len(bindings) == 403 and len(worker['files']) == 403)
    require({r['path']: r['sha256'] for r in worker['files']} == bindings)
    history = index['historical']
    historical_keys = {'status', 'catalog_sha256', 'observed_count', 'missing', 'metadata_error_count'}
    require(set(history) in (historical_keys, historical_keys | {'catalog'}))
    if 'catalog' in history:
        require(len(history['catalog']) == history['observed_count']
                and sha(encoded(history['catalog'])) == history['catalog_sha256'])
        for item in history['catalog']:
            require(set(item) == {'kind', 'id'} and item['kind'] in ('artifact', 'release-asset')
                    and type(item['id']) is int and item['id'] > 0)
    require(history['status'] == HISTORICAL and re.fullmatch(r'[0-9a-f]{64}', history['catalog_sha256']))
    require(type(history['observed_count']) is int and history['observed_count'] >= 0
            and type(history['metadata_error_count']) is int and history['metadata_error_count'] >= 0)
    for item in history['missing']:
        require(set(item) == {'kind', 'id'} and item['kind'] in ('artifact', 'release-asset', 'unknown-history')
                and ((type(item['id']) is int and item['id'] > 0) or
                     (isinstance(item['id'], str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', item['id']))))
    for name in EXPOSURE:
        corpus = index['corpora'][name]
        require(corpus['files'] and corpus['inventory_complete'] is True)
        if name == 'graph' and corpus.get('status') == 'disabled':
            from lightyear_factory.copau_boundary import disabled_graph
            require(len(corpus['files']) == 1 and corpus['files'][0]['path'] == 'disabled.json')
            disabled_graph(corpus, load_json(stable_read(Path(corpus['root'])/'disabled.json', 4096)))
        else:
            require(corpus['records'] > 0)
        require(corpus['inventory_sha256'] == sha(encoded(corpus['files'])))
    for name in ('graph', 'prompts', 'contexts'):
        corpus = index['corpora'][name]
        require(re.fullmatch(r'[0-9a-f]{64}', corpus['run_binding_sha256'])
                and corpus['all_run_visible_content_included'] is True)
    main = index['corpora']['main']
    require(re.fullmatch(r'[0-9a-f]{40}', main['commit']) and
            re.fullmatch(r'[0-9a-f]{64}', main['tree_listing_sha256']))
    return index


def scan_corpora(index, values):
    validate_index(index)
    require(all(isinstance(v, str) and len(v) == 40 and not any(c.isspace() for c in v) for v in values))
    require(len(windows(values)) == len(values))
    require(values and len(values) == len(set(values)))
    report = dict(schema='copau-public-collision-report/2', corpus_index_sha256=sha(encoded(index)),
                  scanner_sha256=SCANNER_SHA, window_count=len(windows(values)), corpora={},
                  historical=index['historical'], unavailable=index['unavailable'], scans_clean=False)
    for name in sorted(CORPORA):
        corpus = index['corpora'][name]
        row = dict(file_count=0, record_count=0, window_count=len(windows(values)), match_count=0,
                   missing_count=sum(x['corpus'] == name for x in index['unavailable']), error_count=0)
        inventory = []
        try:
            records = (main_records(Path(corpus['root']), corpus) if name == 'main'
                       else directory_records(Path(corpus['root']), corpus['files']))
            for meta, raw in records:
                row['file_count'] += 1
                inventory.append([sha(raw), len(raw)])
                try:
                    for content in chain([meta['path'].encode()], views(raw, meta.get('archive', False))):
                        row['record_count'] += 1
                        matches, errors = scan_bytes(content, values)
                        row['match_count'] += matches; row['error_count'] += errors
                except Exception:
                    row['error_count'] += 1
        except Exception:
            row['error_count'] += 1
        row['corpus_sha256'] = sha(encoded(sorted(inventory)))
        report['corpora'][name] = row
    def clean(names):
        return all(report['corpora'][n]['file_count'] > 0 and report['corpora'][n]['record_count'] > 0 and
                   report['corpora'][n]['match_count'] == report['corpora'][n]['missing_count'] ==
                   report['corpora'][n]['error_count'] == 0 for n in names)
    report['exposure_clean'] = clean(EXPOSURE)
    report['collision_clean'] = clean(BASELINE)
    report['collision_count'] = sum(report['corpora'][n]['match_count'] for n in BASELINE)
    report['scans_clean'] = report['exposure_clean'] and report['collision_clean']
    return report


def verify_current_main(index):
    from tools.copau_public_corpus_index import github
    require(github('git/ref/heads/main')['object']['sha'] == index['corpora']['main']['commit'])


def prepare(store, root, seed, index, private_random_seed_confirmed=False, seed_commitment=False):
    store.absent('heldout-provenance.json', 'heldout-collision-report.json', 'expected-source.json',
                 'copau-expected-values.json', 'bundle-binding.json', 'heldout-bundle-attestation.json')
    require(sha((root / 'src/lightyear_factory/isolation_scan.py').read_bytes()) == SCANNER_SHA)
    validate_index(index); verify_current_main(index)
    # Prevent accidental acceptance of the public synthetic CI seed.
    require(private_random_seed_confirmed is True and isinstance(seed, bytes) and len(seed) == 32
            and seed not in (bytes(range(32)), bytes(reversed(range(32))), bytes(32)))
    created = datetime.now(timezone.utc)
    require(datetime.fromisoformat(index['captured_at']) < created)
    values, provenance = run_session(root, seed)
    require(len(provenance['selected_output_bindings']) == len(values) and all(
        b['selection'] == 'existing-judge-computed-record-digest' and
        b['private_identifier_characters'] == 15 and b['length'] == 40
        for b in provenance['selected_output_bindings']))
    report = scan_corpora(index, values)
    verify_current_main(index)
    # Production CLI supplies a privately persisted OS-random seed; tests use synthetic seeds.
    report['freshness'] = dict(os_generated_private_seed=True,
        private_input_dependency=True, generated_after_snapshot=True,
        public_reconstruction='requires unexposed high-entropy seed; computational claim')
    report['selection'] = dict(identifier_characters=15, selected_count=len(values),
                              messages_labels_padding_selected=False)
    report['qualified'] = report['scans_clean']
    provenance.update(created_at=created.isoformat(), seed_custody_file=seed_custody.SEED,
                      private_random_seed_confirmed=True,
                      values=values, corpus_index_sha256=sha(encoded(index)))
    store.write('heldout-provenance.json', encoded(provenance))
    # Historical disclosure can be large; retain its hash/count privately and
    # return the complete public-ID list publicly. It must not exhaust Store's
    # per-file limit and thereby become an accidental qualification blocker.
    stored_report = dict(report, historical=dict(status=HISTORICAL,
        disclosure_sha256=sha(encoded(report['historical'])),
        missing_count=len(report['historical']['missing']),
        metadata_error_count=report['historical']['metadata_error_count']))
    store.write('heldout-collision-report.json', encoded(stored_report))
    if not report['qualified']:
        return report, None
    source = dict(schema='copau-private-source/1', freeze_sha256=FREEZE_SHA, amendment_sha256=AMENDMENT_SHA,
                  source_reference='heldout-provenance.json',
                  coverage_description='Existing judge computed record digests derived from private transaction IDs; exact 40-character windows. Short-field leakage is outside coverage. Bound worker, graph, prompt/context exposure and current-main collision baseline; historical artifacts disclosure-only.',
                  approved_expected_state_source=True, values=values)
    raw = encoded(dict(schema='factory-private-expected-values/1', values=values))
    info = bundle_info(raw)
    store.write('expected-source.json', encoded(source))
    store.write('copau-expected-values.json', raw)
    store.write('bundle-binding.json', encoded(info))
    commitment = dict(optional=True, published=seed_commitment)
    if seed_commitment:commitment['sha256'] = sha(seed)
    store.write('heldout-bundle-attestation.json', encoded(dict(bundle=info, optional_seed_commitment=commitment)))
    return report, info



class PrivateArguments(argparse.ArgumentParser):
    def error(self, message):raise Refused()

def operate(args):
    root = Path(__file__).resolve().parents[1]
    require(Path.cwd().resolve() == root)
    require(git_bytes(root, 'rev-parse', 'HEAD').decode().strip() == args.reviewed_commit)
    require(not git_bytes(root, 'status', '--porcelain', '--untracked-files=all').strip())
    no_links(args.corpus_index.absolute())
    raw = stable_read(args.corpus_index.absolute(), 16 * 1024 * 1024)
    require(sha(raw) == args.reviewed_corpus_sha256)
    index = validate_index(load_json(raw))
    roots = [root, *args.exposed_root, *(Path(x['root']) for x in index['corpora'].values())]
    store = seed_custody.PrivateStore(args.private_dir, roots, args.expected_owner_sid)
    # Check every public input before creating any private seed.
    if not args.reuse:verify_current_main(index)
    seed, record, created = seed_custody.seed_for(store, sha(encoded(index)), reuse=args.reuse)
    args.seed_status[:] = [str(store.path(seed_custody.SEED)), created]
    complete = os.path.lexists(store.path('copau-expected-values.json'))
    if args.reuse or complete:
        info = seed_custody.replay(store, root, seed, run_session, bundle_info)
        report = dict(audit_replay_verified=True, fresh_surface_qualification=False)
    else:
        require(datetime.fromisoformat(index['captured_at']) < datetime.fromisoformat(record['created_at']))
        report, info = prepare(store, root, seed, index, True, args.seed_commitment)
    if args.seed_commitment:
        report['optional_seed_commitment'] = dict(optional=True, sha256=sha(seed))
    return report, info, str(store.path(seed_custody.SEED)), created

def main():
    status = []
    try:
        parser = PrivateArguments(description=__doc__)
        parser.add_argument('--reviewed-commit', required=True)
        parser.add_argument('--corpus-index', type=Path, required=True)
        parser.add_argument('--reviewed-corpus-sha256', required=True)
        parser.add_argument('--exposed-root', action='append', required=True)
        parser.add_argument('--private-dir', type=Path, default=seed_custody.DEFAULT if windows_host() else Path.home()/'private/copau-key-1')
        parser.add_argument('--expected-owner-sid')
        parser.add_argument('--reuse', action='store_true')
        parser.add_argument('--seed-commitment', action='store_true', help='Optional public SHA-256 seed commitment')
        args = parser.parse_args()
        args.seed_status = status
        with seed_custody.quiet_private():report, info, seed_path, created = operate(args)
        print(('Seed created: ' if created else 'Existing seed reused: ') + seed_path)
        print('Back up the seed file privately; never display or publish its contents.')
        print(json.dumps(report, sort_keys=True))
        if info is not None:print(json.dumps(info, sort_keys=True))
        return 0 if info is not None else 2
    except BaseException:
        if status:
            print(('Seed created: ' if status[1] else 'Existing seed reused: ') + status[0])
            print('Back up the seed file privately; never display or publish its contents.')
        print('REFUSED: preserve private files; inspect privately. No automatic retry.', file=sys.stderr)
        return 1

if __name__ == '__main__':sys.exit(main())
