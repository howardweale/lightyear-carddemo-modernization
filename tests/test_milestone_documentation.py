import hashlib
from html.parser import HTMLParser
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
        for number in range(1, 71):
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
        supplemental = manifest["supplemental_artifacts"]
        self.assertEqual([a["path"] for a in supplemental], ["docs/milestones/MS-73/MS-73.md", "docs/milestones/MS-74/MS-74.md", "docs/milestones/MS-75/MS-75.md", "docs/milestones/MS-76/MS-76.md", "docs/milestones/MS-77/MS-77.md", "docs/milestones/MS-78/MS-78.md", "docs/milestones/MS-79/MS-79.md", "docs/milestones/MS-80/MS-80.md", "docs/milestones/MS-81/MS-81.md", "docs/milestones/MS-82/MS-82.md"])
        for artifact in supplemental:
            data = (ROOT / artifact["path"]).read_bytes()
            self.assertEqual(len(data), artifact["bytes"])
            self.assertEqual(hashlib.sha256(data).hexdigest(), artifact["sha256"])
        self.assertEqual(manifest["milestone_count"], 70)
        self.assertEqual(manifest["supplemental_milestone_count"], 10)
        self.assertEqual(manifest["searchable_milestone_count"], 80)
        self.assertEqual(manifest["artifact_count"], 210)
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
        self.assertEqual(readme.count("https://github.com/"), 151)
        self.assertEqual(readme.count("https://raw.githubusercontent.com/"), 70)
        self.assertNotRegex(readme, r"\]\(MS-\d{2}/")
        self.assertEqual(page.count('class="milestone"'), 80)
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
        self.assertEqual(len(raw_paths), 140)
        for relative in set(github_paths + raw_paths):
            self.assertTrue((ROOT / relative).is_file(), relative)

    def test_later_records_are_in_the_working_search_and_phase_filters(self) -> None:
        class Rows(HTMLParser):
            def __init__(self):
                super().__init__(); self.rows = []; self.current = None
            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if tag == "tr" and attrs.get("class") == "milestone":
                    self.current = {"dataset": {"search": attrs["data-search"], "phase": attrs["data-phase"]}}
                    self.rows.append(self.current)
                if tag == "a" and attrs.get("class") == "title" and self.current is not None:
                    self.current["url"] = attrs["href"]
            def handle_endtag(self, tag):
                if tag == "tr": self.current = None
        page = (DOC_ROOT / "index.html").read_text(encoding="utf-8")
        parsed = Rows(); parsed.feed(page)
        later = [row for row in parsed.rows if row["dataset"]["phase"] == "implementation"]
        self.assertEqual(10, len(later))
        script = re.search(r"<script>(.*?)</script>", page, re.DOTALL).group(1)
        harness = r'''const vm = require('node:vm');
const fs = require('node:fs');
const {rows, script} = JSON.parse(fs.readFileSync(0, 'utf8'));
const search = {value:'', addEventListener(_, fn){this.apply=fn;}};
const phase = {value:'all', options:[{value:'all'}, {value:'implementation'}, {value:'foundation'}],
  addEventListener(_, fn){this.apply=fn;}};
const count = {}, empty = {style:{}};
const controls = {'#search':search, '#phase':phase, '#result-count':count, '#empty':empty};
vm.runInNewContext(script, {document:{querySelector:q=>controls[q], querySelectorAll:()=>rows,
  addEventListener(){}}, location:{search:'?q=service+packs&phase=implementation',pathname:'/milestones/'},
  history:{replaceState(){}}, URLSearchParams});
const visible = () => rows.filter(row=>!row.hidden).map(row=>row.url);
const result = {initial:visible(), initialCount:count.textContent};
search.value='decidability'; search.apply(); result.decidability=visible();
search.value='cancellation'; search.apply(); result.cancellation=visible();
search.value=''; phase.value='implementation'; phase.apply(); result.later=visible();
phase.value='foundation'; phase.apply(); result.foundation=visible();
console.log(JSON.stringify(result));'''
        result = subprocess.run(["node", "-e", harness], input=json.dumps({"rows":parsed.rows,"script":script}),
                                capture_output=True, text=True, check=False)
        self.assertEqual(0, result.returncode, result.stderr)
        output = json.loads(result.stdout)
        for key, number in [("initial",79),("decidability",80),("cancellation",78)]:
            self.assertTrue(any(f"/MS-{number}/MS-{number}.md" in url for url in output[key]), (key, output))
        self.assertEqual(10, len(output["later"]))
        self.assertEqual(10, len(output["foundation"]))

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
        self.assertIn('"artifacts": 210', result.stdout)

    def test_idda_numbers_do_not_promote_planned_stages(self) -> None:
        catalog = json.loads((DOC_ROOT / "catalog.json").read_text(encoding="utf-8"))
        self.assertEqual(70, catalog["milestones"][-1]["number"])
        roadmap = (ROOT / "LIGHTYEAR-ROADMAP.md").read_text(encoding="utf-8")
        self.assertIn("| MS #69 | iDempiere Deterministic Semantic Comparison | Complete bounded baseline;", roadmap)
        self.assertIn("| MS #70 | iDempiere Bounded Triage and Evidence Assembly | Complete bounded safe-floor package;", roadmap)

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
            "| MS #51 | Oracle Native Execution Admission Gate | Admission contract complete; 40 NUMBER harnesses; 0 executions in this readiness snapshot. Separate [260-pair native campaign passed](docs/oracle-native-evidence.md). |",
            roadmap,
        )
        self.assertIn("4,000-execution native requirement", roadmap)
        self.assertIn("originally materialized zero of the 4,000", roadmap)
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
            "| MS #54 | CloudBank Executable Source Baseline | Passed; [published execution evidence](docs/receipts/index.html#ms54) |",
            roadmap,
        )
        self.assertIn("integration classes and seven native Oracle tests", roadmap)
        self.assertIn("MS #55 — CloudBank Customer PostgreSQL Mapping", roadmap)
        self.assertIn(
            "| MS #55 | CloudBank Customer PostgreSQL Mapping | Passed; [published execution evidence](docs/receipts/index.html#ms55) |",
            roadmap,
        )
        self.assertIn("all seven columns", roadmap)
        self.assertIn("MS #56 — First CloudBank Dark Factory Run", roadmap)
        self.assertIn(
            "| MS #56 | First CloudBank Dark Factory Run | Passed; [published execution evidence](docs/receipts/index.html#ms56) |",
            roadmap,
        )
        self.assertIn("exactly six customer-service paths", roadmap)


if __name__ == "__main__":
    unittest.main()
