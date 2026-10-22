"""Read exact public CI evidence from a digest-bound Release; never extract it."""
from functools import lru_cache
from hashlib import sha256
import io
import json
from pathlib import PurePosixPath
import stat
from urllib.parse import urlsplit
from urllib.request import urlopen
import zipfile

SCHEMA = 'intcalc-retained-publication/1'
REPOSITORY = 'howardweale/lightyear-carddemo-modernization'
MAX_ARCHIVE = 2 * 1024 * 1024
MAX_FILES = 64
MAX_TOTAL = 16 * 1024 * 1024


def need(value, reason):
    if not value:
        raise ValueError('retained-intcalc-' + reason)


def valid_path(name):
    path = PurePosixPath(name)
    return bool(name) and not path.is_absolute() and '..' not in path.parts and chr(92) not in name and ':' not in name


@lru_cache(maxsize=4)
def download(url, size, digest):
    # Public download only: no token, auth header, credential helper or writes.
    with urlopen(url, timeout=60) as response:
        raw = response.read(size + 1)
    need(len(raw) == size and sha256(raw).hexdigest() == digest, 'archive-hash')
    return raw


def read(root, publication, *, fetch=download):
    need(publication['schema'] == SCHEMA and publication['repository'] == REPOSITORY, 'schema')
    source = publication['source']
    need(len(source['head']) == 40 and source['run_id'] > 0 and source['run_attempt'] > 0
         and source['artifact_id'] > 0 and source['artifact_name'] == 'intcalc-current-verdict', 'source')
    archive = publication['archive']
    url = urlsplit(archive['url'])
    prefix = '/' + REPOSITORY + '/releases/download/intcalc-verdict-run' + str(source['run_id']) + '-attempt' + str(source['run_attempt']) + '/'
    need(url.scheme == 'https' and url.netloc == 'github.com' and not url.query and not url.fragment
         and url.path == prefix + 'intcalc-current-verdict.zip', 'url')
    for key, filename in (('verdict_url', 'intcalc-releasability-' + publication['prepared_on'] + '.md'),
                          ('packet_url', 'howard-decision-packet-' + publication['prepared_on'] + '-handoff-refresh.md')):
        need(publication[key] == 'https://github.com' + prefix + filename, 'document-url')
    need(0 < archive['bytes'] <= MAX_ARCHIVE and len(archive['sha256']) == 64, 'archive-size')
    rows = publication['files']
    need(0 < len(rows) <= MAX_FILES and all(0 <= row['bytes'] <= MAX_TOTAL for row in rows)
         and sum(row['bytes'] for row in rows) <= MAX_TOTAL, 'inventory-size')
    expected = {row['path']: row for row in rows}
    need(len(expected) == len(rows) and all(valid_path(n) for n in expected), 'inventory-path')
    raw = fetch(archive['url'], archive['bytes'], archive['sha256'])
    need(len(raw) == archive['bytes'] and sha256(raw).hexdigest() == archive['sha256'], 'archive-hash')
    files = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as bundle:
        members = bundle.infolist()
        need(len(members) == len(expected) and {i.filename for i in members} == set(expected), 'inventory')
        for member in members:
            need(not member.is_dir() and valid_path(member.filename) and not member.flag_bits & 1
                 and stat.S_IFMT(member.external_attr >> 16) in (0, stat.S_IFREG), 'member-type')
            row = expected[member.filename]
            need(member.file_size == row['bytes'] and member.file_size <= MAX_TOTAL, 'member-size')
            value = bundle.read(member)
            need(sha256(value).hexdigest() == row['sha256'], 'member-hash')
            files[member.filename] = value
    report = json.loads(files[publication['report']])
    index = json.loads(files[publication['index']])
    need(report['schema'] == 'intcalc-releasability/3' and report['prepared_on'] == publication['prepared_on'], 'report')
    need(report['head'] == index['head'] == publication['measurement']['head']
         and report['run_id'] == index['run_id'] == publication['measurement']['run_id'], 'measurement')
    need(report['release_authorized'] is False and publication['release_authorized'] is False, 'authority')
    need(report['evidence_index']['path'] == publication['index']
         and report['evidence_index']['sha256'] == sha256(files[publication['index']]).hexdigest(), 'index-hash')
    original = publication['original_manifest']
    need(valid_path(original['path']) and original['path'] == 'docs/factory/evidence-retention-2026-10-18-intcalc.json', 'original-path')
    files[original['path']] = (root / original['path']).read_bytes()
    need(sha256(files[original['path']]).hexdigest() == original['sha256']
         and index['external_archive']['manifest_sha256'] == original['sha256'], 'original-hash')
    for item in index['sources'] + index.get('crosscheck_sources', []):
        need(item['head'] == report['head'] and item['run_id'] == report['run_id'], 'index-source')
        for name, digest in item['files'].items():
            need(name in files and sha256(files[name]).hexdigest() == digest, 'source-file-hash')
    return dict(release=report, index=index, files=files, local_inputs=[original['path']], publication=publication)
