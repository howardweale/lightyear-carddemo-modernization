from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

from lightyear_factory.agents import LocalAgentSet
from lightyear_factory.benchmark import MUTATIONS, benchmark_work_order
from lightyear_factory.context import GraphContextAssembler
from lightyear_factory.contracts import WorkOrder
from lightyear_factory.memory import MemoryPolicy, SemanticMemoryStore
from lightyear_factory.orchestrator import FactoryOrchestrator
from lightyear_factory.workspace import IsolatedWorkspace
from lightyear_knowledge_graph.explorer import ExplorerServer, GraphExplorerIndex
from lightyear_knowledge_graph.model import load_graph


ROOT = Path(__file__).resolve().parents[1]
GRAPH = ROOT / "knowledge" / "graph.snapshot.json.gz"
EVIDENCE = ROOT / "knowledge" / "evidence" / "source.pack.json.gz"


def prepare_rounding(workspace: IsolatedWorkspace, _: WorkOrder) -> None:
    path = workspace.resolve("factory/benchmarks/intcalc_candidate.py")
    before, after = MUTATIONS["rounding-mode"]
    content = path.read_text(encoding="utf-8")
    path.write_text(content.replace(before, after, 1), encoding="utf-8")


def classified_order(evaluation_class: str) -> WorkOrder:
    payload = benchmark_work_order("rounding-mode").to_dict()
    payload["metadata"]["evaluation_class"] = evaluation_class
    return WorkOrder.from_dict(payload)


