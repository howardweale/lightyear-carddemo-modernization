"""Independent byte fixtures for IBM binary, overlays and variable records."""
import unittest
import json
from pathlib import Path
from lightyear_mainframe.records import DecodeError, LayoutError, decode_record, decode_fixed, decode_rdw
from tests.test_mainframe_records import layout


class ExtendedRecordTests(unittest.TestCase):
    def test_published_bank_vectors(self):
        from lightyear_mainframe.records import load_copybook
        root=Path(__file__).resolve().parents[1]/'spec/mainframe'
        fixture=json.loads((root/'extended-golden.json').read_text())
        l=load_copybook(root/fixture['copybook'])
        options={k:fixture[k] for k in ('codec','binary_byteorder','binary_truncation','redefines')}
        raw=bytes.fromhex(''.join(r['rdw_hex']+r['payload_hex'] for r in fixture['records']))
        records=decode_rdw(l,raw,**options)
        self.assertEqual((13,22),(l.minimum_length,l.record_length))
        for r,expected in zip(records,fixture['records']):
            self.assertEqual(expected['payload_hex'],r['raw_hex'])
            self.assertEqual(expected['values'],[f['value'] for f in r['fields']])

    def test_binary_sizes_sign_endian_and_exact_scale(self):
        l=layout('05 A PIC S9(4) COMP.', '05 B PIC 9(9) BINARY.', '05 C PIC S9(18) COMP-5.')
        self.assertEqual([2,4,8],[f.length for f in l.fields])
        raw=bytes.fromhex('ff85ffffffff8000000000000000')
        result=decode_record(l,raw,binary_byteorder='big',binary_truncation='bin')
        self.assertEqual(['-123','4294967295','-9223372036854775808'],[f['value'] for f in result['fields']])
        scaled=layout('05 N PIC S99V99 COMP-5.')
        self.assertEqual('-327.68',decode_record(scaled,bytes.fromhex('0080'),binary_byteorder='little')['fields'][0]['value'])
        with self.assertRaises(DecodeError):decode_record(l,raw,binary_byteorder='big',binary_truncation='std')
        with self.assertRaises(DecodeError):decode_record(l,raw)
        with self.assertRaises(DecodeError):decode_record(l,raw,binary_byteorder='big')

    def test_overlay_is_one_storage_area_and_requires_selection(self):
        l=layout('05 RAW PIC X(4).','05 NUMBER REDEFINES RAW PIC S9(9) COMP.',
                 '05 PARTS REDEFINES NUMBER.','10 A PIC X(2).','10 B PIC X(3).','05 TAIL PIC X.')
        self.assertEqual(6,l.record_length)
        raw=bytes.fromhex('0000007b')+b'\x40\xc1'
        with self.assertRaises(DecodeError):decode_record(l,raw)
        result=decode_record(l,raw,redefines={'REC.RAW':'NUMBER'},binary_byteorder='big',binary_truncation='std')
        self.assertEqual(['123','A'],[f['value'] for f in result['fields']])
        self.assertEqual(5,result['fields'][-1]['offset'])
        self.assertEqual(raw.hex(),result['raw_hex'])
        with self.assertRaises(DecodeError):decode_record(l,raw,redefines={'REC.RAW':'NOPE'})
        with self.assertRaises(DecodeError):decode_record(l,raw,redefines={'REC.RAW':'RAW','typo':'RAW'})
        with self.assertRaises(LayoutError):layout('05 A PIC X.','05 B PIC X.','05 C REDEFINES A PIC X.')

    def test_fixed_occurs_can_choose_different_overlays(self):
        l=layout('05 ITEMS OCCURS 2.','10 TEXT PIC X(2).','10 NUM REDEFINES TEXT PIC 9(2).')
        r=decode_record(l,'AB12'.encode('cp037'),redefines={'REC.ITEMS[1].TEXT':'TEXT','REC.ITEMS[2].TEXT':'NUM'})
        self.assertEqual(['AB','12'],[f['value'] for f in r['fields']])

    def test_odo_zero_middle_max_and_sliding_tail(self):
        l=layout('05 COUNT PIC 9.','05 ITEMS OCCURS 0 TO 3 DEPENDING ON COUNT.',
                 '10 AMOUNT PIC S9(3) COMP-3.','05 TAIL PIC X.')
        self.assertEqual((2,8),(l.minimum_length,l.record_length))
        for n in (0,1,3):
            raw=str(n).encode('cp037')+bytes.fromhex('123c')*n+b'\xc1'
            r=decode_record(l,raw)
            self.assertEqual(1+2*n,r['fields'][-1]['offset'])
            self.assertEqual('A',r['fields'][-1]['value'])
            self.assertEqual(n+2,len(r['fields']))
        for raw in [b'\xf4'+b'\0'*8+b'\xc1', b'\xf1\x12\x3c',b'\xf0\xc1\x40']:
            with self.assertRaises(DecodeError):decode_record(l,raw)
        with self.assertRaises(DecodeError):decode_fixed(l,b'')

    def test_variable_binary_controller_and_rdw_boundaries(self):
        l=layout('05 N PIC 9(4) COMP.','05 DATA PIC X OCCURS 1 TO 3 DEPENDING ON N.')
        raw=bytes.fromhex('000800000002c1c2000900000003c3c4c5')
        r=decode_rdw(l,raw,binary_byteorder='big',binary_truncation='std')
        self.assertEqual(2,len(r))
        self.assertEqual(['2','A','B'],[f['value'] for f in r[0]['fields']])
        for bad in [raw[:-1],bytes.fromhex('00030100'),bytes.fromhex('000600000000'),b'\0',bytes.fromhex('000700010002c1c2')]:
            with self.assertRaises(DecodeError):decode_rdw(l,bad,binary_byteorder='big',binary_truncation='std')

    def test_ambiguous_or_unsafe_variable_layouts_fail(self):
        cases=[('05 N PIC 9V9.','05 T PIC X OCCURS 1 TO 3 DEPENDING ON N.'),
               ('05 T PIC X OCCURS 1 TO 3 DEPENDING ON N.','05 N PIC 9.'),
               ('05 N PIC 9.','05 T PIC X OCCURS 3 TO 1 DEPENDING ON N.'),
               ('05 N PIC 9.','05 G OCCURS 2.','10 T PIC X OCCURS 1 TO 3 DEPENDING ON N.'),
               ('05 N PIC 9.','05 A PIC X.','05 B REDEFINES A.','10 T PIC X OCCURS 1 TO 3 DEPENDING ON N.'),
               ('05 N PIC 9.','05 A PIC X OCCURS 1 TO 3 DEPENDING ON N.','05 B PIC X OCCURS 1 TO 3 DEPENDING ON N.')]
        for declarations in cases:
            with self.subTest(declarations=declarations),self.assertRaises(LayoutError):layout(*declarations)
