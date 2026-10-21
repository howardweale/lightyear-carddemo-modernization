"""Synthetic CI-only archive closure fixtures; no real downloads or proof runs."""
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import stat
import unittest
from zipfile import ZipFile, ZipInfo
from tools.carddemo_account_archive import ARCHIVES, HASH_GROUPS, verify_archives, verify_receipt_hashes


class Captured:
    def __init__(self): self.data = {}
    def add(self, path, raw):
        self.data[path] = raw
        return dict(path=path, sha256=sha256(raw).hexdigest())
    def read(self, ref):
        raw = self.data[ref['path']]
        if sha256(raw).hexdigest() != ref['sha256']: raise ValueError('unbound')
        return raw


def fixture(member_name='reference/result.json', mode=None):
    evidence = Captured(); rows = []; bindings = {}
    for i, name in enumerate(sorted(ARCHIVES)):
        stream = BytesIO(); raw = b'{"passed":true}'
        with ZipFile(stream, 'w') as archive:
            item = ZipInfo(member_name)
            if mode is not None: item.create_system = 3; item.external_attr = mode << 16
            archive.writestr(item, raw)
        data = stream.getvalue(); bindings[name] = evidence.add('archives/'+name, data)
        rows.append(dict(name=name, sha256=sha256(data).hexdigest(), size=len(data),
            original_artifact_id=i+1, members=[dict(path=member_name, size=len(raw), sha256=sha256(raw).hexdigest())]))
    return evidence, dict(schema='carddemo-retained-proof-archives/1', archives=rows), bindings


class AccountArchiveTests(unittest.TestCase):
    def test_complete_seven_archives_are_immutable(self):
        e, inventory, bindings = fixture(); captured = verify_archives(e, inventory, bindings)
        self.assertEqual(len(captured), 7)
        with self.assertRaises(TypeError): captured['extra'] = {}
        with self.assertRaises(TypeError): captured['carddemo-proof-api']['x'] = b'x'

    def test_missing_extra_duplicate_archive_and_id_refused(self):
        for kind in ('missing', 'extra', 'duplicate', 'id', 'boolean-id'):
            e, inventory, bindings = fixture()
            if kind == 'missing': inventory['archives'].pop()
            elif kind == 'extra': bindings['unknown.zip'] = next(iter(bindings.values()))
            elif kind == 'duplicate': inventory['archives'][1]['name'] = inventory['archives'][0]['name']
            elif kind == 'id': inventory['archives'][1]['original_artifact_id'] = 1
            else: inventory['archives'][0]['original_artifact_id'] = True
            with self.subTest(kind=kind), self.assertRaises(ValueError): verify_archives(e, inventory, bindings)

    def test_archive_and_member_hash_size_tampering_refused(self):
        for level in ('archive', 'member'):
            for field, value in (('sha256', '0'*64), ('size', 1), ('size', True)):
                e, inventory, bindings = fixture(); row = inventory['archives'][0]
                if level == 'member': row = row['members'][0]
                row[field] = value
                with self.subTest(level=level, field=field), self.assertRaises(ValueError): verify_archives(e, inventory, bindings)

    def test_missing_undeclared_and_alias_member_refused(self):
        for kind in ('missing', 'undeclared', 'alias'):
            e, inventory, bindings = fixture(); members = inventory['archives'][0]['members']
            if kind == 'missing': members.append(dict(path='missing', sha256='0'*64, size=0))
            elif kind == 'undeclared': members[0]['path'] = 'different'
            else: members.append({**members[0], 'path':members[0]['path'].upper()})
            with self.subTest(kind=kind), self.assertRaises(ValueError): verify_archives(e, inventory, bindings)

    def test_traversal_and_link_members_refused(self):
        for path in ('../outside', '/absolute', 'A:stream', 'trailing./file'):
            e, inventory, bindings = fixture(path)
            with self.subTest(path=path), self.assertRaises(ValueError): verify_archives(e, inventory, bindings)
        for mode in (stat.S_IFLNK | 0o777, stat.S_IFIFO | 0o600):
            e, inventory, bindings = fixture(mode=mode)
            with self.subTest(mode=mode), self.assertRaises(ValueError): verify_archives(e, inventory, bindings)

    def test_every_receipt_source_and_artifact_is_checked(self):
        e, inventory, bindings = fixture(); archives = verify_archives(e, inventory, bindings)
        sources = {}; hashes = {}
        for group in HASH_GROUPS:
            path = 'source/'+group; sources[path] = e.add('captured/'+path, group.encode())
            hashes[group] = [dict(path=path, sha256=sources[path]['sha256'])]
        raw = archives['carddemo-proof-api']['reference/result.json']
        artifact = dict(path='work/carddemo-proof-artifacts/carddemo-proof-api/reference/result.json', sha256=sha256(raw).hexdigest())
        receipt = dict(hashes=hashes, artifacts=[artifact])
        self.assertEqual(verify_receipt_hashes(receipt, archives, e, sources), dict(source_and_mapping_hashes=6, artifact_hashes=1))
        for kind in ('source', 'artifact', 'extra-source', 'alias', 'generated-disagreement'):
            r = deepcopy(receipt); s = deepcopy(sources); a = {k:dict(v) for k,v in archives.items()}
            if kind == 'source': r['hashes']['services'][0]['sha256'] = '0'*64
            elif kind == 'artifact': r['artifacts'][0]['sha256'] = '0'*64
            elif kind == 'extra-source': s['unclaimed'] = next(iter(s.values()))
            elif kind == 'alias': r['artifacts'].append(deepcopy(artifact))
            else:
                r['hashes']['mappings'] = [dict(path='work/reference/result.json', sha256=sha256(raw).hexdigest())]
                del s['source/mappings']; a['carddemo-proof-browser']['reference/result.json'] = b'changed'
            with self.subTest(kind=kind), self.assertRaises(ValueError): verify_receipt_hashes(r, a, e, s)