class SemanticMemoryTests(unittest.TestCase):
    def _run(
        self,
        root: Path,
        memory: SemanticMemoryStore,
        order: WorkOrder | None = None,
        agents: LocalAgentSet | None = None,
        run_id: str = "verified-repair",
    ) -> dict:
        return FactoryOrchestrator(
            ROOT,
            root / "runs",
            agents or LocalAgentSet(),
            graph_path=GRAPH,
            evidence_path=EVIDENCE,
            prepare_workspace=prepare_rounding,
            memory_store=memory,
        ).run(order or benchmark_work_order("rounding-mode"), run_id)

    def test_verified_success_is_promoted_and_retrieved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            memory = SemanticMemoryStore(root / "memory")
            receipt = self._run(root, memory)
            validation = memory.validate()
            context = GraphContextAssembler(GRAPH, EVIDENCE).assemble(
                benchmark_work_order("rounding-mode"), ROOT
            )
            retrieval = memory.retrieve(
                benchmark_work_order("rounding-mode"),
                context["graph_content_sha256"],
                context["evidence_pack_sha256"],
            )
            record = memory.records()[0]
        self.assertEqual("passed", receipt["status"])
        self.assertEqual(
            "promoted-positive",
            receipt["semantic_memory"]["decision"]["disposition"],
        )
        self.assertEqual("verified_success", record["outcome"]["class"])
        self.assertTrue(record["knowledge"]["edit_templates"])
        self.assertTrue(record["privacy"]["verifier_private_artifacts_excluded"])
        self.assertEqual("passed", validation["status"])
        self.assertEqual(1, retrieval["statistics"]["records_returned"])
        self.assertEqual(record["experience_id"], retrieval["cards"][0]["experience_id"])
        self.assertIn("same graph entity", retrieval["cards"][0]["match_reasons"])

    def test_sealed_holdout_is_excluded_without_creating_a_record(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            memory = SemanticMemoryStore(root / "memory")
            receipt = self._run(
                root,
                memory,
                order=classified_order("sealed-holdout"),
                run_id="sealed-case-ref-only",
            )
        decision = receipt["semantic_memory"]["decision"]
        self.assertEqual("excluded", decision["disposition"])
        self.assertEqual("sealed-holdout-is-never-implementer-memory", decision["reason"])
        self.assertEqual([], memory.records())

    def test_blocked_run_becomes_non_executable_negative_memory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            memory = SemanticMemoryStore(root / "memory")
            receipt = self._run(
                root,
                memory,
                agents=LocalAgentSet(repair_rules=()),
                run_id="verified-failure",
            )
            record = memory.records()[0]
            validation = memory.validate()
            blocked_status = receipt["status"]
            decision_disposition = receipt["semantic_memory"]["decision"]["disposition"]
            outcome_class = record["outcome"]["class"]
            edit_templates = list(record["knowledge"]["edit_templates"])
        self.assertEqual("blocked", blocked_status)
        self.assertEqual("promoted-negative", decision_disposition)
        self.assertEqual("verified_failure", outcome_class)
        self.assertEqual([], edit_templates)
        self.assertEqual("passed", validation["status"])

    def test_graph_or_evidence_change_invalidates_retrieval(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            memory = SemanticMemoryStore(root / "memory")
            self._run(root, memory)
            context = GraphContextAssembler(GRAPH, EVIDENCE).assemble(
                benchmark_work_order("rounding-mode"), ROOT
            )
            retrieval = memory.retrieve(
                benchmark_work_order("rounding-mode"),
                "0" * 64,
                context["evidence_pack_sha256"],
            )
        self.assertEqual(0, retrieval["statistics"]["records_returned"])
        self.assertEqual(1, retrieval["statistics"]["stale_records"])

    def test_memory_context_is_bounded_and_role_visible(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            memory = SemanticMemoryStore(
                root / "memory",
                MemoryPolicy(maximum_context_bytes=8_000),
            )
            self._run(root, memory)
            order = benchmark_work_order("rounding-mode")
            context = GraphContextAssembler(GRAPH, EVIDENCE).assemble(order, ROOT)
            retrieval = memory.retrieve(
                order, context["graph_content_sha256"], context["evidence_pack_sha256"]
            )
            attached = GraphContextAssembler.attach_semantic_memory(
                context, retrieval, order
            )
            planner = GraphContextAssembler.planner_context(attached)
            capsule_ids = [item["capsule_id"] for item in context["source_excerpts"][:1]]
            builder = GraphContextAssembler.builder_context(
                attached, capsule_ids, ["workload:carddemo-intcalc"]
            )
        self.assertLessEqual(
            attached["statistics"]["context_bytes"], order.max_context_bytes
        )
        self.assertEqual(1, planner["statistics"]["semantic_memory_cards"])
        self.assertEqual(1, builder["statistics"]["semantic_memory_cards"])
        self.assertNotIn("verifier_private", json.dumps(planner))

    def test_existing_run_ingest_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = SemanticMemoryStore(root / "first-memory")
            receipt = self._run(root, first)
            second = SemanticMemoryStore(root / "second-memory")
            run_dir = root / "runs" / receipt["run_id"]
            one = second.ingest_run_dir(run_dir)
            two = second.ingest_run_dir(run_dir)
            record_count = len(second.records())
        self.assertEqual(one["experience_sha256"], two["experience_sha256"])
        self.assertEqual(1, record_count)

    def test_validation_detects_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            memory = SemanticMemoryStore(root / "memory")
            self._run(root, memory)
            path = next((root / "memory" / "experiences").glob("*.json"))
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["knowledge"]["summary"] = "tampered"
            path.write_text(json.dumps(payload), encoding="utf-8")
            validation = memory.validate()
        self.assertEqual("failed", validation["status"])
        self.assertTrue(any("hash mismatch" in item for item in validation["errors"]))

    def test_memory_schemas_and_control_tower_projection(self) -> None:
        schemas = [
            "semantic-memory-policy.schema.json",
            "semantic-experience.schema.json",
            "semantic-memory-snapshot.schema.json",
            "semantic-memory-retrieval.schema.json",
        ]
        for name in schemas:
            payload = json.loads((ROOT / "factory" / "schema" / name).read_text())
            self.assertEqual("https://json-schema.org/draft/2020-12/schema", payload["$schema"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            memory = SemanticMemoryStore(root / "memory")
            self._run(root, memory)
            index = GraphExplorerIndex(load_graph(GRAPH))
            server = ExplorerServer(
                ("127.0.0.1", 0),
                index,
                ROOT / "knowledge" / "viewer",
                memory_store=memory,
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_port}"
                with urlopen(f"{base}/api/memory/summary", timeout=3) as response:
                    summary = json.load(response)
                query = urlencode({"id": summary["experiences"][0]["experience_id"]})
                with urlopen(
                    f"{base}/api/memory/experience?{query}", timeout=3
                ) as response:
                    experience = json.load(response)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)
        self.assertEqual(1, summary["statistics"]["experience_count"])
        self.assertEqual("implementer", experience["privacy"]["audience"])
        app = (ROOT / "knowledge" / "viewer" / "app.js").read_text(encoding="utf-8")
        html = (ROOT / "knowledge" / "viewer" / "index.html").read_text(encoding="utf-8")
        self.assertIn('api("/api/memory/summary"', app)
        self.assertIn('id="memory-tab"', html)
        self.assertIn('id="memory-experiences"', html)


if __name__ == "__main__":
    unittest.main()
