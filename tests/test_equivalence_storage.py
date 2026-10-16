import unittest
from lightyear_mainframe.source import tokenize
from lightyear_mainframe.equivalence_storage import compile_area, Memory, StorageError, storage_ir
from lightyear_mainframe.equivalence_automation import bound


def area(lines):
    return compile_area('WS', [tokenize('       ' + line) for line in lines])


class StorageTests(unittest.TestCase):
    def test_level_01_overlay_is_same_bytes(self):
        a = area(['01 NUMBER PIC 9(4) BINARY.', '01 RAW REDEFINES NUMBER.',
                  '05 LEFT-BYTE PIC X.', '05 RIGHT-BYTE PIC X.'])
        m = Memory([a]); m.write('WS:NUMBER', b'\x12\x34')
        self.assertEqual(b'\x12', m.read('WS:RAW.LEFT-BYTE'))
        m.write('WS:RAW.RIGHT-BYTE', b'\xff')
        self.assertEqual(b'\x12\xff', m.read('WS:NUMBER'))
        self.assertTrue(m.overlaps('WS:RAW', 'WS:NUMBER'))

    def test_level_01_occurs_views_have_distinct_offsets(self):
        a = area(['01 TABLE-ROW OCCURS 3 TIMES.', '05 ITEM PIC X(2).'])
        m = Memory([a]); m.write('WS:TABLE-ROW[2].ITEM', b'ab')
        self.assertEqual(b'ab', m.read('WS:TABLE-ROW[2]'))
        self.assertFalse(m.overlaps('WS:TABLE-ROW[1]', 'WS:TABLE-ROW[2]'))
        with self.assertRaisesRegex(StorageError, 'uninitialized'): m.read('WS:TABLE-ROW[1]')

    def test_group_move_pads_bytes_and_updates_elementary_alias(self):
        a = area(['01 A.', '05 A1 PIC X(2).', '01 B.', '05 B1 PIC X(3).'])
        m = Memory([a]); m.write('WS:A', b'hi'); m.group_move('WS:A', 'WS:B')
        self.assertEqual(b'hi ', m.read('WS:B.B1'))

    def test_group_move_snapshot_handles_overlapping_storage(self):
        a = area(['01 A.', '05 A1 PIC X(2).', '01 B REDEFINES A.', '05 B1 PIC X(4).'])
        m = Memory([a]); m.write('WS:A', b'xy'); m.group_move('WS:A', 'WS:B')
        self.assertEqual(b'xy  ', m.read('WS:B'))

    def test_anonymous_redefines_and_occurs_groups_are_not_discarded(self):
        a = area(['01 A PIC X(4).', '01 FILLER REDEFINES A.',
                  '05 PART OCCURS 2 TIMES PIC X(2).'])
        m = Memory([a]); m.write('WS:A', b'abcd')
        self.assertEqual(b'cd', m.read('WS:LY-FILLER-1.PART[2]'))

    def test_exact_lengths_and_qualified_names_required(self):
        m = Memory([area(['01 A PIC X(2).'])])
        with self.assertRaises(StorageError): m.write('WS:A', b'x')
        with self.assertRaises(StorageError): m.read('A')

    def test_full_program_gate_stays_closed_after_storage_translation(self):
        text = ('       IDENTIFICATION DIVISION.\n       PROGRAM-ID. T.\n'
                '       DATA DIVISION.\n       WORKING-STORAGE SECTION.\n'
                '       01 A PIC X(2).\n       PROCEDURE DIVISION.\n'
                '           STOP RUN.\n')
        result = storage_ir(bound('T.cbl', text), {})
        self.assertTrue(result['storage_complete'])
        self.assertFalse(result['whole_program_accepted'])


if __name__ == '__main__': unittest.main()
