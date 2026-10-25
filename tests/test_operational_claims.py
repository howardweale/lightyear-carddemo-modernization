from hashlib import sha256
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.operational_claims import ClaimRefused, added_lines, audit, check, in_scope, receipt_path, supported, units


class OperationalClaimsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Synthetic CI")
        self.git("config", "user.email", "ci@example.invalid")
        self.write("seed.txt", "fixture\n")
        self.base = self.commit()

    def git(self, *args):
        return subprocess.check_output(["git", "-c", "commit.gpgsign=false", *args], cwd=self.root, text=True)

    def write(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8", newline="\n")

    def commit(self):
        self.git("add", ".")
        self.git("commit", "-qm", "synthetic fixture")
        return self.git("rev-parse", "HEAD").strip()

    def receipt(self, kind="installation"):
        data = dict(schema="public-operational-receipt/1", kind=kind,
                    status="completed", historical_only=True,
                    source_commit=self.base, evidence_sha256="a" * 64,
                    observed_at="2026-10-23T16:00:00Z",
                    public_url="https://github.com/howardweale/lightyear-carddemo-modernization/issues/436#issuecomment-1")
        if kind == "ci":
            data.update(public_url="https://github.com/howardweale/lightyear-carddemo-modernization/actions/runs/123", conclusion="success")
        raw = json.dumps(data)
        self.write("docs/receipt.json", raw)
        return "[public receipt](receipt.json#sha256=" + sha256(raw.encode()).hexdigest() + ")"

    def test_original_ms106_installed_wording_fails(self):
        # Exact operational sentence in the retained MS-106; no old file edited.
        self.write("docs/MS-106.md", "The Tower is installed as a user login service at `http://127.0.0.1:8769/`.\n")
        self.commit()
        with self.assertRaisesRegex(ClaimRefused, "evidence-required"):
            check(self.root, self.base)

    def test_bound_installation_receipt_passes(self):
        self.write("docs/now.md", "The Tower is installed. " + self.receipt() + "\n")
        self.commit()
        self.assertEqual(["installation"], check(self.root, self.base)[0]["kinds"])

    def test_planned_and_not_yet_pass_without_receipt(self):
        self.write("docs/next.md", "Planned: Tower installed as a user login service.\nNot yet signed.\n")
        self.commit()
        self.assertTrue(all(row["planned"] for row in check(self.root, self.base)))

    def test_marker_cannot_cover_second_clause(self):
        for text in ("Planned: installation accepted; Tower is installed.",
                     "Not yet approved but Tower is installed.",
                     "Planned: installation accepted. Tower is installed."):
            with self.subTest(text=text):
                rows = list(units(text))
                self.assertTrue(rows[0]["planned"])
                self.assertFalse(rows[-1]["planned"])
                self.assertFalse(supported(rows[-1], "docs/n.md", lambda _: b""))

    def test_ci_receipt_cannot_prove_installation(self):
        self.write("docs/n.md", "Tower is installed. " + self.receipt("ci") + "\n")
        self.commit()
        with self.assertRaisesRegex(ClaimRefused, "evidence-required"):
            check(self.root, self.base)

    def test_ci_link_elsewhere_does_not_prove_claim(self):
        self.write("docs/n.md", "Tower is installed.\n\n[CI](https://github.com/howardweale/lightyear-carddemo-modernization/actions/runs/123)\n")
        self.commit()
        with self.assertRaisesRegex(ClaimRefused, "evidence-required"):
            check(self.root, self.base)

    def test_changed_receipt_invalidates_unchanged_claim(self):
        self.write("docs/n.md", "Tower is installed. " + self.receipt() + "\n")
        base = self.commit()
        self.write("docs/receipt.json", (self.root / "docs/receipt.json").read_text() + " ")
        self.commit()
        with self.assertRaisesRegex(ClaimRefused, "receipt-bytes"):
            check(self.root, base)

    def test_deleted_receipt_invalidates_unchanged_claim(self):
        self.write("docs/n.md", "Tower is installed. " + self.receipt() + "\n")
        base = self.commit()
        (self.root / "docs/receipt.json").unlink()
        self.commit()
        with self.assertRaisesRegex(ClaimRefused, "regular-file"):
            check(self.root, base)

    def test_receipt_link_must_be_regular_git_blob(self):
        self.write("docs/n.md", "Tower is installed. " + self.receipt() + "\n")
        self.commit()
        blob = self.git("rev-parse", "HEAD:docs/receipt.json").strip()
        self.git("update-index", "--cacheinfo", "120000," + blob + ",docs/receipt.json")
        self.git("commit", "-qm", "synthetic link mode")
        with self.assertRaisesRegex(ClaimRefused, "regular-file"):
            check(self.root, self.base)

    def test_paths_and_missing_digests_refused(self):
        for target in ("../../outside.json#sha256=" + "a" * 64,
                       "https://example.invalid/a.json#sha256=" + "a" * 64,
                       "receipt.json", "receipt.json#sha256=bad",
                       "..%2f..%2foutside.json#sha256=" + "a" * 64):
            with self.subTest(target=target), self.assertRaises(ClaimRefused):
                receipt_path("docs/a.md", target)

    def test_history_audited_without_exempting_new_backdated_claim(self):
        self.write("docs/old-2020-01-01.md", "Tower is installed.\n")
        base = self.commit()
        self.write("seed.txt", "next\n")
        self.commit()
        self.assertEqual([], check(self.root, base))
        report = audit(self.root, base)
        self.assertEqual(1, report["unsupported_count"])
        self.assertEqual([], report["errors"])
        self.assertFalse(report["authority_granted"])
        self.write("docs/new-2020-01-01.md", "Tower is installed.\n")
        self.commit()
        with self.assertRaisesRegex(ClaimRefused, "evidence-required"):
            check(self.root, base)

    def test_scope_and_json_string_values(self):
        for path in ("docs/guide.md", "docs/milestones/current.html", "docs/factory/current-status.json", "index.html"):
            self.assertTrue(in_scope(path))
        self.assertFalse(in_scope("tests/fixture.py"))
        rows = list(units('  "summary": "Tower is installed.",\n  "approved": false,\n'))
        self.assertEqual(1, len(rows))
        self.assertEqual(["installation"], rows[0]["kinds"])

    def test_fenced_example_and_multiple_hunks(self):
        self.assertEqual([], list(units("```powershell\nWrite-Host 'installed'\n```\n")))
        self.assertEqual({3, 8, 9}, added_lines("@@ -1 +3 @@\n-old\n+new\n@@ -8 +8,2 @@\n+x\n+y\n"))

    def test_same_clause_needs_every_evidence_kind(self):
        text = "Tower is installed and signed. " + self.receipt()
        row = list(units(text))[0]
        self.assertEqual(["decision", "installation"], row["kinds"])
        self.assertFalse(supported(row, "docs/n.md", lambda p: (self.root / p).read_bytes()))

    def test_html_receipt_and_failed_ci_metadata(self):
        link = self.receipt("ci")
        target = link.split("(", 1)[1][:-1]
        row = list(units('Tests passed. <a href="' + target + '">receipt</a>'))[0]
        self.assertTrue(supported(row, "docs/n.html", lambda p: (self.root / p).read_bytes()))
        payload = json.loads((self.root / "docs/receipt.json").read_bytes())
        payload["conclusion"] = "failure"
        raw = json.dumps(payload).encode()
        row = list(units("Tests passed. [receipt](receipt.json#sha256=" + sha256(raw).hexdigest() + ")"))[0]
        with self.assertRaisesRegex(ClaimRefused, "ci-binding"):
            supported(row, "docs/n.md", lambda _: raw)

    def test_existing_commit_gate_calls_operational_gate(self):
        from tools.check_record_commit_claims import check as combined
        self.write("docs/factory/n.md", "Tower is installed.\n")
        self.commit()
        with self.assertRaisesRegex(ClaimRefused, "evidence-required"):
            combined(self.root, self.base)

    def test_exact_legacy_audit_decoding_preserves_claims_and_source(self):
        from unittest.mock import patch
        raw = b"Tower is installed. \x97 Historical text.\n"
        path = "docs/historical.md"
        self.write(path, "placeholder")
        (self.root / path).write_bytes(raw)
        revision = self.commit()
        with patch("tools.operational_claims.LEGACY_AUDIT_CP1252", {path: sha256(raw).hexdigest()}):
            report = audit(self.root, revision)
            self.assertEqual([], report["errors"])
            self.assertEqual(1, report["unsupported_count"])
            self.assertEqual([dict(path=path, file_sha256=sha256(raw).hexdigest(), encoding="cp1252")], report["legacy_decodings"])
            with self.assertRaises(UnicodeDecodeError):
                check(self.root, self.base)
        self.assertEqual(raw, (self.root / path).read_bytes())

    def test_legacy_binding_cannot_cover_altered_bytes_or_different_path(self):
        from unittest.mock import patch
        from tools.operational_claims import audit_text
        raw = b"Tower is installed. \x97 Historical text.\n"
        with patch("tools.operational_claims.LEGACY_AUDIT_CP1252", {"docs/old.md": sha256(raw).hexdigest()}):
            for path, changed in (("docs/old.md", raw + b"changed"), ("docs/other.md", raw)):
                with self.subTest(path=path), self.assertRaises(UnicodeDecodeError):
                    audit_text(path, changed)
        self.assertEqual(("ASCII source", "utf-8"), audit_text("docs/new.md", b"ASCII source"))

    def test_unknown_historical_encoding_remains_audit_error(self):
        path = "docs/unknown.md"
        self.write(path, "placeholder")
        (self.root / path).write_bytes(b"Tower is installed. \xff")
        revision = self.commit()
        report = audit(self.root, revision)
        self.assertEqual([dict(path=path, error="source-unavailable")], report["errors"])
        self.assertEqual([], report["legacy_decodings"])
