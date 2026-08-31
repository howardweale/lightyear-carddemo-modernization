import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOC_ROOT = ROOT / "docs" / "milestones"


class MilestoneDocumentationTests(unittest.TestCase):
    def test_all_milestones_have_all_three_formats(self) -> None:
        for number in range(1, 45):
            stem = f"MS-{number:02d}"
            directory = DOC_ROOT / stem
            self.assertTrue(directory.is_dir(), stem)
            for suffix in (".md", ".docx", ".pdf"):
                path = directory / f"{stem}{suffix}"
                self.assertTrue(path.is_file(), path)
                self.assertGreater(path.stat().st_size, 500, path)

    def test_manifest_is_complete_and_content_addressed(self) -> None:
        manifest = json.loads((DOC_ROOT / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["milestone_count"], 44)
        self.assertEqual(manifest["artifact_count"], 132)
        self.assertEqual(set(manifest["formats"]), {"md", "docx", "pdf"})
        for artifact in manifest["artifacts"]:
            path = ROOT / artifact["path"]
            self.assertEqual(path.stat().st_size, artifact["bytes"])
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), artifact["sha256"])

    def test_standard_library_verifier_passes(self) -> None:
        result = subprocess.run(
            [sys.executable, "tools/generate_milestone_documentation.py", "verify"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('"artifacts": 132', result.stdout)

    def test_roadmap_reserves_ms45_for_sap_ase(self) -> None:
        roadmap = (ROOT / "LIGHTYEAR-ROADMAP.md").read_text(encoding="utf-8")
        self.assertIn("MS #44 — Milestone Documentation System", roadmap)
        self.assertIn("MS #45 — SAP ASE Semantic Source Adapter", roadmap)


if __name__ == "__main__":
    unittest.main()
