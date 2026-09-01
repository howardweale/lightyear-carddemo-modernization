from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.parse import urlencode
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from lightyear_factory.agents import LocalAgentSet, OpenAIAgentSet
from lightyear_factory.benchmark import benchmark_work_order, run_mutation_benchmark
from lightyear_factory.contracts import (
    ARTIFACT_SCHEMA_VERSION,
    RUN_RECEIPT_SCHEMA_VERSION,
    WORK_ORDER_SCHEMA_VERSION,
    ContractError,
    WorkOrder,
)
from lightyear_factory.ledger import RunLedger
from lightyear_factory.store import FactoryRunStore
from lightyear_knowledge_graph.explorer import ExplorerServer, GraphExplorerIndex
from lightyear_knowledge_graph.model import load_graph


ROOT = Path(__file__).resolve().parents[1]


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class FactoryTests(unittest.TestCase):
    def test_work_order_rejects_path_escape_and_verifier_audience(self) -> None:
        payload = benchmark_work_order("rounding-mode").to_dict()
        payload["scope"]["allowed_paths"] = ["../private-tests"]
        with self.assertRaisesRegex(ContractError, "Unsafe project-relative path"):
            WorkOrder.from_dict(payload)
        payload = benchmark_work_order("rounding-mode").to_dict()
        payload["policy"]["audience"] = "verifier"
        with self.assertRaisesRegex(ContractError, "implementer audience"):
            WorkOrder.from_dict(payload)

    def test_ledger_is_hash_chained_and_detects_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            ledger = RunLedger(path)
            first = ledger.append("ACCEPTED", "created", {"id": "one"})
            second = ledger.append("PLANNED", "planned", {"id": "two"})
            self.assertEqual(first["event_sha256"], second["previous_sha256"])
            self.assertTrue(ledger.verify())
            events = path.read_text(encoding="utf-8").splitlines()
            changed = json.loads(events[0])
            changed["payload"]["id"] = "tampered"
            events[0] = json.dumps(changed, sort_keys=True, separators=(",", ":"))
            path.write_text("\n".join(events) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "event hash"):
                RunLedger(path)

    def test_mutation_gauntlet_repairs_all_faults_without_false_acceptance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "benchmark"
            receipt = run_mutation_benchmark(ROOT, output)
            self.assertEqual("passed", receipt["status"])
            self.assertEqual(5, receipt["mutations"])
            self.assertEqual(5, receipt["autonomously_repaired"])
            self.assertEqual(0, receipt["false_acceptances"])
            self.assertTrue(all(item["attempts"] == 1 for item in receipt["results"]))
            self.assertTrue(all(item["baseline_rejected"] for item in receipt["results"]))
            self.assertTrue(all(item["baseline_status"] == "failed" for item in receipt["results"]))
            self.assertFalse(any(item["false_acceptance"] for item in receipt["results"]))
            for item in receipt["results"]:
                ledger = RunLedger(output / "runs" / item["run_id"] / "events.jsonl")
                self.assertTrue(ledger.verify())
                kinds = [event["kind"] for event in ledger.events]
                self.assertIn("baseline_verified", kinds)
                self.assertIn("changes_applied", kinds)
                self.assertIn("acceptance_gates_passed", kinds)

    def test_factory_json_schemas_match_runtime_contract_versions(self) -> None:
        expectations = {
            "work-order.schema.json": WORK_ORDER_SCHEMA_VERSION,
            "run-receipt.schema.json": RUN_RECEIPT_SCHEMA_VERSION,
            "agent-artifact.schema.json": ARTIFACT_SCHEMA_VERSION,
        }
        for name, expected in expectations.items():
            schema = json.loads((ROOT / "factory" / "schema" / name).read_text())
            self.assertEqual(expected, schema["properties"]["schema_version"]["const"])
        example = WorkOrder.load(
            ROOT / "factory" / "work-orders" / "intcalc-repair.example.json"
        )
        self.assertEqual(WORK_ORDER_SCHEMA_VERSION, example.to_dict()["schema_version"])

    @unittest.skipIf(os.name == "nt", "Bash launcher is verified on POSIX hosts")
    def test_python_runtime_admission_selects_supported_interpreter_and_rejects_old_one(self) -> None:
        runtime = ROOT / "python-runtime.sh"
        accepted = subprocess.run(
            [
                "bash",
                "-c",
                'source "$1"; LIGHTYEAR_PYTHON="$2"; lightyear_resolve_python',
                "lightyear-runtime-test",
                str(runtime),
                sys.executable,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        self.assertEqual(0, accepted.returncode, accepted.stderr)
        self.assertIn("Using Python", accepted.stdout)
        with tempfile.TemporaryDirectory() as directory:
            unsupported = Path(directory) / "python3.9"
            unsupported.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
            unsupported.chmod(0o755)
            rejected = subprocess.run(
                [
                    "bash",
                    "-c",
                    'source "$1"; LIGHTYEAR_PYTHON="$2"; lightyear_resolve_python',
                    "lightyear-runtime-test",
                    str(runtime),
                    str(unsupported),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
                env={**os.environ, "LIGHTYEAR_PYTHON": str(unsupported)},
            )
        self.assertEqual(2, rejected.returncode)
        self.assertIn("Python 3.11 or newer", rejected.stderr)

    def test_repeated_factory_collections_have_collision_safe_run_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_mutation_benchmark(ROOT, root / "first", ["rounding-mode"])
            run_mutation_benchmark(ROOT, root / "second", ["rounding-mode"])
            store = FactoryRunStore(root)
            runs = store.list_runs()
            self.assertEqual(2, len(runs))
            self.assertEqual(1, len({item["run_id"] for item in runs}))
            self.assertEqual(2, len({item["run_key"] for item in runs}))
            for item in runs:
                selected = store.run(item["run_key"])
                self.assertEqual(item["run_key"], selected["run_key"])
                self.assertEqual(item["run_id"], selected["receipt"]["run_id"])
            with self.assertRaises(KeyError):
                store.run("benchmark-rounding-mode")

    def test_public_run_view_redacts_verifier_artifacts_and_holdout_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "benchmark"
            run_mutation_benchmark(ROOT, output, ["rounding-mode"])
            public = FactoryRunStore(output / "runs").run("benchmark-rounding-mode")
            encoded = json.dumps(public)
            self.assertNotIn("private policy gate failed", encoded)
            self.assertNotIn("stdout", encoded)
            self.assertNotIn("stderr", encoded)
            self.assertTrue(
                all(
                    item["visibility"] != "verifier_private"
                    for item in public["receipt"]["artifacts"]
                )
            )
            self.assertTrue(
                any(event["payload"].get("redacted") for event in public["events"])
            )

    def test_openai_workers_use_strict_json_and_disable_storage(self) -> None:
        captured: dict = {}

        def opener(request: Request, timeout: int) -> FakeResponse:
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            captured["authorization"] = request.headers["Authorization"]
            captured["timeout"] = timeout
            result = {"summary": "Plan", "tasks": [{
                "id": "one",
                "objective": "Repair",
                "paths": ["factory/benchmarks/intcalc_candidate.py"],
                "graph_node_ids": ["workload:carddemo-intcalc"],
                "evidence_capsule_ids": [],
            }], "risks": []}
            return FakeResponse({"output": [{"content": [{
                "type": "output_text", "text": json.dumps(result)
            }]}]})

        agents = OpenAIAgentSet("secret", "test-model", opener=opener)
        result = agents.plan(benchmark_work_order("rounding-mode"), {"nodes": []})
        self.assertEqual("Plan", result["summary"])
        self.assertFalse(captured["payload"]["store"])
        self.assertTrue(captured["payload"]["text"]["format"]["strict"])
        self.assertEqual("Bearer secret", captured["authorization"])
        self.assertNotIn("secret", json.dumps(result))

    def test_local_builder_never_receives_private_gate_output(self) -> None:
        order = benchmark_work_order("rounding-mode")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "factory" / "benchmarks" / "intcalc_candidate.py"
            path.parent.mkdir(parents=True)
            path.write_text('ROUNDING = "half-up"\n', encoding="utf-8")
            proposal = LocalAgentSet().build(
                order,
                {"tasks": []},
                {
                    "status": "failed",
                    "gates": [{"id": "private", "status": "failed", "output_sha256": "abc"}],
                },
                root,
                1,
            )
            self.assertEqual(1, len(proposal["edits"]))
            self.assertNotIn("expected", json.dumps(proposal).casefold())

    def test_factory_control_room_api_and_ui_respect_audience(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "benchmark"
            run_mutation_benchmark(ROOT, output, ["rounding-mode"])
            index = GraphExplorerIndex(load_graph(ROOT / "knowledge" / "graph.snapshot.json.gz"))
            server = ExplorerServer(
                ("127.0.0.1", 0),
                index,
                ROOT / "knowledge" / "viewer",
                factory_store=FactoryRunStore(output),
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_port}"
                with urlopen(f"{base}/api/factory/runs", timeout=3) as response:
                    runs = json.load(response)["runs"]
                self.assertEqual("benchmark-rounding-mode", runs[0]["run_id"])
                self.assertRegex(runs[0]["run_key"], r"^factory-[0-9a-f]{24}$")
                query = urlencode(
                    {"id": runs[0]["run_key"], "audience": "implementer"}
                )
                with urlopen(f"{base}/api/factory/run?{query}", timeout=3) as response:
                    public = json.load(response)
                self.assertTrue(any(item["payload"].get("redacted") for item in public["events"]))
                query = urlencode(
                    {"id": runs[0]["run_key"], "audience": "verifier"}
                )
                verifier_url = f"{base}/api/factory/run?{query}"
                with self.assertRaises(HTTPError) as rejected:
                    urlopen(verifier_url, timeout=3)
                self.assertEqual(401, rejected.exception.code)
                request = Request(
                    verifier_url,
                    headers={"Authorization": f"Bearer {server.verifier_token}"},
                )
                with urlopen(request, timeout=3) as response:
                    verifier = json.load(response)
                self.assertFalse(any(item["payload"].get("redacted") for item in verifier["events"]))
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)

        app = (ROOT / "knowledge" / "viewer" / "app.js").read_text(encoding="utf-8")
        html = (ROOT / "knowledge" / "viewer" / "index.html").read_text(encoding="utf-8")
        self.assertIn('api("/api/factory/run"', app)
        self.assertIn("run.run_key", app)
        self.assertIn('id="factory-tab"', html)
        self.assertIn('id="factory-timeline"', html)
        self.assertIn("required agent actions attested", app)


if __name__ == "__main__":
    unittest.main()
