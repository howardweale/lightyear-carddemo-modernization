import hashlib
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOC_ROOT = ROOT / "docs" / "milestones"


class MilestoneDocumentationTests(unittest.TestCase):
    def test_all_milestones_have_all_three_formats(self) -> None:
        for number in range(1, 63):
            stem = f"MS-{number:02d}"
            directory = DOC_ROOT / stem
            self.assertTrue(directory.is_dir(), stem)
            for suffix in (".md", ".docx", ".pdf"):
                path = directory / f"{stem}{suffix}"
                self.assertTrue(path.is_file(), path)
                self.assertGreater(path.stat().st_size, 500, path)

    def test_manifest_is_complete_and_content_addressed(self) -> None:
        manifest = json.loads((DOC_ROOT / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema_version"], "1.1")
        self.assertEqual(manifest["milestone_count"], 62)
        self.assertEqual(manifest["artifact_count"], 186)
        self.assertEqual(set(manifest["formats"]), {"md", "docx", "pdf"})
        for artifact in manifest["artifacts"]:
            path = ROOT / artifact["path"]
            self.assertEqual(path.stat().st_size, artifact["bytes"])
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), artifact["sha256"])
        self.assertEqual(
            {item["path"] for item in manifest["library_files"]},
            {
                "docs/milestones/README.md",
                "docs/milestones/index.html",
                "docs/milestones/assets/lightyear-reversed.svg",
            },
        )
        for library_file in manifest["library_files"]:
            path = ROOT / library_file["path"]
            self.assertEqual(path.stat().st_size, library_file["bytes"])
            self.assertEqual(
                hashlib.sha256(path.read_bytes()).hexdigest(), library_file["sha256"]
            )

    def test_indexes_are_searchable_and_use_portable_links(self) -> None:
        readme = (DOC_ROOT / "README.md").read_text(encoding="utf-8")
        page = (DOC_ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn("Open the searchable milestone index", readme)
        self.assertEqual(readme.count("https://github.com/"), 125)
        self.assertEqual(readme.count("https://raw.githubusercontent.com/"), 62)
        self.assertNotRegex(readme, r"\]\(MS-\d{2}/")
        self.assertEqual(page.count('class="milestone"'), 62)
        self.assertIn('id="search"', page)
        self.assertIn('id="phase"', page)
        self.assertIn("URLSearchParams", page)
        self.assertIn('data-search="', page)
        self.assertIn("stored procedure", page.lower())
        self.assertIn("oracle", page.lower())
        self.assertIn("sap ase", page.lower())
        self.assertIn("lightyear-reversed.svg", page)
        self.assertIn("#7d57ea", page.lower())
        self.assertIn("Where context becomes trusted action", readme)

        github_paths = re.findall(
            r"https://github\.com/howardweale/lightyear-carddemo-modernization/blob/main/([^\"\s)]+)",
            readme + page,
        )
        raw_paths = re.findall(
            r"https://raw\.githubusercontent\.com/howardweale/lightyear-carddemo-modernization/main/([^\"\s)]+)",
            readme + page,
        )
        self.assertTrue(github_paths)
        self.assertEqual(len(raw_paths), 124)
        for relative in set(github_paths + raw_paths):
            self.assertTrue((ROOT / relative).is_file(), relative)

    def test_brand_assets_are_consistent_across_surfaces(self) -> None:
        canonical = ROOT / "brand" / "assets" / "lightyear-primary.svg"
        viewer = ROOT / "knowledge" / "viewer" / "assets" / "lightyear-primary.svg"
        website = ROOT / "docs" / "assets" / "lightyear-primary.svg"
        reversed_logo = ROOT / "brand" / "assets" / "lightyear-reversed.svg"
        published_reversed = DOC_ROOT / "assets" / "lightyear-reversed.svg"
        self.assertEqual(canonical.read_bytes(), viewer.read_bytes())
        self.assertEqual(canonical.read_bytes(), website.read_bytes())
        self.assertEqual(reversed_logo.read_bytes(), published_reversed.read_bytes())
        for stem in (
            "lightyear-primary",
            "lightyear-reversed",
            "lightyear-icon",
            "lightyear-horizontal",
            "lightyear-horizontal-reversed",
        ):
            svg = ROOT / "brand" / "assets" / f"{stem}.svg"
            png = ROOT / "brand" / "assets" / f"{stem}.png"
            self.assertGreater(svg.stat().st_size, 200, svg)
            self.assertGreater(png.stat().st_size, 2_000, png)
        self.assertGreater((ROOT / "brand" / "Lightyear-Deck-Template.pptx").stat().st_size, 30_000)
        for foundation in (
            "LIGHTYEAR-Investor-Foundation.pptx",
            "LIGHTYEAR-Developer-Architecture-Foundation.pptx",
        ):
            self.assertGreater(
                (ROOT / "brand" / "foundation" / foundation).stat().st_size,
                10_000_000,
            )
        tokens = json.loads((ROOT / "brand" / "tokens.json").read_text(encoding="utf-8"))
        self.assertEqual("#15184D", tokens["colors"]["navy"])
        self.assertEqual("#7D57EA", tokens["colors"]["violet"])
        self.assertEqual("#A7702C", tokens["colors"]["bronze"])

    def test_search_script_has_valid_javascript(self) -> None:
        page = (DOC_ROOT / "index.html").read_text(encoding="utf-8")
        script = re.search(r"<script>(.*?)</script>", page, re.DOTALL)
        self.assertIsNotNone(script)
        result = subprocess.run(
            ["node", "--check", "-"],
            cwd=ROOT,
            input=script.group(1),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_standard_library_verifier_passes(self) -> None:
        result = subprocess.run(
            [sys.executable, "tools/generate_milestone_documentation.py", "verify"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('"artifacts": 186', result.stdout)

    def test_roadmap_records_unified_estate_navigation(self) -> None:
        roadmap = (ROOT / "LIGHTYEAR-ROADMAP.md").read_text(encoding="utf-8")
        self.assertIn("MS #44 — Milestone Documentation System", roadmap)
        self.assertIn("MS #44.1 — Searchable Milestone Index Reliability", roadmap)
        self.assertIn("MS #45 — SAP ASE Semantic Source Adapter", roadmap)
        self.assertIn("| MS #45 | SAP ASE Semantic Source Adapter | Complete |", roadmap)
        self.assertIn("MS #46 — Unified Estate Operator Navigation", roadmap)
        self.assertIn("| MS #46 | Unified Estate Operator Navigation | Complete |", roadmap)
        self.assertIn("MS #47 — Graph-Bound Live Evidence Control Tower", roadmap)
        self.assertIn("| MS #47 | Graph-Bound Live Evidence Control Tower | Complete |", roadmap)
        self.assertIn("MS #48 — iDempiere Oracle Reference Estate Inventory", roadmap)
        self.assertIn(
            "| MS #48 | iDempiere Oracle Reference Estate Inventory | Complete |", roadmap
        )
        self.assertIn(
            "MS #49 — Oracle Dialect Authority Corpus and Executable Fixtures", roadmap
        )
        self.assertIn(
            "| MS #49 | Oracle Dialect Authority Corpus and Executable Fixtures | Complete |",
            roadmap,
        )
        self.assertIn("MS #50 — Oracle Semantic Coverage Program", roadmap)
        self.assertIn(
            "| MS #50 | Oracle Semantic Coverage Program | Complete |",
            roadmap,
        )
        self.assertIn("Release 0.50.1 executes all 920 governed cases", roadmap)
        self.assertIn("Release 0.50.2 executes", roadmap)
        self.assertIn("Release 0.50.3 executes all 280", roadmap)
        self.assertIn("Release 0.50.4 executes all 480", roadmap)
        self.assertIn("500 unique bounded-model-verified behaviors", roadmap)
        self.assertIn("2,024 bounded evidence records", roadmap)
        self.assertIn("No governed catalog cases remain unexecuted", roadmap)
        self.assertIn("MS #51 — Oracle Native Execution Admission Gate", roadmap)
        self.assertIn(
            "| MS #51 | Oracle Native Execution Admission Gate | Admission contract complete; SQL harnesses and authorized native runs pending |",
            roadmap,
        )
        self.assertIn("4,000-execution native requirement", roadmap)
        self.assertIn("materializes zero of the 4,000", roadmap)
        self.assertIn("MS #52 — Oracle Customer (Large) Control Tower Projection", roadmap)
        self.assertIn(
            "| MS #52 | Oracle Customer (Large) Control Tower Projection | Complete |",
            roadmap,
        )
        self.assertIn("20 static document-flow trace scenarios", roadmap)
        self.assertIn("MS #53 — CloudBank Modern Oracle Reference Estate", roadmap)
        self.assertIn(
            "| MS #53 | CloudBank Modern Oracle Reference Estate | Complete |",
            roadmap,
        )
        self.assertIn("five business workloads and 20 curated migration-risk scenarios", roadmap)
        self.assertIn("MS #54 — CloudBank Executable Source Baseline", roadmap)
        self.assertIn(
            "| MS #54 | CloudBank Executable Source Baseline | Complete; signed execution receipts remain operator-held evidence |",
            roadmap,
        )
        self.assertIn("integration classes and seven native Oracle tests", roadmap)
        self.assertIn("MS #55 — CloudBank Customer PostgreSQL Mapping", roadmap)
        self.assertIn(
            "| MS #55 | CloudBank Customer PostgreSQL Mapping | Mapping qualified; signed native receipt remains operator-held evidence |",
            roadmap,
        )
        self.assertIn("all seven columns", roadmap)
        self.assertIn("MS #56 — First CloudBank Dark Factory Run", roadmap)
        self.assertIn(
            "| MS #56 | First CloudBank Dark Factory Run | Factory contract complete; operator dual-run receipt pending |",
            roadmap,
        )
        self.assertIn("exactly six customer-service paths", roadmap)


if __name__ == "__main__":
    unittest.main()
