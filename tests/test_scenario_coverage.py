import unittest
from lightyear_mainframe.legacy_twin import ROOT, sha
from lightyear_mainframe.scenario_coverage import inventory, instrument, observe


class CoverageTests(unittest.TestCase):
    def test_pinned_inventories_and_pure_derived_source(self):
        for program,count in [('CBACT04C',47),('CBTRN02C',55)]:
            source=ROOT/f'spec/mainframe/public-source/{program}.cbl'
            raw=source.read_bytes();traced,inv=instrument(source.read_text(),program)
            self.assertEqual(count,len(inv['points']))
            self.assertEqual(raw,source.read_bytes())
            self.assertIn("LYC|D|",traced)
            self.assertIn('NOT INVALID KEY',traced)
            self.assertTrue(inv['file_operations'])
            self.assertEqual(sha(source.read_text().encode()),inv['source_sha256'])

    def test_only_observed_outcomes_count_and_unknown_trace_refuses(self):
        _,inv=instrument((ROOT/'spec/mainframe/public-source/CBACT04C.cbl').read_text(),'CBACT04C')
        row=observe(inv,'LYC|D|189|true\nLYC|D|189|true\n')
        self.assertEqual('1/94',row['decision_outcomes'])
        self.assertEqual(93,len(row['uncovered']))
        self.assertFalse(row['releasable'])
        for bad in ('LYC|D|9999|true','LYC|D|189|maybe','LYC|S|236|WRONG|00'):
            with self.assertRaisesRegex(ValueError,'trace-not-in-inventory'):observe(inv,bad)

    def test_loop_has_initial_and_backedge_probes(self):
        traced,inv=instrument((ROOT/'spec/mainframe/public-source/CBACT04C.cbl').read_text(),'CBACT04C')
        self.assertEqual(2,traced.count("LYC|D|188|true"))
        self.assertEqual(2,traced.count("LYC|D|188|false"))

    def test_unknown_program_refuses(self):
        with self.assertRaisesRegex(ValueError,'not-pinned'):inventory('','OTHER')
