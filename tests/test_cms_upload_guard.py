"""CI-only fixtures: no CMS execution or archive download."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from tools.cms.upload_guard import check, check_repository, ALLOWED
from tools.cms.diagnostic_audit_report import render


def workflow(path=ALLOWED, retention="1"):
    return {"jobs": {"probe": {"steps": [{"uses": "actions/upload-artifact@v4",
        "with": {"path": path, "retention-days": retention, "if-no-files-found": "error"}}]}}}


class UploadGuardTests(unittest.TestCase):
    def test_real_workflows_and_allowlisted_fixture(self):
        self.assertTrue(check_repository(Path(__file__).resolve().parents[1]))
        check(workflow())

    def test_raw_and_indirect_uploads_fail(self):
        for path in ["work/cms/f0/a.log", "work/cms/f0/a.lst", "work/diagnostic.json",
                     "work/stderr.txt", "work/cms/f0/compile-logs", "work/**", "${{ inputs.path }}",
                     ALLOWED + "\nwork/cms/f0/a.log"]:
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "path-not-allowlisted"):
                check(workflow(path))

    def test_retention_missing_receipt_and_missing_upload_fail(self):
        for retention in [None, "14", "${{ inputs.days }}"]:
            with self.assertRaisesRegex(ValueError, "retention"):
                check(workflow(retention=retention))
        config=workflow();del config["jobs"]["probe"]["steps"][0]["with"]["if-no-files-found"]
        with self.assertRaisesRegex(ValueError, "missing-receipt"):
            check(config)
        with self.assertRaisesRegex(ValueError, "step-missing"):
            check({"jobs": {}})

    def test_audit_text_tracks_input_and_does_not_quote_diagnostics(self):
        row={"program":"FIXTURE", "dialect":"fixture", "possible_source_quote":True,
             "raw_diagnostics_uploaded":False,"diagnostic_text":"PRIVATE FIXTURE SOURCE"}
        value={"run_id":1,"evidence_head":"a"*40,"public_receipt":{"raw_diagnostics_uploaded":False,
            "source_uploaded":False,"compile":{"diagnostic_audit":[row]}}}
        first=render(value)
        self.assertIn("1 flagged attempts",first);self.assertNotIn("PRIVATE FIXTURE SOURCE",first)
        changed=deepcopy(value);changed["public_receipt"]["compile"]["diagnostic_audit"][0]["possible_source_quote"]=False
        self.assertIn("0 flagged attempts",render(changed));self.assertNotEqual(first,render(changed))
        changed=deepcopy(value);changed["public_receipt"]["raw_diagnostics_uploaded"]=True
        with self.assertRaisesRegex(ValueError,"publication-boundary"):
            render(changed)

    def test_committed_addendum_matches_retained_metadata(self):
        root=Path(__file__).resolve().parents[1]
        value=json.loads((root/"docs/cms/feasibility-ipps-fy2021-ci-2026-10-17.json").read_bytes())
        self.assertEqual(render(value),(root/"docs/cms/diagnostic-audit-correction-2026-10-18.md").read_text(encoding="utf-8"))
