from decimal import getcontext
import json
from pathlib import Path
import unittest

from lightyear_mainframe.records import (DecodeError, LayoutError, compile_copybook,
    decode_fixed, decode_record, decode_spool, load_copybook, spool_envelope)

ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT/'spec/mainframe'


def layout(*lines):
    return compile_copybook('\n'.join('       '+s for s in ('01 REC.',)+lines)+'\n')


def field_value(schema, raw, **options):
    return decode_record(schema, raw, **options)['fields'][0]


class LayoutTests(unittest.TestCase):
    def test_carddemo_offsets_from_public_copybook(self):
        acct = load_copybook(KIT/'copybooks/CVACT01Y.cpy')
        trans = load_copybook(KIT/'copybooks/CVTRA05Y.cpy')
        self.assertEqual(300, acct.record_length)
        self.assertEqual(350, trans.record_length)
        amount = next(f for f in acct.fields if f.path.endswith('.ACCT-CURR-BAL'))
        self.assertEqual((12, 12, 2), (amount.offset, amount.length, amount.scale))
        self.assertEqual(178, acct.fields[-1].length)
        self.assertTrue(acct.fields[-1].filler)

    def test_nested_fixed_occurs_and_filler_offsets(self):
        l = layout('05 ROWS OCCURS 2 TIMES.', '10 NAME PIC X(2).', '10 AMT PIC S9(3)V99 COMP-3.', '05 FILLER PIC X.', '05 FILLER PIC X.')
        self.assertEqual(12, l.record_length)
        self.assertEqual([0, 2, 5, 7, 10, 11], [f.offset for f in l.fields])
        self.assertEqual(len(l.fields), len({f.path for f in l.fields}))
        self.assertIn('ROWS[2]', l.fields[2].path)

    def test_refuses_layout_guesses(self):
        declarations = ['05 A REDEFINES B PIC X.', '05 A PIC 9(4) COMP.',
            '05 A PIC 9(4) BINARY.', '05 A PIC X OCCURS 1 TO 10 DEPENDING ON N.',
            '05 A PIC 9(2) SYNC.', '05 A PIC ZZ9.99.', '05 A PIC 9(2) SIGN LEADING SEPARATE.',
            '05 A PIC X COMP-3.', '05 A PIC X(0).', '05 A PIC X(99999).', '05 A PIC S9(2) COMP-3 SIGN LEADING.',
            '05 A POINTER.', '05 A PIC X.\n       01 SECOND PIC X.', '05 A PIC X.\n       10 B PIC X.']
        for declaration in declarations:
            with self.subTest(declaration=declaration), self.assertRaises(LayoutError): layout(declaration)

    def test_continued_pic_and_value_do_not_shift_offsets(self):
        l = layout('05 AMT PIC S9(5)V99', 'USAGE IS PACKED-DECIMAL VALUE ZERO.', '05 TEXT PIC X(03) VALUE SPACES.')
        self.assertEqual(7, l.record_length)


