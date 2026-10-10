import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from lightyear_mainframe import legacy_twin as twin
from lightyear_mainframe import posttran_invariants as inv
from lightyear_mainframe.records import load_copybook,to_ascii_fixed
from lightyear_mainframe.zos_bindings import load_bindings,dataset_binding

class ReviewTwinTests(unittest.TestCase):
    def test_clock_requires_real_intcalc_date_and_posttran_declares_unused(self):
        meta={'candidate_timestamp':'2022-07-18-00.00.00.000000'}
        for value in [None,'','0000000000','2022023000','20220718xx']:
            with self.assertRaises(ValueError): twin.runtime_clock('INTCALC',dict(meta,processing_date=value))
        self.assertNotIn('TWIN_PROCESSING_DATE',twin.runtime_clock('POSTTRAN',meta))
        self.assertEqual(twin.runtime_clock('INTCALC',dict(meta,processing_date='2022071800'))['TWIN_PROCESSING_DATE'],'2022071800')
    def test_missing_date_refuses_before_output_created(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'output'
            with patch.object(twin,'linux_platform'),patch.object(twin,'verify_build'),patch.object(twin,'public_inputs',return_value=('INTCALC',{'candidate_timestamp':'2022-07-18-00.00.00.000000'}, {},{})):
                with self.assertRaises(ValueError): twin.run(Path(t),'x',p)
            self.assertFalse(p.exists())
    def test_receipt_is_provisional_and_binds_limits(self):
        with tempfile.TemporaryDirectory() as t:
            r=twin.receipt(Path(t)/'receipt.json',job='POSTTRAN')
            self.assertFalse(r['releasable']);self.assertFalse(r['zos_confirmation'])
            self.assertEqual(r['oracle_status'],'provisional')
            self.assertEqual(r['twin_limits_sha256'],twin.sha((twin.ROOT/r['twin_limits_path']).read_bytes()))
    def test_ascii_and_ebcdic_iso_order_agrees_but_mixed_letters_does_not(self):
        dates=['2022-01-01','2022-12-31','2023-01-01']
        self.assertEqual(sorted(dates),sorted(dates,key=lambda d:d.encode('cp037')))
        self.assertNotEqual(sorted('aA0'),sorted('aA0',key=lambda d:d.encode('cp037')))

class PostingInvariantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _,cls.meta,cls.before,_=twin.public_inputs('posttran-public')
        cls.after=dict(cls.before)
        base=twin.ROOT/'tests/mainframe/fixtures/twin-posttran-output-v1'
        provenance=json.loads((base/'PROVENANCE.json').read_text())
        published=json.loads((twin.ROOT/'docs/factory/gnucobol-twin-result.json').read_text())['scenarios']['posttran-public']['outputs']
        for dd,digest in provenance['files'].items():
            raw=(base/dd).read_bytes()
            assert twin.sha(raw)==digest==published[dd]['sha256']
            cls.after[dd]=raw
    def check(self,after): return inv.check(self.before,after,timestamp=self.meta['candidate_timestamp'])
    def test_public_fixture_conservation(self):
        r=self.check(self.after)
        self.assertTrue(r['passed'],r['failures'][:5])
        self.assertEqual((r['posted'],r['rejected'],r['inputs']),(262,38,300))
    def test_missing_duplicate_or_modified_output_refused(self):
        lines=self.after['TRANFILE'].splitlines(keepends=True)
        for raw in [b''.join(lines[1:]),self.after['TRANFILE']+lines[0]]:
            self.assertFalse(self.check(dict(self.after,TRANFILE=raw))['passed'])
        raw=bytearray(self.after['TRANFILE']);raw[0]=ord('9')
        self.assertFalse(self.check(dict(self.after,TRANFILE=bytes(raw)))['passed'])
    def test_wrong_rejection_reason_refused(self):
        raw=bytearray(self.after['DALYREJS']);raw[350:354]=b'0109'
        self.assertFalse(self.check(dict(self.after,DALYREJS=bytes(raw)))['passed'])
    def test_collation_sensitive_keys_refused(self):
        raw=bytearray(self.before['XREFFILE']);raw[0]=ord('A')
        with self.assertRaisesRegex(ValueError,'collation-sensitive'):
            inv.require_collation_independent(dict(self.before,XREFFILE=bytes(raw)))
    def test_review_sheet_deterministic_unsigned_and_covers_reasons(self):
        a=inv.review_sheet(self.before,self.after)
        self.assertEqual(a,inv.review_sheet(self.before,self.after))
        self.assertEqual(len(a['records']),10)
        self.assertIsNone(a['signature'])
        selected={r['id'] for r in a['records']}
        reasons={r['WS-VALIDATION-FAIL-REASON'] for r in inv.records(self.after,'DALYREJS') if r['DALYTRAN-ID'] in selected}
        self.assertEqual(reasons,{r['WS-VALIDATION-FAIL-REASON'] for r in inv.records(self.after,'DALYREJS')})
