"""Public schema refusals only; no Java execution or hidden evidence in discovery."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from tools import run_cobol_codec_vectors as vectors

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / 'spec/cobol-runtime/2026-11-15/PROFILE.json'
SUITE = ROOT / 'tests/fixtures/cobol-runtime/codecs-author.json'


class VectorSchemaTests(unittest.TestCase):
    def setUp(self):
        self.suite = vectors.load(SUITE)
        self.profile = hashlib.sha256(PROFILE.read_bytes()).hexdigest()

    def validate(self, suite=None, independent=False):
        return vectors.protocol(self.suite if suite is None else suite, self.profile, independent)

    def rehash(self, row):
        row['sha256'] = hashlib.sha256(vectors.canonical({k: v for k, v in row.items() if k != 'sha256'})).hexdigest()

    def test_author_protocol(self):
        rows = self.validate().decode().splitlines()
        self.assertEqual(37, len(rows))
        self.assertEqual([v["id"] for v in self.suite["vectors"]],
                         [line.split("\t")[12] for line in rows])

    def test_author_cannot_substitute_for_independent(self):
        with self.assertRaisesRegex(ValueError, '^vector-author$'):
            self.validate(independent=True)

    def test_hash_tampering(self):
        self.suite['vectors'][0]['expected'] = '0:0:false'
        with self.assertRaisesRegex(ValueError, '^vector-hash$'):
            self.validate()

    def test_extra_field(self):
        self.suite['vectors'][0]['unreviewed'] = 1
        with self.assertRaisesRegex(ValueError, '^vector-fields$'):
            self.validate()

    def test_duplicate_id(self):
        self.suite['vectors'].append(copy.deepcopy(self.suite['vectors'][0]))
        with self.assertRaisesRegex(ValueError, '^vector-id-duplicate$'):
            self.validate()

    def test_profile_join(self):
        self.suite['profile_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, '^vector-profile$'):
            self.validate()

    def test_boolean_scale_not_integer(self):
        row = self.suite['vectors'][0]
        row['scale'] = True
        self.rehash(row)
        with self.assertRaisesRegex(ValueError, '^vector-number$'):
            self.validate()

    def test_no_protocol_injection(self):
        row = self.suite['vectors'][0]
        row['pic'] = 'S9\tencode'
        self.rehash(row)
        with self.assertRaisesRegex(ValueError, '^vector-string$'):
            self.validate()

    def test_strict_input(self):
        # TemporaryDirectory works on Windows; no POSIX APIs or skips.
        for raw in (b'{"x":1,"x":2}', b'{"x":1.5}', b'{"x":NaN}', b'{"x":1e400}', b'\xff'):
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'synthetic.json'
                path.write_bytes(raw)
                with self.assertRaises((ValueError, UnicodeError)):
                    vectors.load(path)


if __name__ == '__main__':
    unittest.main()
