from __future__ import annotations

import json
from io import BytesIO
import tempfile
import types
import unittest
from pathlib import Path
from urllib.error import HTTPError

from lightyear_factory.agents import ModelAgentSet
from lightyear_factory.benchmark import benchmark_work_order
from lightyear_factory.context import GraphContextAssembler
from lightyear_factory.contracts import ContractError, WorkOrder
from lightyear_factory.evals import (
    EvaluationPolicy,
    load_evaluation_catalog,
    run_model_evaluation,
    validate_evaluation_catalog,
)
from lightyear_factory.orchestrator import FactoryOrchestrator
from lightyear_factory.patches import PatchBroker
from lightyear_factory.private_benchmark import policy_checks
from lightyear_factory.providers import (
    ModelProvider,
    OpenAIResponsesProvider,
    ProviderError,
    ProviderResult,
    ScriptedModelProvider,
)
from lightyear_factory.workspace import IsolatedWorkspace


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "factory" / "evals" / "carddemo-v0.12-public.json"
TARGET = ROOT / "factory" / "benchmarks" / "intcalc_candidate.py"


def planner() -> dict:
    return {
        "summary": "Use graph evidence to restore the approved file.",
        "tasks": [
            {
                "id": "repair",
                "objective": "Restore source-faithful behavior",
                "paths": ["factory/benchmarks/intcalc_candidate.py"],
                "graph_node_ids": ["workload:carddemo-intcalc"],
            }
        ],
        "risks": [],
    }


def diagnosis() -> dict:
    return {
        "summary": "The private semantic gate rejected the candidate.",
        "failure_codes": ["GATE_FAILED:private-intcalc-policy"],
        "builder_guidance": "Reconcile the approved file with graph-grounded source behavior.",
        "risk": "medium",
    }


def proposal() -> dict:
    return {
        "summary": "Restore truncation semantics.",
        "edits": [
            {
                "path": "factory/benchmarks/intcalc_candidate.py",
                "find": 'ROUNDING = "half-up"',
                "replace": 'ROUNDING = "down"',
                "rationale": "The source-backed rule requires truncation toward zero.",
            }
        ],
        "blocked_reason": None,
    }


def replacement_proposal(before: str, after: str) -> dict:
    return {
        "summary": "Restore the canonical constant.",
        "edits": [{
            "path": "factory/benchmarks/intcalc_candidate.py",
            "find": after,
            "replace": before,
            "rationale": "The graph-grounded source rule requires the canonical value.",
        }],
        "blocked_reason": None,
    }


class FailingProvider(ModelProvider):
    provider_id = "failing-test"
    model = "failing-test-model"

    def complete(self, role, instruction, payload, schema) -> ProviderResult:
        raise ProviderError(
            role,
            "rate_limit_exceeded",
            status_code=429,
            retryable=True,
            attempts=5,
            retries=[{"attempt": 1, "delay_ms": 1000, "error_code": "rate_limit_exceeded"}],
        )


