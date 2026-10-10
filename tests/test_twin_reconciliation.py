import tempfile
import unittest
from pathlib import Path
from lightyear_mainframe.twin_reconciliation import compare_images, reference
from lightyear_mainframe.legacy_twin import ROOT, public_inputs
from lightyear_mainframe.records import load_copybook


class ReconciliationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.layout=load_copybook(ROOT/'spec/mainframe/copybooks/CVACT01Y.cpy')
        cls.keys=['ACCOUNT-RECORD.ACCT-ID']
        cls.raw=public_inputs('intcalc-discriminating')[2]['ACCTFILE']

    def compare(self, other):
        return compare_images(self.raw,other,self.layout,self.keys)

    def test_exact_identity(self):
        result=self.compare(self.raw)
        self.assertTrue(result['byte_identical'])
        self.assertFalse(result['fields'])

    def test_filler_difference_is_never_hidden(self):
        modified=bytearray(self.raw); modified[299]=ord('!')
        result=self.compare(bytes(modified))
        self.assertFalse(result['byte_identical'])
        self.assertTrue(any(d['filler'] for d in result['fields'].values()))

    def test_numeric_representation_difference_is_never_hidden(self):
        modified=bytearray(self.raw)
        # Same positive digit, different zoned sign encoding.
        lookup=dict(zip(b'{ABCDEFGHI',b'0123456789'))
        original=modified[23]
        self.assertIn(original,lookup)
        modified[23]=lookup[original]
        result=self.compare(bytes(modified))
        d=next(iter(result['fields'].values()))
        self.assertEqual(d['value_records'],0)
        self.assertEqual(d['raw_records'],1)

    def test_record_order_is_reported(self):
        lines=self.raw.splitlines(keepends=True)
        result=self.compare(b''.join(reversed(lines)))
        self.assertTrue(result['order_or_framing_only'])
        self.assertFalse(result['byte_identical'])

    def test_missing_and_duplicate_records_are_not_equal(self):
        lines=self.raw.splitlines(keepends=True)
        self.assertEqual(self.compare(b''.join(lines[1:]))['deleted'],1)
        with self.assertRaisesRegex(ValueError,'duplicate'):
            self.compare(self.raw+lines[0])

    def test_missing_disclosure_reference_is_execution_failure(self):
        _,meta,images,_=public_inputs('intcalc-missing-disclosure')
        with tempfile.TemporaryDirectory() as tmp:
            result=reference(meta,images,Path(tmp)/'reference')
            self.assertEqual(result['status'],'execution-failure')
            self.assertIn('DEFAULT DISCLOSURE MISSING',(Path(tmp)/'reference/failure.txt').read_text())

    def test_reference_runs_discriminating_fixture_without_expected_outputs(self):
        _,meta,images,_=public_inputs('intcalc-discriminating')
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'reference'
            self.assertEqual(reference(meta,images,folder)['status'],'completed')
            self.assertEqual(len((folder/'TRANSACT').read_bytes().splitlines()),13)


if __name__=='__main__':
    unittest.main()