class NumericTests(unittest.TestCase):
    def test_packed_independently_specified_positive_negative_and_zero(self):
        l = layout('05 AMT PIC S9(3)V99 COMP-3.')
        for raw, expected in [('12345c', '123.45'), ('12345d', '-123.45'), ('00000d', '-0.00'), ('99999c','999.99')]:
            with self.subTest(raw=raw): self.assertEqual(expected, field_value(l, bytes.fromhex(raw))['value'])
        self.assertTrue(field_value(l, bytes.fromhex('00000d'))['negative_zero'])
        self.assertEqual('01234c', field_value(layout('05 N PIC S9(2)V99 COMP-3.'),bytes.fromhex('01234c'))['raw_hex'])

    def test_packed_invalid_digits_sign_and_padding_fail(self):
        l = layout('05 N PIC S9(2)V99 COMP-3.')
        for raw in ['11234c', '0123ac', '012345', '01234b']:
            with self.subTest(raw=raw), self.assertRaises(DecodeError): field_value(l,bytes.fromhex(raw))
        self.assertEqual('-12.34',field_value(l,bytes.fromhex('01234b'),sign_policy='ibm-valid')['value'])
        unsigned=layout('05 N PIC 9(3) COMP-3.')
        self.assertEqual('123',field_value(unsigned,bytes.fromhex('123f'))['value'])
        with self.assertRaises(DecodeError):field_value(unsigned,bytes.fromhex('123d'))

    def test_ebcdic_zoned_and_separate_signs(self):
        l = layout('05 AMT PIC S9(3)V99.')
        self.assertEqual('-123.45',field_value(l,bytes.fromhex('f1f2f3f4d5'))['value'])
        self.assertEqual('123.45',field_value(l,bytes.fromhex('f1f2f3f4c5'))['value'])
        self.assertEqual('12345',field_value(l,bytes.fromhex('f1f2f3f4f5'))['digits'])
        leading = layout('05 AMT PIC S9(3)V99 SIGN LEADING.')
        self.assertEqual('-123.45',field_value(leading,bytes.fromhex('d1f2f3f4f5'))['value'])
        separate = layout('05 AMT PIC S9(3)V99 SIGN LEADING SEPARATE CHARACTER.')
        self.assertEqual('-123.45',field_value(separate,'-12345'.encode('cp037'))['value'])
        for raw in ['f1f2f3f4af','c1f2f3f4f5','3132333435']:
            with self.subTest(raw=raw), self.assertRaises(DecodeError):field_value(l,bytes.fromhex(raw))

    def test_large_decimal_is_exact_despite_small_context(self):
        l = layout('05 N PIC 9(30)V99.')
        old=getcontext().prec
        try:
            getcontext().prec=6
            self.assertEqual('123456789012345678901234567890.12',field_value(l,'12345678901234567890123456789012'.encode('cp037'))['value'])
        finally:getcontext().prec=old

    def test_padding_filler_and_raw_bytes_are_preserved(self):
        l=layout('05 TXT PIC X(3).','05 FILLER PIC X(2).')
        raw='A    '.encode('cp037');decoded=decode_record(l,raw)
        self.assertEqual('A  ',decoded['fields'][0]['value'])
        self.assertEqual('  ',decoded['fields'][1]['value'])
        self.assertEqual(raw.hex(),decoded['raw_hex'])
        self.assertTrue(decoded['fields'][1]['filler'])
        for codec in ['utf-8','ascii','guess']:
            with self.assertRaises(DecodeError):decode_record(l,raw,codec=codec)

    def test_codepage_is_explicit_and_material(self):
        l=layout('05 TXT PIC X.')
        self.assertNotEqual(field_value(l,b'\x9f',codec='cp037')['value'],field_value(l,b'\x9f',codec='cp1140')['value'])

    def test_framing_refuses_short_long_or_partial_records(self):
        l=layout('05 N PIC 9(2).')
        for raw in [b'\xf0',b'\xf0'*3]:
            with self.assertRaises(DecodeError):decode_record(l,raw)
            with self.assertRaises(DecodeError):decode_fixed(l,raw)
        self.assertEqual(2,len(decode_fixed(l,b'\xf0'*4)))
        self.assertEqual([],decode_fixed(l,b''))

    def test_spool_transport_checks_identity_count_and_hash(self):
        l=layout('05 N PIC 9(2).');payload=spool_envelope(b'\xf1\xf2',l)
        self.assertEqual('12',decode_spool(payload,l)[0]['fields'][0]['value'])
        for changes in [dict(lrecl=3),dict(record_count=2),dict(record_count=True),dict(hex='f1'),dict(hex='f1 f2'),dict(sha256='0'*64),dict(copybook_sha256='0'*64),dict(format='text')]:
            data={**json.loads(payload),**changes}
            with self.subTest(changes=changes),self.assertRaises(DecodeError):decode_spool(json.dumps(data).encode(),l)
        for raw in [b'12\n',b'\xf1\xf2',b'{"format":1,"format":2}']:
            with self.assertRaises(DecodeError):decode_spool(raw,l)
