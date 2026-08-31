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
        for number in range(1, 46):
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
        self.assertEqual(manifest["milestone_count"], 45)
        self.assertEqual(manifest["artifact_count"], 135)
        self.assertEqual(set(manifest["formats"]), {"md", "docx", "pdf"})
        for artifact in manifest["artifacts"]:
            path = ROOT / artifact["path"]
            self.assertEqual(path.stat().st_size, artifact["bytes"])
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), artifact["sha256"])
        self.assertEqual(
            {item["path"] for item in manifest["library_files"]},
            {"docs/milestones/README.md", "docs/milestones/index.html"},
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
        self.assertEqual(readme.count("https://github.com/"), 91)
        self.assertEqual(readme.count("https://raw.githubusercontent.com/"), 45)
        self.assertNotRegex(readme, r"\]\(MS-\d{2}/")
        self.assertEqual(page.count('class="milestone"'), 45)
        self.assertIn('id="search"', page)
        self.assertIn('id="phase"', page)
        self.assertIn("URLSearchParams", page)
        self.assertIn('data-search="', page)
        self.assertIn("stored procedure", page.lower())
        self.assertIn("oracle", page.lower())
        self.assertIn("sap ase", page.lower())

        github_paths = re.findall(
            r"https://github\.com/howardweale/lightyear-carddemo-modernization/blob/main/([^\"\s)]+)",
            readme + page,
        )
        raw_paths = re.findall(
            r"https://raw\.githubusercontent\.com/howardweale/lightyear-carddemo-modernization/main/([^\"\s)]+)",
            readme + page,
        )
        self.assertTrue(github_paths)
        self.assertEqual(len(raw_paths), 90)
        for relative in set(github_paths + raw_paths):
            self.assertTrue((ROOT / relative).is_file(), relative)

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
        self.assertIn('"artifacts": 135', result.stdout)

    def test_roadmap_reserves_ms45_for_sap_ase(self) -> None:
        roadmap = (ROOT / "LIGHTYEAR-ROADMAP.md").read_text(encoding="utf-8")
        self.assertIn("MS #44 — Milestone Documentation System", roadmap)
        self.assertIn("MS #44.1 — Searchable Milestone Index Reliability", roadmap)
        self.assertIn("MS #45 — SAP ASE Semantic Source Adapter", roadmap)
        self.assertIn("| MS #45 | SAP ASE Semantic Source Adapter | Complete |", roadmap)


if __name__ == "__main__":
    unittest.main()
