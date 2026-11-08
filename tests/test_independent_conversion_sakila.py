"""Synthetic capture-document unit tests only; never database equivalence evidence."""
import copy
from decimal import Decimal
import json
import unittest

from tools.independent_conversion_demo.compare import (
    assemble, compare, configuration, InsufficientEvidence, loads)


class SakilaIndependentTests(unittest.TestCase):
    def setUp(self):
        self.manifest, self.digest, self.contract = configuration()
        self.captures = {}
        for engine in ("sqlserver", "postgres"):
            observations = {}
            for view in ("customer_list", "sales_by_store"):
                names = list(self.contract["mapping"][view][engine])
                if view == "customer_list":
                    values = [[1,"Alex Fixture","1 Fixture Way","00100","555-0100","Same City","Example","active",1],
                              [2,"Alex Fixture","2 Fixture Way","00101",None,"Same City","Example","",1]]
                else:
                    values = [["Same City,Example","Pat Manager","3.30"],
                              ["Same City,Example","Pat Manager","5.00"]]
                    if engine == "sqlserver":
                        names = ["store_id"]+names
                        values = [[i+1]+v for i,v in enumerate(values)]
                observations[view] = dict(
                    columns=[dict(name=n,type="fixture-native-type") for n in names],
                    rows=[dict(zip(names,v)) for v in values])
            self.captures[engine] = assemble(
                engine, self.manifest["engines"][engine]["image"], "SYNTHETIC UNIT FIXTURE",
                "original", observations, manifest=self.manifest, manifest_sha=self.digest)

    def compare(self, **kwargs):
        return compare(self.captures["sqlserver"], self.captures["postgres"],
                       manifest=self.manifest, manifest_sha=self.digest, contract=self.contract, **kwargs)

    def test_common_fields_match_with_strict_schema_differences(self):
        report = self.compare()
        self.assertEqual("COMPARED",report["status"])
        for view in report["views"].values():
            self.assertEqual("DIFFERENT",view["strict_schema"])
            self.assertEqual("MATCH",view["common_fields"])
        self.assertEqual("NOT_OBSERVED",report["sensitivity_controls"])

    def test_labelled_active_predicate_control_detected(self):
        target = self.captures["postgres"]
        target["variant"] = "active-flip"
        for row in target["views"]["customer_list"]["rows"]:
            row["notes"] = "" if row["notes"] == "active" else "active"
        report = self.compare(expected_right_variant="active-flip")
        self.assertEqual("DIFFERENT",report["views"]["customer_list"]["common_fields"])

    def test_labelled_duplicate_name_store_payment_omission_detected(self):
        target = self.captures["postgres"]
        target["variant"] = "payment-omission"
        target["views"]["sales_by_store"]["rows"][1]["total_sales"] = "4.40"
        report = self.compare(expected_right_variant="payment-omission")
        self.assertEqual("DIFFERENT",report["views"]["sales_by_store"]["common_fields"])

    def test_multiplicity_null_and_exact_decimal_preserved(self):
        rows = self.captures["postgres"]["views"]["sales_by_store"]["rows"]
        rows[1]["total_sales"] = "3.30"
        self.assertEqual("DIFFERENT",self.compare()["views"]["sales_by_store"]["common_fields"])
        rows[1]["total_sales"] = Decimal("5.000")
        self.assertEqual("MATCH",self.compare()["views"]["sales_by_store"]["common_fields"])
        self.captures["postgres"]["views"]["customer_list"]["rows"][1]["phone"] = ""
        self.assertEqual("DIFFERENT",self.compare()["views"]["customer_list"]["common_fields"])

    def test_missing_failed_changed_image_and_incomplete_rows_are_insufficient(self):
        original = copy.deepcopy(self.captures)
        for mutate in (
                lambda p:p.update(status="startup-failed"),
                lambda p:p.update(image="postgres:latest"),
                lambda p:p.update(manifest_sha256="0"*64),
                lambda p:p["views"]["sales_by_store"].update(rows=[]),
                lambda p:p["views"].pop("customer_list")):
            self.captures = copy.deepcopy(original)
            mutate(self.captures["postgres"])
            self.assertEqual("INSUFFICIENT_EVIDENCE",self.compare()["status"])
        self.assertEqual("INSUFFICIENT_EVIDENCE", compare(None,None)["status"])

    def test_float_and_unlabelled_control_never_pass(self):
        target = self.captures["postgres"]
        target["views"]["sales_by_store"]["rows"][0]["total_sales"] = 3.3
        self.assertEqual("INSUFFICIENT_EVIDENCE",self.compare()["status"])
        target["variant"] = "active-flip"
        self.assertEqual("INSUFFICIENT_EVIDENCE",self.compare()["status"])

    def test_duplicate_json_fields_and_nonfinite_numbers_refused(self):
        for raw in ('{"x":1,"x":2}', '{"x":NaN}'):
            with self.assertRaises(InsufficientEvidence):
                loads(raw)

    def test_encoded_upstream_views_preserve_exact_bytes(self):
        import base64
        import hashlib
        from pathlib import Path
        from tools.independent_conversion_demo.compare import ROOT
        for relative, metadata in self.manifest["views"].items():
            record = loads((ROOT.parent.parent/relative).read_bytes())
            raw = base64.b64decode(record["sql_base64"], validate=True)
            self.assertEqual(metadata["view_sha256"], hashlib.sha256(raw).hexdigest())
            self.assertEqual(record["bytes"], len(raw))
            self.assertTrue(raw.startswith(b"CREATE VIEW"))
