"""Read-only P1 manifest-v2 loader. No freeze, network, or hand-output fallback.

ReviewedKey is an authenticated launcher input, not an authorization issued here.
published_key joins the approved release bytes to the reviewed manifest.
"""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import time

from lightyear_factory import public_evaluator_adapter as adapter


class Refused(ValueError):
    pass


def require(ok, code):
    if not ok:
        raise Refused(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(value, length=64):
    return type(value) is str and re.fullmatch('[a-f0-9]{%d}' % length, value) is not None


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode('utf-8')


def strict(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'answer-json')
            result[key] = value
        return result
    def invalid(_):
        raise Refused('answer-json')
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
                          parse_float=invalid, parse_constant=invalid)
    except (UnicodeError, ValueError, TypeError, RecursionError) as error:
        raise Refused('answer-json') from error


def shape(value, keys, code):
    require(type(value) is dict and set(value) == set(keys.split()), code)


QUALIFICATION = dict(
    qualification_commit='71a18164612ce574d889a39ceb335c5643721fc6',
    qualification_tree='7316662cb5cc52d5361ad1954c417b37e1e18fe5',
    qualification_sha256='934457b92d24dfc330e078420b14cb529fa6478c6799347b53857e74af98784b',
    evidence_manifest_sha256='a489a3e66e556946827b20f53395847b290e1f61eafda78bbd0eef4fd225964f',
    evidence_archive_sha256='e81cc0f0c6a77a57c00ea258e8a4f7b66c6da690f8bc081097da9b1b6d4129b3',
    binding_sha256='bb8b956a122c44ea70047848f56a2688f28071f2901df3b093a2af0e3ff758cb',
    public_suite_sha256=adapter.PUBLIC_SUITE)
CASE_IDS = tuple('PC-%02d' % n for n in range(1, 17))
FILE_BYTES = 8 * 1024 * 1024
TOTAL_BYTES = 256 * 1024 * 1024
MANIFEST_BYTES = 65536
INPUT_NAMES = {'ACCTFILE', 'DISCGRP', 'TCATBALF', 'XREFFILE'}
MANIFEST_KEYS = ('schema visibility wrapper_commit wrapper_tree wrapper_tool_sha256 '
                 'wrapper_workflow_sha256 approval_sha256 run_id run_attempt named_limits files '
                 + ' '.join(QUALIFICATION))


@dataclass(frozen=True)
class ReviewedKey:
    manifest_sha256: str
    wrapper_commit: str
    wrapper_tree: str
    approval_sha256: str
    run_id: int
    run_attempt: int

    def validate(self):
        require(digest(self.manifest_sha256) and digest(self.approval_sha256)
                and digest(self.wrapper_commit, 40) and digest(self.wrapper_tree, 40)
                and type(self.run_id) is int and self.run_id > 0
                and type(self.run_attempt) is int and self.run_attempt > 0,
                'answer-review-binding')


RELEASE_BINDING_SHA256 = '92aa133e6000e5dd9b34ddbbdbf822e4613002f47e0e42f5e76ac8b2a4bfbfae'


def published_key(binding_bytes, tag, archive_bytes):
    """Admit the staged public archive before L1 unpacks it in a fresh directory."""
    require(type(binding_bytes) is bytes and len(binding_bytes) <= MANIFEST_BYTES
            and sha(binding_bytes) == RELEASE_BINDING_SHA256, 'answer-release-binding')
    binding = strict(binding_bytes)
    require(tag == binding['release_tag'], 'answer-release-tag')
    require(type(archive_bytes) is bytes and len(archive_bytes) == binding['zip_bytes']
            and sha(archive_bytes) == binding['zip_sha256'], 'answer-release-archive')
    reviewed = ReviewedKey(**binding['reviewed_key'])
    reviewed.validate()
    return reviewed


def regular(info, directory=False):
    require(not getattr(info, 'st_file_attributes', 0) & 0x400,
            'answer-reparse')
    require((stat.S_ISDIR if directory else stat.S_ISREG)(info.st_mode), 'answer-path')


def root_path(root):
    root = Path(root)
    require(root.is_absolute() and '..' not in root.parts, 'answer-path')
    try:
        for component in (root, *root.parents):
            regular(component.lstat(), directory=True)
        require(root.resolve(strict=True) == root, 'answer-path')
    except OSError as error:
        raise Refused('answer-path') from error
    return root


