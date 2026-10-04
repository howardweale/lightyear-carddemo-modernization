"""Classfile parser tests; no native provenance or qualification claims."""
import hashlib
import struct
import unittest
from tools.ms94_b06_classfile import inspect_class
from tools.ms94_b06_admission import EvidenceFailure


def u2(value): return struct.pack('>H', value)
def u4(value): return struct.pack('>I', value)
def utf8(value):
    raw = value.encode('ascii')
    return b'\x01' + u2(len(raw)) + raw


def fixture():
    pool = utf8('test/Fixture') + b'\x07' + u2(1) + utf8('f') + utf8('()V') + utf8('Code')
    code = u2(0) + u2(0) + u4(1) + b'\xb1' + u2(0) + u2(0)
    method = u2(0x0009) + u2(3) + u2(4) + u2(1) + u2(5) + u4(len(code)) + code
    raw = u4(0xCAFEBABE) + u2(0) + u2(65) + u2(6) + pool
    raw += u2(0x0021) + u2(2) + u2(0) + u2(0) + u2(0) + u2(1) + method + u2(0)
    return raw, pool


class ClassfileTests(unittest.TestCase):
    def test_method_and_pool_are_separately_bound(self):
        raw, pool = fixture(); result = inspect_class(raw)
        self.assertEqual(result['class'], 'test.Fixture')
        self.assertEqual(result['constant_pool_sha256'], hashlib.sha256(pool).hexdigest())
        self.assertEqual(result['methods'], {'f()V': hashlib.sha256(b'\xb1').hexdigest()})
        self.assertEqual(result['class_sha256'], hashlib.sha256(raw).hexdigest())

    def test_all_truncations_and_trailing_bytes_are_rejected(self):
        raw, _ = fixture()
        for size in range(len(raw)):
            with self.subTest(size=size), self.assertRaises(EvidenceFailure): inspect_class(raw[:size])
        with self.assertRaises(EvidenceFailure): inspect_class(raw + b'ignored')

    def test_unknown_pool_tag_is_not_skipped(self):
        raw, _ = fixture()
        with self.assertRaises(EvidenceFailure): inspect_class(raw[:10] + b'\xff' + raw[11:])


if __name__ == '__main__': unittest.main()