class ModelWorkcellTests(unittest.TestCase):
    def test_context_is_graph_grounded_bounded_and_source_backed(self) -> None:
        order = benchmark_work_order("rounding-mode")
        context = GraphContextAssembler(
            ROOT / "knowledge" / "graph.snapshot.json.gz",
            ROOT / "knowledge" / "evidence" / "source.pack.json.gz",
        ).assemble(order, ROOT)
        self.assertEqual("implementer", context["audience"])
        self.assertTrue(context["nodes"])
        self.assertTrue(context["edges"])
        self.assertTrue(context["source_excerpts"])
        self.assertEqual(1, len(context["allowed_files"]))
        self.assertLessEqual(
            context["statistics"]["context_bytes"], order.max_context_bytes
        )
        self.assertRegex(context["content_sha256"], r"^[0-9a-f]{64}$")
        self.assertNotIn("inspector_private", json.dumps(context))

    def test_patch_broker_validates_every_edit_before_writing(self) -> None:
        order = benchmark_work_order("rounding-mode")
        with tempfile.TemporaryDirectory() as directory:
            workspace = IsolatedWorkspace(
                ROOT,
                Path(directory) / "workspace",
                order.allowed_paths,
            )
            workspace.create()
            path = workspace.resolve("factory/benchmarks/intcalc_candidate.py")
            before = path.read_text(encoding="utf-8")
            with self.assertRaisesRegex(ContractError, "expected one exact match"):
                PatchBroker().apply(
                    order,
                    workspace,
                    [
                        {
                            "path": "factory/benchmarks/intcalc_candidate.py",
                            "find": 'ROUNDING = "down"',
                            "replace": 'ROUNDING = "half-up"',
                            "rationale": "first",
                        },
                        {
                            "path": "factory/benchmarks/intcalc_candidate.py",
                            "find": "marker-that-does-not-exist",
                            "replace": "anything",
                            "rationale": "second",
                        },
                    ],
                )
            self.assertEqual(before, path.read_text(encoding="utf-8"))

    def test_scripted_model_run_emits_call_evidence_and_passes_private_gate(self) -> None:
        order = benchmark_work_order("rounding-mode")

        def prepare(workspace: IsolatedWorkspace, _: WorkOrder) -> None:
            path = workspace.resolve("factory/benchmarks/intcalc_candidate.py")
            text = path.read_text(encoding="utf-8")
            path.write_text(
                text.replace('ROUNDING = "down"', 'ROUNDING = "half-up"', 1),
                encoding="utf-8",
            )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            provider = ScriptedModelProvider([planner(), diagnosis(), proposal()])
            receipt = FactoryOrchestrator(
                ROOT,
                root / "runs",
                ModelAgentSet(provider),
                graph_path=ROOT / "knowledge" / "graph.snapshot.json.gz",
                evidence_path=ROOT / "knowledge" / "evidence" / "source.pack.json.gz",
                prepare_workspace=prepare,
            ).run(order, "scripted-model-repair")
            artifacts = receipt["artifacts"]
            model_evidence = [
                item for item in artifacts if item["artifact_type"] == "model-call-evidence"
            ]
            change_set = [item for item in artifacts if item["artifact_type"] == "change-set"]
        self.assertEqual("passed", receipt["status"])
        self.assertEqual("model-backed", receipt["intelligence"]["mode"])
        self.assertEqual(3, receipt["intelligence"]["calls"])
        self.assertEqual(3, len(model_evidence))
        self.assertEqual(1, len(change_set))
        self.assertEqual(0, receipt["intelligence"]["estimated_cost_usd"])
        builder_request = next(item for item in provider.requests if item["role"] == "builder")
        self.assertTrue(builder_request["payload"]["graph_context"]["source_excerpts"])
        self.assertNotIn("allowed_files", builder_request["payload"]["graph_context"])

    def test_model_call_budget_fails_closed(self) -> None:
        payload = benchmark_work_order("rounding-mode").to_dict()
        payload["policy"]["max_model_calls"] = 1
        order = WorkOrder.from_dict(payload)
        agents = ModelAgentSet(ScriptedModelProvider([planner(), planner()]))
        agents.plan(order, {"nodes": []})
        with self.assertRaisesRegex(ContractError, "max_model_calls"):
            agents.plan(order, {"nodes": []})

    def test_openai_provider_retries_transient_429_and_receipts_the_delay(self) -> None:
        calls = 0
        sleeps: list[float] = []
        schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["ok"],
            "properties": {"ok": {"type": "boolean"}},
        }

        class Response:
            headers = {"x-ratelimit-remaining-requests": "499"}

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def read(self):
                return json.dumps({
                    "status": "completed",
                    "model": "gpt-test",
                    "usage": {"input_tokens": 10, "output_tokens": 2},
                    "output": [{"content": [{
                        "type": "output_text", "text": json.dumps({"ok": True})
                    }]}],
                }).encode()

        def opener(request, timeout):
            nonlocal calls
            calls += 1
            body = json.loads(request.data)
            self.assertEqual(25_000, body["max_output_tokens"])
            if calls == 1:
                raise HTTPError(
                    request.full_url,
                    429,
                    "rate limited",
                    {"Retry-After": "0"},
                    BytesIO(json.dumps({
                        "error": {"code": "rate_limit_exceeded"}
                    }).encode()),
                )
            return Response()

        provider = OpenAIResponsesProvider(
            "secret",
            "gpt-test",
            opener=opener,
            sleep=sleeps.append,
            jitter=lambda _: 0.0,
        )
        result = provider.complete("planner", "Return JSON.", {}, schema)
        self.assertTrue(result.content["ok"])
        self.assertEqual(2, result.evidence["attempts"])
        self.assertEqual(1, result.evidence["retry_count"])
        self.assertEqual([0.0], sleeps)
        self.assertEqual("499", result.evidence["rate_limits"]["x-ratelimit-remaining-requests"])

    def test_openai_provider_does_not_retry_billing_429(self) -> None:
        calls = 0

        def opener(request, timeout):
            nonlocal calls
            calls += 1
            raise HTTPError(
                request.full_url,
                429,
                "quota",
                {},
                BytesIO(json.dumps({"error": {"code": "insufficient_quota"}}).encode()),
            )

        provider = OpenAIResponsesProvider("secret", opener=opener, sleep=lambda _: None)
        with self.assertRaises(ProviderError) as raised:
            provider.complete("planner", "Return JSON.", {}, {"type": "object"})
        self.assertEqual(1, calls)
        self.assertFalse(raised.exception.retryable)
        self.assertNotIn("secret", json.dumps(raised.exception.safe_dict()))

    def test_public_catalog_has_36_rejected_faults_and_is_not_called_holdout(self) -> None:
        catalog = load_evaluation_catalog(CATALOG)
        validation = validate_evaluation_catalog(ROOT, catalog)
        self.assertEqual("public-calibration", catalog["evaluation_class"])
        self.assertEqual(36, validation["cases"])
        self.assertGreaterEqual(len(validation["categories"]), 8)
        canonical = TARGET.read_text(encoding="utf-8")
        namespace = types.ModuleType("candidate")
        exec(compile(canonical, str(TARGET), "exec"), namespace.__dict__)
        self.assertTrue(all(policy_checks(namespace)))
        for case in catalog["cases"]:
            mutated = canonical.replace(case["before"], case["after"], 1)
            namespace = types.ModuleType(f"candidate_{case['id'].replace('-', '_')}")
            exec(compile(mutated, str(TARGET), "exec"), namespace.__dict__)
            self.assertFalse(all(policy_checks(namespace)), case["id"])

    def test_evaluation_receipt_scores_repair_and_false_acceptance_separately(self) -> None:
        catalog = load_evaluation_catalog(CATALOG)
        catalog["id"] = "single-case-test"
        catalog["minimum_repair_rate"] = 1.0
        catalog["cases"] = [
            next(item for item in catalog["cases"] if item["id"] == "rounding-half-up")
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog_path = root / "catalog.json"
            catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
            receipt = run_model_evaluation(
                ROOT,
                root / "evaluation",
                catalog_path,
                lambda _: ModelAgentSet(
                    ScriptedModelProvider([planner(), diagnosis(), proposal()])
                ),
            )
        self.assertEqual("passed", receipt["status"])
        self.assertEqual(1, receipt["baselines_rejected"])
        self.assertEqual(1, receipt["autonomously_repaired"])
        self.assertEqual(0, receipt["false_acceptances"])
        self.assertEqual(1.0, receipt["repair_rate"])

    def test_evaluation_checkpoints_stops_and_resumes_without_repeating_completed_case(self) -> None:
        catalog = load_evaluation_catalog(CATALOG)
        selected = [
            next(item for item in catalog["cases"] if item["id"] == "rounding-half-up"),
            next(item for item in catalog["cases"] if item["id"] == "monthly-divisor-100"),
        ]
        catalog["id"] = "resume-test"
        catalog["minimum_repair_rate"] = 1.0
        catalog["cases"] = selected
        policy = EvaluationPolicy(pace_seconds=0)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog_path = root / "catalog.json"
            output = root / "evaluation"
            catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
            calls = 0

            def first_factory(order):
                nonlocal calls
                calls += 1
                if calls == 1:
                    case = selected[0]
                    return ModelAgentSet(ScriptedModelProvider([
                        planner(), diagnosis(), replacement_proposal(case["before"], case["after"])
                    ]))
                return ModelAgentSet(FailingProvider())

            stopped = run_model_evaluation(
                ROOT, output, catalog_path, first_factory, policy=policy, sleep=lambda _: None
            )
            checkpoint = json.loads((output / "evaluation.checkpoint.json").read_text())
            case = selected[1]
            resumed = run_model_evaluation(
                ROOT,
                output,
                catalog_path,
                lambda _: ModelAgentSet(ScriptedModelProvider([
                    planner(), diagnosis(), replacement_proposal(case["before"], case["after"])
                ])),
                policy=policy,
                resume=True,
                sleep=lambda _: None,
            )
        self.assertEqual("stopped", stopped["status"])
        self.assertEqual(["rounding-half-up"], checkpoint["completed_case_ids"])
        self.assertEqual("passed", resumed["status"])
        self.assertEqual(2, resumed["completed_cases"])

    def test_evaluation_global_call_budget_stops_before_next_case(self) -> None:
        catalog = load_evaluation_catalog(CATALOG)
        selected = [
            next(item for item in catalog["cases"] if item["id"] == "rounding-half-up"),
            next(item for item in catalog["cases"] if item["id"] == "monthly-divisor-100"),
        ]
        catalog["id"] = "budget-stop-test"
        catalog["cases"] = selected
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog_path = root / "catalog.json"
            catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
            case = selected[0]
            receipt = run_model_evaluation(
                ROOT,
                root / "evaluation",
                catalog_path,
                lambda _: ModelAgentSet(ScriptedModelProvider([
                    planner(), diagnosis(), replacement_proposal(case["before"], case["after"])
                ])),
                policy=EvaluationPolicy(max_model_calls=3, pace_seconds=0),
                sleep=lambda _: None,
            )
        self.assertEqual("stopped", receipt["status"])
        self.assertEqual("evaluation_budget_exhausted", receipt["stopped_reason"]["code"])
        self.assertEqual(1, receipt["completed_cases"])

    def test_workcell_schemas_are_versioned(self) -> None:
        for name in (
            "model-call-evidence.schema.json",
            "evaluation-catalog.schema.json",
            "evaluation-receipt.schema.json",
            "evaluation-checkpoint.schema.json",
        ):
            schema = json.loads((ROOT / "factory" / "schema" / name).read_text())
            self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])
            self.assertRegex(schema["$id"], r"-1\.[01]\.json$")

    def test_factory_ui_projects_intelligence_without_becoming_authority(self) -> None:
        html = (ROOT / "knowledge" / "viewer" / "index.html").read_text()
        script = (ROOT / "knowledge" / "viewer" / "app.js").read_text()
        self.assertIn('id="factory-intelligence"', html)
        self.assertIn("renderFactoryIntelligence", script)
        self.assertIn("independently receipted call", script)


if __name__ == "__main__":
    unittest.main()