def relative(name):
    require(type(name) is str and name and '\\' not in name and '\x00' not in name,
            'answer-path')
    p = PurePosixPath(name)
    require(not p.is_absolute() and str(p) == name
            and all(x not in ('.', '..', '') and ':' not in x for x in p.parts), 'answer-path')
    return p.parts


def read(root, name, limit=FILE_BYTES):
    """Stable bounded bytes; public files only, no lazy handles given to workers."""
    parts = relative(name)
    target = root.joinpath(*parts)
    fd = None
    try:
        for n in range(1, len(parts)):
            regular(root.joinpath(*parts[:n]).lstat(), directory=True)
        before = target.lstat()
        regular(before)
        require(before.st_size <= limit, 'answer-size')
        fd = os.open(target, os.O_RDONLY | getattr(os, 'O_BINARY', 0)
                     | getattr(os, 'O_NOFOLLOW', 0))
        opened = os.fstat(fd)
        regular(opened)
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)
        require(identity(before) == identity(opened), 'answer-changed')
        with os.fdopen(fd, 'rb') as stream:
            fd = None
            raw = stream.read(limit + 1)
            require(identity(os.fstat(stream.fileno())) == identity(opened), 'answer-changed')
        require(identity(target.lstat()) == identity(opened), 'answer-changed')
        require(len(raw) == before.st_size and len(raw) <= limit, 'answer-size')
        return raw
    except OSError as error:
        raise Refused('answer-read') from error
    finally:
        if fd is not None:
            os.close(fd)


def checked(root, descriptor):
    require(type(descriptor) is dict and set(descriptor) == {'path', 'sha256'}
            and digest(descriptor['sha256']), 'answer-input-descriptor')
    raw = read(root, descriptor['path'])
    require(sha(raw) == descriptor['sha256'], 'answer-input-hash')
    return raw


def inventory(root, wanted):
    """Only sixteen case directories, manifest, approval, and exact listed files."""
    try:
        entries = list(root.iterdir())
        require({p.name for p in entries} == set(CASE_IDS) | {'MANIFEST.json', 'APPROVAL.json'},
                'answer-inventory')
        found = set()
        for case_id in CASE_IDS:
            folder = root / case_id
            regular(folder.lstat(), directory=True)
            for p in folder.iterdir():
                regular(p.lstat())
                found.add(case_id + '/' + p.name)
        require(found == wanted, 'answer-inventory')
    except OSError as error:
        raise Refused('answer-inventory') from error


def approval_expected(review):
    row = dict(QUALIFICATION)
    del row['evidence_archive_sha256']
    row.update(schema='reference-two-source-public-freeze-approval/1', authority='Howard',
               authorize_public_freeze=True, scope='PC-01..PC-16 only; no hidden set',
               wrapper_commit=review.wrapper_commit, wrapper_tree=review.wrapper_tree)
    return row


