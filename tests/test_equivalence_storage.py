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


class StorageBoundaryTests(unittest.TestCase):
    def test_program_paths_match_git_case(self):
        import subprocess
        from pathlib import Path
        from tools.inspect_equivalence_storage import PROGRAM_PATHS
        tracked = set(subprocess.check_output(['git', 'ls-files'], cwd=Path(__file__).resolve().parents[1], text=True).splitlines())
        self.assertTrue(set(PROGRAM_PATHS.values()) <= tracked)

    def test_large_working_storage_and_linkage_are_not_fd_records(self):
        from lightyear_mainframe.records import LayoutError
        declarations = [tokenize('       01 A PIC X(40000).')]
        for kind in ('WORKING-STORAGE', 'LINKAGE'):
            a = compile_area('A', declarations, kind=kind)
            self.assertEqual(40000, a['length'])
            self.assertEqual(40000, len(Memory([a]).buffers['A']))
        with self.assertRaises(LayoutError): compile_area('A', declarations, kind='FD')

    def test_larger_01_overlay_advances_by_widest(self):
        a = area(['01 A PIC X(2).', '01 B REDEFINES A PIC X(4).', '01 C PIC X.'])
        self.assertEqual(5, a['length'])
        self.assertEqual(4, Memory([a]).view('WS:C').offset)

    def test_larger_subordinate_overlay_refuses(self):
        from lightyear_mainframe.records import LayoutError
        with self.assertRaisesRegex(LayoutError, 'larger-subordinate'):
            area(['01 A.', '05 X PIC X(2).', '05 Y REDEFINES X PIC X(4).', '05 Z PIC X.'])

    def test_smaller_subordinate_overlay_keeps_original_width(self):
        a = area(['01 A.', '05 X PIC X(4).', '05 Y REDEFINES X PIC X(2).', '05 Z PIC X.'])
        self.assertEqual(4, Memory([a]).view('WS:A.Z').offset)

    def test_unsupported_is_diagnostic_data(self):
        text = '       DATA DIVISION.\n       WORKING-STORAGE SECTION.\n       01 P USAGE POINTER.\n       PROCEDURE DIVISION.\n'
        result = storage_ir(bound('unsupported.cbl', text), {})
        self.assertFalse(result['storage_complete'])
        self.assertIn('POINTER', result['unsupported'][0]['reason'])


if __name__ == '__main__': unittest.main()
