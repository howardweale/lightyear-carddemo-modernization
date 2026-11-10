"""CI only: pinned public CardDemo bytes and explicitly derived mutations."""
import base64
import hashlib
import json
from pathlib import Path
import unittest

from lightyear_mainframe.public_dataset_diff import (
    UPSTREAM, compare_dataset, compare_snapshots, decode_dataset)
from lightyear_mainframe.records import DecodeError

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "spec/modernization/carddemo-data/upstream/app/data/EBCDIC"


class PublicDatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = json.loads((ROOT/"tests/fixtures/carddemo-dataset-diff/public-data.json").read_text())
        assert fixture["commit"] == UPSTREAM
        cls.samples = {}
        for row in fixture["files"]:
            raw = base64.b64decode(row["base64"], validate=True)
            assert len(raw) == row["bytes"]
            assert hashlib.sha256(raw).hexdigest() == row["sha256"]
            if "slice_offset" not in row:
                assert hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest() == row["git_blob"]
            else:
                assert row["slice_offset"] == 0 and row["source_bytes"] == 105000
                assert row["source_sha256"] == "479b1f99cb7adcd9b79e94708f04c8bde0a010ba87f2ed69ba8af1effe57d076"
            cls.samples[row["path"].split("/")[-1]] = raw
        cls.account = (PUBLIC/"AWS.M2.CARDDEMO.ACCTDATA.PS").read_bytes()
        cls.xref = (PUBLIC/"AWS.M2.CARDDEMO.CARDXREF.PS").read_bytes()
        assert hashlib.sha256(cls.account).hexdigest() == "23167cdff65ca6dfa2e5bccee89112e3e83a80247a38e251f3981377ab098ec9"
        assert hashlib.sha256(cls.xref).hexdigest() == "b07ab2e5fa2500501c1dcaffe478ee74c4562a290174020a093dfa6f0e6325d3"

    def sample(self, name):
        return self.samples["AWS.M2.CARDDEMO."+name+".PS"]

    def delta(self, before, after, **options):
        return compare_dataset("POSTTRAN", "STEP15", "ACCTFILE", before, after, codec="cp037", **options)

    def test_known_account_fields_and_fifty_public_records(self):
        row = decode_dataset("INTCALC","STEP15","ACCTFILE",self.account,codec="cp037")
        self.assertEqual(len(row["records"]),50)
        fields = {f["path"].split(".")[-1]:f for f in row["records"][0]["fields"]}
        self.assertEqual(fields["ACCT-ID"]["value"],"1")
        self.assertEqual(fields["ACCT-ID"]["digits"],"00000000001")
        self.assertEqual(fields["ACCT-CURR-BAL"]["value"],"194.00")
        self.assertEqual(fields["ACCT-CURR-BAL"]["offset"],12)
        self.assertEqual(fields["ACCT-CURR-BAL"]["length"],12)
        self.assertFalse(row["qualified"])

    def test_all_three_job_bindings_use_public_bytes(self):
        cases = [
            ("POSTTRAN","STEP15","DALYTRAN",self.sample("DALYTRAN"),2),
            ("POSTTRAN","STEP15","TCATBALF",self.sample("TCATBALF"),50),
            ("INTCALC","STEP15","DISCGRP",self.sample("DISCGRP"),51),
            ("INTCALC","STEP15","TRANSACT",self.sample("DALYTRAN"),2),
            ("TRANREPT","STEP10R","TRANFILE",self.sample("DALYTRAN"),2),
            ("TRANREPT","STEP10R","CARDXREF",self.xref,50),
            ("TRANREPT","STEP10R","TRANTYPE",self.sample("TRANTYPE"),7),
            ("TRANREPT","STEP10R","TRANCATG",self.sample("TRANCATG"),18)]
        for job,step,dd,raw,count in cases:
            with self.subTest(job=job,dd=dd):
                result=compare_dataset(job,step,dd,raw,raw,codec="cp037")
                self.assertEqual(result["before_records"],count)
                self.assertTrue(result["identical"])
                self.assertTrue(result["details_complete"])
                self.assertFalse(result["production_controller_receipt"])

    def test_balance_change_and_filler_change_are_both_visible(self):
        raw = self.account[:300]
        changed = bytearray(raw)
        changed[22] = 0xf1  # public account 194.00 -> 194.10
        changed[-1] = 0xc1  # filler mutation, never ignored
        result = self.delta(raw,bytes(changed))
        self.assertEqual(result["changed_records"],1)
        differences = result["details"][0]["fields"]
        self.assertEqual(len(differences),2)
        balance = next(f for f in differences if f["path"].endswith("ACCT-CURR-BAL"))
        self.assertEqual((balance["before_value"],balance["after_value"]),("194.00","194.10"))
        self.assertTrue(any(f["filler"] for f in differences))
        self.assertFalse(result["identical"])

    def test_sign_encoding_change_is_not_silently_equal(self):
        raw = self.account[:300]
        changed = bytearray(raw)
        self.assertEqual(changed[23],0xc0)
        changed[23] = 0xf0  # same positive numeric value, different zoned sign
        result = self.delta(raw,bytes(changed))
        self.assertEqual(result["changed_records"],1)
        self.assertFalse(result["details"][0]["fields"][0]["value_changed"])
        self.assertFalse(result["keyed_identical"])

    def test_reorder_add_delete_and_missing_are_distinct(self):
        a,b,c = self.account[:300],self.account[300:600],self.account[600:900]
        reordered = self.delta(a+b,b+a)
        self.assertTrue(reordered["order_changed"])
        self.assertTrue(reordered["keyed_identical"])
        self.assertFalse(reordered["identical"])
        changed = self.delta(a+b,b+c)
        self.assertEqual((changed["added_records"],changed["deleted_records"]),(1,1))
        empty = self.delta(a,b"")
        self.assertEqual(empty["deleted_records"],1)
        with self.assertRaises(ValueError):
            compare_snapshots("POSTTRAN",{("STEP15","ACCTFILE"):a},{},codec="cp037")

    def test_duplicate_keys_truncation_and_bad_digits_refuse(self):
        raw = self.account[:300]
        with self.assertRaises(ValueError):
            self.delta(raw+raw,raw)
        with self.assertRaises(ValueError):
            self.delta(raw[:-1],raw)
        corrupt = bytearray(raw); corrupt[0] = 0x40
        with self.assertRaises(DecodeError):
            self.delta(bytes(corrupt),raw)
        # The upstream INIT file is not valid numeric transaction business data.
        with self.assertRaises(DecodeError):
            decode_dataset("POSTTRAN","STEP15","DALYTRAN",
                self.samples["AWS.M2.CARDDEMO.DALYTRAN.PS.INIT"],codec="cp037")

    def test_unsupported_job_binding_and_codec_refuse(self):
        for args in (("OTHER","STEP15","ACCTFILE"),("POSTTRAN","BAD","ACCTFILE"),
                     ("POSTTRAN","STEP15","STEPLIB")):
            with self.subTest(args=args),self.assertRaises(ValueError):
                decode_dataset(*args,self.account,codec="cp037")
        with self.assertRaises(ValueError):
            decode_dataset("POSTTRAN","STEP15","ACCTFILE",self.account,codec="ascii")

    def test_report_is_positional_fixed133_and_preserves_blanks(self):
        # Public TRANTYPE label embedded in an explicitly derived FB133 test line.
        label = self.sample("TRANTYPE")[2:52]
        line = label + b"\x40" * (133-len(label))
        changed = line[:-1]+b"\xc1"
        result = compare_dataset("TRANREPT","STEP10R","TRANREPT",line,changed,codec="cp037")
        self.assertEqual(result["comparison"],"positional-exact-text-bytes")
        self.assertEqual(result["changed_records"],1)
        self.assertEqual(result["details"][0]["fields"][0]["before_value"],"Purchase".ljust(133))
        with self.assertRaises(ValueError):
            compare_dataset("TRANREPT","STEP10R","TRANREPT",line+b"\n",changed,codec="cp037")

    def test_detail_cap_is_explicit_without_losing_counts(self):
        result = self.delta(self.account[:300],self.account[300:600],detail_limit=0)
        self.assertEqual((result["added_records"],result["deleted_records"]),(1,1))
        self.assertEqual(result["details"],[])
        self.assertEqual(result["omitted_detail_rows"],2)
        self.assertFalse(result["details_complete"])
        with self.assertRaises(ValueError):
            self.delta(b"",b"",detail_limit=True)

    def test_multi_dataset_scope_is_explicit(self):
        before = {("STEP15","ACCTFILE"):self.account,("STEP15","XREFFILE"):self.xref}
        result = compare_snapshots("POSTTRAN",before,dict(before),codec="cp037")
        self.assertTrue(result["identical"])
        self.assertEqual(len(result["datasets"]),2)
        self.assertIn("not a complete job-output inventory",result["scope"])
        self.assertFalse(result["qualified"])


if __name__ == "__main__":
    unittest.main()