def load(answer_root, suite_root, review):
    require(type(review) is ReviewedKey, 'answer-review-binding')
    review.validate()
    root, source = root_path(answer_root), root_path(suite_root)
    raw = read(root, 'MANIFEST.json', MANIFEST_BYTES)
    require(sha(raw) == review.manifest_sha256, 'answer-manifest-hash')
    manifest = strict(raw)
    shape(manifest, MANIFEST_KEYS, 'answer-manifest-shape')
    require(manifest['schema'] == 'reference-public-answer-key/2'
            and manifest['visibility'] == 'public', 'answer-manifest-kind')
    require(all(manifest[k] == v for k, v in QUALIFICATION.items()), 'answer-provenance')
    for k in ('wrapper_commit', 'wrapper_tree', 'approval_sha256', 'run_id', 'run_attempt'):
        require(type(manifest[k]) is type(getattr(review, k))
                and manifest[k] == getattr(review, k), 'answer-review-binding')
    require(digest(manifest['wrapper_tool_sha256']) and digest(manifest['wrapper_workflow_sha256'])
            and type(manifest['named_limits']) is list and len(manifest['named_limits']) == 3
            and all(type(s) is str and 0 < len(s) <= 512 for s in manifest['named_limits']),
            'answer-provenance')
    raw_approval = read(root, 'APPROVAL.json', MANIFEST_BYTES)
    require(sha(raw_approval) == review.approval_sha256, 'answer-approval-hash')
    approval = strict(raw_approval)
    require(approval == approval_expected(review)
            and approval.get('authorize_public_freeze') is True, 'answer-approval')
    suite_raw = read(source, 'SUITE.json', MANIFEST_BYTES)
    require(sha(suite_raw) == adapter.PUBLIC_SUITE, 'answer-suite-hash')
    suite = strict(suite_raw)
    require([c['id'] for c in suite['cases']] == list(CASE_IDS), 'answer-cases')
    wanted = {c['id'] + '/' + channel for c in suite['cases'] for channel in c['hand_outputs']}
    wanted |= {case_id + '/expected.json' for case_id in CASE_IDS}
    rows = manifest['files']
    require(type(rows) is list and len(rows) == len(wanted), 'answer-files')
    blobs = {}
    total = 0
    for row in rows:
        shape(row, 'path sha256 bytes', 'answer-descriptor')
        require(type(row['path']) is str and row['path'] in wanted and row['path'] not in blobs
                and digest(row['sha256']) and type(row['bytes']) is int
                and 0 <= row['bytes'] <= FILE_BYTES, 'answer-descriptor')
        total += row['bytes']
        require(total <= TOTAL_BYTES, 'answer-total-size')
        data = read(root, row['path'])
        require(len(data) == row['bytes'] and sha(data) == row['sha256'], 'answer-file-hash')
        blobs[row['path']] = data
    require(set(blobs) == wanted, 'answer-files')
    inventory(root, wanted)
    cases = []
    for case in suite['cases']:
        case_id = case['id']
        record = strict(blobs[case_id + '/expected.json'])
        shape(record, 'exit compare_output_files outputs', 'answer-case-shape')
        require(type(record['exit']) is int and record['exit'] == case['hand_exit']
                and type(record['compare_output_files']) is bool
                and record['compare_output_files'] == adapter.comparison_policy(case), 'answer-case-policy')
        require(type(record['outputs']) is dict
                and set(record['outputs']) == set(case['hand_outputs']), 'answer-channels')
        expected = {'exit': record['exit']}
        for channel, row in record['outputs'].items():
            shape(row, 'path sha256 bytes', 'answer-descriptor')
            path = case_id + '/' + channel
            data = blobs[path]
            require(row['path'] == path and type(row['bytes']) is int and row['bytes'] == len(data)
                    and row['sha256'] == sha(data) == case['hand_outputs'][channel]['sha256'],
                    'answer-reference-hand-join')
            expected[channel] = data  # Never reads the hand output file.
        require(set(case['inputs']) == INPUT_NAMES, 'answer-inputs')
        inputs = {dd: checked(source, row) for dd, row in case['inputs'].items()}
        total += sum(map(len, inputs.values()))
        require(total <= TOTAL_BYTES, 'answer-total-size')
        cases.append(dict(inputs=inputs, expected=expected,
                          compare_output_files=record['compare_output_files'],
                          timestamp=case['timestamp'], processing_date=case['processing_date']))
    # Preserve exactly the two-source provenance; all returned bytes already verified.
    provenance = {k: manifest[k] for k in MANIFEST_KEYS.split() if k != 'files'}
    provenance['manifest_sha256'] = review.manifest_sha256
    return cases, provenance


class FrozenPublicAdapter(adapter.PublicAdapter):
    """Same feedback/worker contract, expected bytes from the reviewed frozen root."""
    def __init__(self, worker, answer_root, suite_root, source_root, review, retain,
                 clock=time.monotonic):
        self.cases, self.answer_key = load(answer_root, suite_root, review)
        source_root = root_path(source_root)
        self.layouts = {}
        for dd, (name, expected) in adapter.LAYOUTS.items():
            path = 'spec/mainframe/copybooks/' + name
            require(sha(read(source_root, path)) == expected, 'answer-layout-hash')
            self.layouts[dd] = adapter.load_copybook(source_root / path)
            require(sha(read(source_root, path)) == expected, 'answer-layout-hash')
        self.worker, self.suite, self.clock = worker, adapter.PUBLIC_SUITE, clock

        def bound_retain(raw):
            require(retain(raw) == sha(raw), 'answer-receipt-readback')
            record = dict(schema='public-frozen-evaluation-receipt/1',
                          answer_key=self.answer_key, evaluation_sha256=sha(raw),
                          evaluation=strict(raw))
            bound = canonical(record)
            require(retain(bound) == sha(bound), 'answer-receipt-readback')
            # Both records are retained; the controller gets the bound outer hash.
            self._last_bound_receipt = sha(bound)
            return sha(raw)
        self.retain = bound_retain

    def evaluate_public(self, built, suite_sha256, deadline):
        self._last_bound_receipt = None
        result = super().evaluate_public(built, suite_sha256, deadline)
        require(digest(self._last_bound_receipt), 'answer-receipt-readback')
        result['receipt_sha256'] = self._last_bound_receipt
        return result
