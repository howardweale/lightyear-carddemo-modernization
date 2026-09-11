"""Publication must retain measured evidence and keep unrelated gates closed."""
from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch

from lightyear_data.cloudbank_publication import BUNDLE, ROOT, load_publication, workload_publication
from lightyear_knowledge_graph.explorer import GraphExplorerIndex, OPERATOR_WORKLOADS


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        self.hrefs.extend(value for key, value in attrs if key == "href")


class CloudBankPublicationTests(unittest.TestCase):
    def test_complete_chain_preserves_scope_and_measured_results(self):
        p = load_publication()
        self.assertTrue(p["ms67_complete"])
        self.assertFalse(p["production_ready"])
        self.assertFalse(p["production_deployed"])
        self.assertEqual(31, len(p["files"]))
        self.assertEqual(list(range(54, 68)), [r["number"] for r in p["milestones"]])
        self.assertEqual("Plan admitted", p["milestones"][4]["status"])
        self.assertEqual(5451, p["summary"]["load_requests"])
        self.assertEqual(160.6914815, p["summary"]["load_p95_ms"])
        self.assertEqual((622, 630, 455, 18), tuple(p["summary"][k] for k in ("pitr_rto_seconds", "pitr_limit_seconds", "backup_restore_rto_seconds", "rpo_seconds")))
        self.assertFalse(p["summary"]["measurements_changed"])
        self.assertIn("not independently repeated", p["verification"]["hmac_verification"])

    def test_byte_changes_missing_files_and_rewritten_manifest_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            shutil.copytree(ROOT / BUNDLE, root / BUNDLE)
            path = root / BUNDLE / "receipts/retained-load.json"
            original = path.read_bytes()
            path.write_bytes(original + b"\n")
            with self.assertRaisesRegex(ValueError, "bytes changed"):
                load_publication(root)
            value = json.loads(original); value["summary"]["p95_ms"] = 1
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_publication(root)
            path.unlink()
            with self.assertRaises(OSError):
                load_publication(root)
            path.write_bytes(original)
            manifest = root / BUNDLE / "publication-export.json"
            manifest.write_bytes(manifest.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "manifest changed"):
                load_publication(root)

    def test_control_tower_projects_only_cloudbank_and_fails_closed(self):
        p = load_publication()
        self.assertEqual({}, workload_publication("workload:carddemo-intcalc", p))
        self.assertEqual({}, workload_publication("oracle-reference:workload:order-to-cash", p))
        definitions = [w for w in OPERATOR_WORKLOADS if w['id'].startswith('cloudbank-reference:')]
        payload = {"nodes": [{"id": w['id'], "name": w['id'], "kind": "workload", "properties": {}} for w in definitions], "edges": [], "content_sha256": "a" * 64}
        index = GraphExplorerIndex(payload)
        for row in index.operator_context()['workloads']:
            self.assertIn("MS #67 passed", row['platform_qualification_status'])
            self.assertTrue((ROOT / row['platform_qualification_artifact']).is_file())
            self.assertFalse(row['production_ready'])
        with patch('lightyear_knowledge_graph.explorer.load_publication', side_effect=ValueError('tampered')):
            index = GraphExplorerIndex(payload)
        for row in index.operator_context()['workloads']:
            self.assertNotIn('publication_run_id', row)
            self.assertIn('required', row['platform_qualification_status'])

    def test_generated_projections_and_all_public_links_resolve(self):
        spec = importlib.util.spec_from_file_location('receipt_publisher', ROOT / 'tools/publish_cloudbank_receipts.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        for path, expected in module.outputs(load_publication()).items():
            self.assertEqual(expected, path.read_text(encoding="utf-8"), str(path))
        parser = Links(); parser.feed((ROOT / 'docs/receipts/index.html').read_text(encoding="utf-8"))
        for href in parser.hrefs:
            if href.startswith(('https://', '#')):
                continue
            self.assertTrue((ROOT / 'docs/receipts' / href.split('#')[0]).exists(), href)
        catalog = json.loads((ROOT / 'docs/milestones/catalog.json').read_text(encoding="utf-8"))
        for row in load_publication()['milestones']:
            entry = next(e for e in catalog['milestones'] if e['number'] == row['number'])
            self.assertEqual([f['path'] for f in row['receipts']], entry['execution_receipts'])
            self.assertEqual('Plan admitted' if row['number'] == 58 else 'Complete — execution passed', entry['status'])
        page = (ROOT / 'docs/index.html').read_text(encoding="utf-8")
        self.assertIn('MS67 complete. Nonproduction platform qualified.', page)
        self.assertIn('chat p95 was 21.36 seconds', page)
        self.assertIn('Mainframe equivalence claims remain gated', page)


if __name__ == '__main__':
    unittest.main()
