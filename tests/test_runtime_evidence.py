from __future__ import annotations

import copy
import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

from lightyear_knowledge_graph.evidence_pack import EvidenceStore, load_evidence_pack
from lightyear_knowledge_graph.chat import GraphChatService
from lightyear_knowledge_graph.explorer import ExplorerServer, GraphExplorerIndex
from lightyear_knowledge_graph.model import load_graph
from lightyear_runtime.adapters import FixtureAdapter, LocalOracleAdapter
from lightyear_runtime.contracts import CaptureBundle, RuntimeContractError
from lightyear_runtime.engine import (
    RuntimeEvidenceEngine,
    load_snapshot,
    validate_snapshot,
    write_snapshot,
)
from lightyear_runtime.store import RuntimeEvidenceStore


ROOT = Path(__file__).resolve().parents[1]
GRAPH_PATH = ROOT / "knowledge" / "graph.snapshot.json.gz"
FIXTURE_PATH = ROOT / "knowledge" / "runtime" / "fixtures" / "intcalc-zos-replay.json"


class RuntimeEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.graph = load_graph(GRAPH_PATH)

    def test_local_capture_and_replay_are_deterministic_and_policy_honest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            engine = RuntimeEvidenceEngine(self.graph)
            first = engine.build([
                LocalOracleAdapter(root / "first").capture(),
                FixtureAdapter(FIXTURE_PATH).capture(),
            ])
            second = engine.build([
                LocalOracleAdapter(root / "second").capture(),
                FixtureAdapter(FIXTURE_PATH).capture(),
            ])
            self.assertEqual(first["content_sha256"], second["content_sha256"])
            self.assertEqual(2, first["statistics"]["run_count"])
            self.assertEqual(13, first["statistics"]["event_count"])
            self.assertEqual(5, first["statistics"]["observed_edges"])
            self.assertEqual(0, first["statistics"]["contradicted_edges"])
            for run in first["runs"]:
                self.assertEqual("passed", run["policies"]["development_readiness"]["status"])
                self.assertEqual("blocked", run["policies"]["mainframe_equivalence"]["status"])

    def test_runtime_ledger_and_snapshot_detect_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = RuntimeEvidenceEngine(self.graph).build([
                FixtureAdapter(FIXTURE_PATH).capture()
            ])
            path = root / "runtime.snapshot.json.gz"
            write_snapshot(payload, path)
            self.assertEqual([], validate_snapshot(load_snapshot(path), self.graph))
            tampered = copy.deepcopy(payload)
            tampered["runs"][0]["events"][0]["details"]["return_code"] = 12
            errors = validate_snapshot(tampered, self.graph)
            self.assertTrue(any("event hash" in item for item in errors))
            self.assertTrue(any("receipt hash" in item for item in errors))
            self.assertTrue(any("snapshot content hash" in item for item in errors))

    def test_unknown_graph_entity_is_rejected_at_ingestion(self) -> None:
        payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        payload["observations"][0]["entity_id"] = "legacy:jcl-job:DOES-NOT-EXIST"
        with self.assertRaisesRegex(RuntimeContractError, "absent node"):
            RuntimeEvidenceEngine(self.graph).build([CaptureBundle.from_dict(payload)])

    def test_contradiction_overrides_observation_and_blocks_both_policies(self) -> None:
        payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        target = payload["required_edges"][0]
        payload["observations"].append({
            "entity_kind": "edge",
            "entity_id": target,
            "assertion": "contradicted",
            "operation": "runtime_path_absent",
            "details": {"reason": "adversarial test"},
        })
        snapshot = RuntimeEvidenceEngine(self.graph).build([CaptureBundle.from_dict(payload)])
        projection = snapshot["projections"]["edges"][target]
        self.assertEqual("runtime_contradicted", projection["state"])
        self.assertEqual(0.0, projection["confidence"])
        run = snapshot["runs"][0]
        self.assertEqual("blocked", run["policies"]["development_readiness"]["status"])
        self.assertEqual("blocked", run["policies"]["mainframe_equivalence"]["status"])

    def test_runtime_store_defaults_unobserved_entities_to_static_only(self) -> None:
        payload = RuntimeEvidenceEngine(self.graph).build([FixtureAdapter(FIXTURE_PATH).capture()])
        store = RuntimeEvidenceStore(payload)
        observed = store.projection("edge", "edge:0594254ade360b961aef")
        self.assertEqual("runtime_observed", observed["state"])
        self.assertEqual(0.45, observed["confidence"])
        static = store.projection("node", "rule:intcalc:monthly-interest")
        self.assertEqual("static_only", static["state"])
        self.assertEqual(0.35, static["confidence"])

    def test_explorer_exposes_runtime_runs_and_entity_projection(self) -> None:
        snapshot = load_snapshot(ROOT / "knowledge" / "runtime" / "runtime.snapshot.json.gz")
        index = GraphExplorerIndex(self.graph)
        server = ExplorerServer(
            ("127.0.0.1", 0),
            index,
            ROOT / "knowledge" / "viewer",
            evidence_store=EvidenceStore(load_evidence_pack(
                ROOT / "knowledge" / "evidence" / "source.pack.json.gz"
            )),
            runtime_store=RuntimeEvidenceStore(snapshot),
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            with urlopen(f"{base}/api/runtime/summary", timeout=3) as response:
                summary = json.load(response)
            self.assertEqual(2, len(summary["runs"]))
            query = urlencode({"id": "edge:0594254ade360b961aef", "audience": "implementer"})
            with urlopen(f"{base}/api/edge?{query}", timeout=3) as response:
                edge = json.load(response)
            self.assertEqual("runtime_observed", edge["runtime"]["state"])
            run_id = summary["runs"][0]["run_id"]
            with urlopen(f"{base}/api/runtime/run?{urlencode({'id': run_id})}", timeout=3) as response:
                run = json.load(response)
            self.assertIn("mainframe_equivalence", run["policies"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_runtime_ui_exposes_truth_state_and_mainframe_boundary(self) -> None:
        html = (ROOT / "knowledge" / "viewer" / "index.html").read_text(encoding="utf-8")
        javascript = (ROOT / "knowledge" / "viewer" / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="runtime-tab"', html)
        self.assertIn('id="edge-runtime"', html)
        self.assertIn("Only z/OS-observed evidence", html)
        self.assertIn("/api/runtime/summary", javascript)
        self.assertIn("renderRuntimeProjection", javascript)

    def test_graph_chat_answers_when_from_bounded_runtime_evidence(self) -> None:
        snapshot = load_snapshot(ROOT / "knowledge" / "runtime" / "runtime.snapshot.json.gz")
        index = GraphExplorerIndex(self.graph, runtime_store=RuntimeEvidenceStore(snapshot))
        answer = GraphChatService(index).answer({
            "question": "When was this relationship observed?",
            "focus_edge_id": "edge:0594254ade360b961aef",
            "audience": "implementer",
            "provider": "local",
            "depth": 2,
        })
        self.assertEqual("when", answer["intent"])
        self.assertIn("runtime observation", answer["answer"])
        self.assertIn("simulated", answer["answer"])
        self.assertTrue(any("not necessarily the production schedule" in item for item in answer["limitations"]))


if __name__ == "__main__":
    unittest.main()
