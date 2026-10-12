import copy
import unittest
from datetime import datetime,timezone
from lightyear_control_tower.factory_status import status,markdown,unresolved
from test_decision_console_factory_views import FactoryViewsTests


class FactoryStatusTests(FactoryViewsTests):
    def test_same_model_markdown_ages_and_scope_filters(self):
        pending=[dict(id="review-1",program="POSTTRAN",kind="twin-human-review",source_sha256="a"*64,created_at="2026-10-12T04:00:00Z"),dict(id="old-review",program="INTCALC",kind="equivalence-review",source_sha256="b"*64)]
        view=status(self.evidence,pending=pending,now=datetime(2026,10,12,4,10,tzinfo=timezone.utc))
        self.assertEqual([600,None],[r["age_seconds"] for r in view["pending_decisions"]])
        text=markdown(view)
        for row in view["programs"]:self.assertIn(row["raw_kills"],text)
        self.assertFalse(view["release_authorized"])
        rows=unresolved(self.evidence,pending=pending,program="POSTTRAN",kind="pending-review")["rows"]
        self.assertTrue(any(r["id"]=="review-1" for r in rows))
        self.assertTrue(all(r["program"]=="POSTTRAN" and r["source"]["sha256"] for r in rows))
        with self.assertRaises(ValueError):unresolved(self.evidence,program="../private")
        with self.assertRaises(ValueError):unresolved(self.evidence,kind="unlisted")

    def test_signed_io_overlay_is_exact_and_raw_receipt_unchanged(self):
        original=self.evidence.program("INTCALC")
        current=self.evidence.read("tower-run-38198096890/INTCALC/threshold.json")["twin"]
        gap=current["accepted_uncovered_IO"][0]
        overlay=dict(program="INTCALC",kind="io-exception-acceptance",outcome="accept",source_sha256="a"*64,details=dict(source_sha256=current["source_sha256"],outcome_id=gap["id"],outcome=gap["outcome"],line=gap["line"]))
        view=self.evidence.program("INTCALC",overlays=[overlay])
        self.assertEqual([gap],view["scenarios"]["value"]["signed_exceptions"])
        wrong=copy.deepcopy(overlay);wrong["details"]["source_sha256"]="f"*64
        self.assertFalse(self.evidence.program("INTCALC",overlays=[wrong])["scenarios"]["value"]["signed_exceptions"])
        self.assertEqual(original,self.evidence.program("INTCALC"))

    def test_class_counts_recompute_and_fix_retains_invalidation(self):
        for name in ("INTCALC","POSTTRAN"):
            v=self.evidence.program(name)
            rows=self.evidence.read("tower-run-38198096890/"+name+"/results.json")
            self.assertEqual(len(rows),sum(c["count"] for c in v["mutation"]["value"]["classes"]))
        overlay=dict(program="POSTTRAN",kind="legacy-behaviour-disposition",outcome="fix",source_sha256="a"*64,details=dict(dependent_arguments=["argument-1"]))
        rows=unresolved(self.evidence,overlays=[overlay],kind="invalidated-argument")["rows"]
        self.assertEqual(["argument-1"],[r["id"] for r in rows])

    def test_status_routes_unavailable_in_other_scopes(self):
        from unittest.mock import Mock
        from lightyear_control_tower.server import ConsoleAPI
        for scope in ("ms94-b06","carddemo-zos"):
            api=object.__new__(ConsoleAPI);api.service=Mock(scope=scope)
            for route in ("status","unresolved"):self.assertFalse(api.read(route,"fixture",{})["available"])

    def test_agreement_and_missing_comparison_are_not_divergences(self):
        rows=unresolved(self.evidence)["rows"]
        cases=self.evidence.read("generated-review311-classification.json")["cases"]
        by_id={r["id"]:r for r in rows}
        for case in cases:
            if case["classification"]=="expected-failure-agreement":self.assertNotIn(case["id"],by_id)
            if case["classification"]=="provisional-invariants-only":self.assertEqual("pending-review",by_id[case["id"]]["kind"])
        sheet=self.evidence.read("posttran-human-review-sheet.json")
        for record in sheet["records"]:self.assertEqual("pending-review",by_id[record["id"]]["kind"])
