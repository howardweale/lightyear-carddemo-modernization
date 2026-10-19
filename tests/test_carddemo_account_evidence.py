"""CI-only fixtures for account evidence byte and path binding."""
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import stat
import unittest
from unittest.mock import patch
from tools.carddemo_account_evidence import BoundEvidence, canonical_path, json_document, json_rows


class AccountEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = {'docs/receipt.json': b'{"unsigned":true}', 'docs/mutations.xml': b'<mutations/>'}
        for name, raw in self.data.items():
            path = self.root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
        self.manifest = {name: sha256(raw).hexdigest() for name, raw in self.data.items()}
        self.ref = self.write_manifest()

    def write_manifest(self, raw=None):
        raw = json.dumps(self.manifest).encode() if raw is None else raw
        (self.root / 'manifest.json').write_bytes(raw)
        return dict(path='manifest.json', sha256=sha256(raw).hexdigest())

    def bound(self, path='docs/receipt.json'):
        return dict(path=path, sha256=self.manifest[path])

    def test_complete_input_snapshot_and_fresh_documents(self):
        bundle = BoundEvidence(self.root, self.ref)
        self.assertEqual(bundle.inputs, ('manifest.json', 'docs/mutations.xml', 'docs/receipt.json'))
        value = bundle.document(self.bound()); value['unsigned'] = False
        self.assertEqual(bundle.document(self.bound()), {'unsigned': True})
        (self.root / 'docs/receipt.json').write_bytes(b'changed after capture')
        self.assertEqual(bundle.read(self.bound()), self.data['docs/receipt.json'])
        with self.assertRaisesRegex(ValueError, 'member-hash'):
            BoundEvidence(self.root, self.ref)

    def test_nested_duplicates_nonfinite_and_nonobjects_refused(self):
        for raw in (b'{"a":1,"a":2}', b'{"a":{"b":1,"b":2}}', b'{"n":NaN}',
                    b'{"n":Infinity}', b'{"n":-Infinity}', b'{"n":1e999}', b'{"n":-1e999}', b'[]', b'null', b'false'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                json_document(raw)
        self.assertEqual(json_document(b'{"a":{"b":1}}'), {'a': {'b': 1}})

    def test_manifest_shape_and_digest_refusals(self):
        for raw in (b'{}', b'[]', b'{"docs/receipt.json":null}', b'{"docs/receipt.json":"bad"}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                BoundEvidence(self.root, self.write_manifest(raw))
        self.ref = self.write_manifest()
        for ref in ({'path': 'manifest.json', 'sha256': '0'*64},
                    {'path': 'manifest.json', 'sha256': self.ref['sha256'].upper()},
                    {**self.ref, 'extra': True}):
            with self.subTest(ref=ref), self.assertRaises(ValueError):
                BoundEvidence(self.root, ref)

    def test_portable_path_refusals(self):
        for path in ('', '/absolute', '../outside', 'docs/../outside', 'docs//receipt.json',
                     'docs/./receipt.json', 'C:/secret', r'docs\receipt.json', 'docs/x:stream',
                     'docs/NUL.json', 'docs/COM1', 'docs/LPT9.txt', 'docs/a.', 'docs/a ', 'docs/\x00', 'docs/a?b', 'docs/a*b', 'docs/a|b', 'docs/\x01'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                canonical_path(path)
        self.assertEqual(canonical_path('docs/COPAUS0C/source.json'), 'docs/COPAUS0C/source.json')

    def test_every_member_verified_even_when_not_requested(self):
        (self.root / 'docs/mutations.xml').write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, 'member-hash'):
            BoundEvidence(self.root, self.ref)
        (self.root / 'docs/mutations.xml').unlink()
        with self.assertRaisesRegex(ValueError, 'unreadable'):
            BoundEvidence(self.root, self.ref)

    def test_undeclared_or_altered_reference_refused(self):
        bundle = BoundEvidence(self.root, self.ref)
        for ref in (dict(path='elsewhere.json', sha256='0'*64),
                    dict(path='docs/receipt.json', sha256='0'*64),
                    dict(path='DOCS/receipt.json', sha256=self.manifest['docs/receipt.json'])):
            with self.subTest(ref=ref), self.assertRaisesRegex(ValueError, 'unbound-reference'):
                bundle.read(ref)

    def test_manifest_case_alias_and_self_reference_refused(self):
        for extra in ('DOCS/receipt.json', 'manifest.json', 'MANIFEST.JSON'):
            self.manifest[extra] = '0'*64
            with self.subTest(extra=extra), self.assertRaisesRegex(ValueError, 'path-alias'):
                BoundEvidence(self.root, self.write_manifest())
            del self.manifest[extra]

    def test_links_reparse_points_and_nonregular_members_refused(self):
        original = Path.lstat
        for mode, attributes, fragment in ((stat.S_IFLNK, 0, 'link'),
                                          (stat.S_IFREG, 0x400, 'link'),
                                          (stat.S_IFDIR, 0, 'file-type')):
            def inspection(path, *args, **kwargs):
                if path == self.root / 'docs/receipt.json':
                    return SimpleNamespace(st_mode=mode, st_file_attributes=attributes)
                return original(path, *args, **kwargs)
            with self.subTest(mode=mode, attributes=attributes), patch.object(Path, 'lstat', inspection):
                with self.assertRaisesRegex(ValueError, fragment):
                    BoundEvidence(self.root, self.ref)


    def test_rows_preserve_nested_evidence_and_order(self):
        raw = b'[{"case":"reader","nested":{"text":"001","number":1}},{"case":"writer"}]'
        self.assertEqual(json_rows(raw), [{'case': 'reader', 'nested': {'text': '001', 'number': 1}}, {'case': 'writer'}])
        self.assertEqual(json_rows(b'[]'), [])  # Scenario validation enforces its own denominator.

    def test_rows_refuse_nested_duplicates_and_nonfinite_values(self):
        for raw in (b'[{"case":"a","case":"b"}]', b'[{"nested":{"n":1,"n":2}}]',
                    b'[{"n":NaN}]', b'[{"n":Infinity}]', b'[{"n":-Infinity}]',
                    b'[{"n":1e999}]', b'[{"n":-1e999}]'):
            with self.subTest(raw=raw), self.assertRaises(ValueError): json_rows(raw)

    def test_rows_refuse_nonrow_roots_and_members(self):
        for raw in (b'{}', b'null', b'false', b'1', b'"text"', b'[null]', b'[1]', b'[[]]', b'[{},false]'):
            with self.subTest(raw=raw), self.assertRaises(ValueError): json_rows(raw)
        with self.assertRaises(ValueError): json_document(b'[{}]')



if __name__ == '__main__':
    unittest.main()
