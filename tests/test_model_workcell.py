from __future__ import annotations

import json
from io import BytesIO
import tempfile
import types
import unittest
from datetime import datetime, timedelta, timezone
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
from lightyear_factory.quality import (
    QualityPolicy,
    compare_evaluations,
    quality_scorecard,
    sign_sealed_catalog,
    verify_sealed_catalog,
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
from lightyear_factory.store import EvaluationStore, FactoryRunStore
from lightyear_factory.workspace import IsolatedWorkspace


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "factory" / "evals" / "carddemo-v0.12-public.json"
TARGET = ROOT / "factory" / "benchmarks" / "intcalc_candidate.py"
EVIDENCE_ID = "capsule:00499794e29839da11701d13"


def planner() -> dict:
    return {
        "summary": "Use graph evidence to restore the approved file.",
        "tasks": [
            {
                "id": "repair",
                "objective": "Restore source-faithful behavior",
                "paths": ["factory/benchmarks/intcalc_candidate.py"],
                "graph_node_ids": ["workload:carddemo-intcalc"],
                "evidence_capsule_ids": [EVIDENCE_ID],
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

    def test_role_contexts_use_catalog_then_plan_selected_source(self) -> None:
        order = benchmark_work_order("rounding-mode")
        context = GraphContextAssembler(
            ROOT / "knowledge" / "graph.snapshot.json.gz",
            ROOT / "knowledge" / "evidence" / "source.pack.json.gz",
        ).assemble(order, ROOT)
        planner_context = GraphContextAssembler.planner_context(context)
        selected = [item["capsule_id"] for item in context["source_excerpts"][:2]]
        builder_context = GraphContextAssembler.builder_context(
            context, selected, ["workload:carddemo-intcalc"]
        )
        self.assertNotIn("source_excerpts", planner_context)
        self.assertNotIn("content", json.dumps(planner_context["allowed_files"]))
        self.assertEqual(selected, builder_context["selected_evidence_capsule_ids"])
        self.assertEqual(2, len(builder_context["source_excerpts"]))
        self.assertLess(
            planner_context["statistics"]["context_bytes"],
            context["statistics"]["context_bytes"] * 0.6,
        )
        self.assertLess(
            builder_context["statistics"]["context_bytes"],
            context["statistics"]["context_bytes"] * 0.6,
        )
        with self.assertRaisesRegex(ContractError, "unknown evidence capsule"):
            GraphContextAssembler.builder_context(
                context, ["capsule:not-approved"], ["workload:carddemo-intcalc"]
            )

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
            transcript = FactoryRunStore(root / "runs").transcript(
                "scripted-model-repair"
            )
        self.assertEqual("passed", receipt["status"])
        self.assertEqual("model-backed", receipt["intelligence"]["mode"])
        self.assertEqual(3, receipt["intelligence"]["calls"])
        self.assertEqual(3, len(model_evidence))
        self.assertEqual(1, len(change_set))
        self.assertEqual(0, receipt["intelligence"]["estimated_cost_usd"])
        builder_request = next(item for item in provider.requests if item["role"] == "builder")
        self.assertTrue(builder_request["payload"]["graph_context"]["source_excerpts"])
        self.assertNotIn("allowed_files", builder_request["payload"]["graph_context"])
        planner_request = next(item for item in provider.requests if item["role"] == "planner")
        self.assertIn("evidence_catalog", planner_request["payload"]["planner_context"])
        self.assertNotIn("source_excerpts", planner_request["payload"]["planner_context"])
        self.assertFalse(transcript["direct_agent_chat"])
        self.assertTrue(
            any(item["artifact_type"] == "plan" for item in transcript["messages"])
        )
        self.assertTrue(
            any(
                item["visibility"] == "verifier_private"
                and item["content"] == {"redacted": True}
                for item in transcript["messages"]
            )
        )

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
            token_preflight=False,
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

        provider = OpenAIResponsesProvider(
            "secret", opener=opener, sleep=lambda _: None, token_preflight=False
        )
        with self.assertRaises(ProviderError) as raised:
            provider.complete("planner", "Return JSON.", {}, {"type": "object"})
        self.assertEqual(1, calls)
        self.assertFalse(raised.exception.retryable)
        self.assertNotIn("secret", json.dumps(raised.exception.safe_dict()))

    def test_openai_provider_preflights_exact_tokens_and_records_evidence(self) -> None:
        requests: list[str] = []
        schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["ok"],
            "properties": {"ok": {"type": "boolean"}},
        }

        class Response:
            headers = {"x-ratelimit-remaining-tokens": "499000"}

            def __init__(self, payload):
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def read(self):
                return json.dumps(self.payload).encode()

        def opener(request, timeout):
            requests.append(request.full_url)
            if request.full_url.endswith("/input_tokens"):
                body = json.loads(request.data)
                self.assertIn("instructions", body)
                self.assertIn("text", body)
                return Response({"input_tokens": 321})
            return Response({
                "status": "completed",
                "model": "gpt-test",
                "usage": {"input_tokens": 321, "output_tokens": 2},
                "output": [{"content": [{
                    "type": "output_text", "text": json.dumps({"ok": True})
                }]}],
            })

        provider = OpenAIResponsesProvider(
            "secret", "gpt-test", opener=opener, max_input_tokens_per_call=1_000
        )
        result = provider.complete("planner", "Return JSON.", {}, schema)
        self.assertEqual(2, len(requests))
        self.assertEqual(321, result.evidence["input_tokens_preflight"])
        self.assertEqual(1_000, result.evidence["max_input_tokens_per_call"])
        self.assertTrue(result.evidence["input_token_preflight"])

    def test_openai_provider_blocks_over_budget_before_generation(self) -> None:
        calls = 0

        class Response:
            headers = {}

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def read(self):
                return json.dumps({"input_tokens": 1_001}).encode()

        def opener(request, timeout):
            nonlocal calls
            calls += 1
            return Response()

        provider = OpenAIResponsesProvider(
            "secret", opener=opener, max_input_tokens_per_call=1_000
        )
        with self.assertRaises(ProviderError) as raised:
            provider.complete("planner", "Return JSON.", {}, {"type": "object"})
        self.assertEqual("input_token_budget_exceeded", raised.exception.code)
        self.assertEqual(1, calls)

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

    def test_sealed_catalog_signature_tamper_expiry_and_wrong_key_fail_closed(self) -> None:
        catalog = load_evaluation_catalog(CATALOG)
        catalog["id"] = "externally-controlled-holdout"
        catalog["evaluation_class"] = "sealed-holdout"
        key = b"a" * 32
        issued = datetime(2026, 8, 14, tzinfo=timezone.utc)
        envelope = sign_sealed_catalog(
            catalog, key, issuer="independent-evaluator", key_id="holdout-1",
            issued_at=issued, ttl_seconds=3600,
        )
        verified, binding = verify_sealed_catalog(
            envelope, {"holdout-1": key}, now=issued + timedelta(minutes=1)
        )
        self.assertEqual(catalog["id"], verified["id"])
        self.assertTrue(binding["signature_valid"])
        tampered = json.loads(json.dumps(envelope))
        tampered["catalog"]["id"] = "changed"
        with self.assertRaisesRegex(ContractError, "identity"):
            verify_sealed_catalog(tampered, {"holdout-1": key}, now=issued)
        with self.assertRaisesRegex(ContractError, "trusted"):
            verify_sealed_catalog(envelope, {"other": key}, now=issued)
        with self.assertRaisesRegex(ContractError, "expired"):
            verify_sealed_catalog(
                envelope, {"holdout-1": key}, now=issued + timedelta(hours=2)
            )

    def test_plain_sealed_catalog_is_rejected_without_verified_envelope(self) -> None:
        catalog = load_evaluation_catalog(CATALOG)
        catalog["id"] = "unsigned-holdout"
        catalog["evaluation_class"] = "sealed-holdout"
        catalog["cases"] = [catalog["cases"][0]]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "catalog.json"
            path.write_text(json.dumps(catalog), encoding="utf-8")
            with self.assertRaisesRegex(ContractError, "verified envelope"):
                run_model_evaluation(
                    ROOT, root / "output", path,
                    lambda _: ModelAgentSet(ScriptedModelProvider([planner()])),
                )

    def test_clean_holdout_case_passes_unchanged_and_receipt_hides_case_identity(self) -> None:
        catalog = {
            "schema_version": "1.0",
            "id": "secret-holdout-name",
            "evaluation_class": "sealed-holdout",
            "description": "private",
            "minimum_repair_rate": 1.0,
            "target_path": "factory/benchmarks/intcalc_candidate.py",
            "cases": [{
                "id": "secret-clean-case",
                "category": "secret-category",
                "expectation": "accept-unchanged",
                "forbidden_public_markers": ["secret-clean-case", "secret-category"],
            }],
        }
        key = b"b" * 32
        envelope = sign_sealed_catalog(
            catalog, key, issuer="independent-evaluator", key_id="holdout-2"
        )
        verified, binding = verify_sealed_catalog(envelope, {"holdout-2": key})
        permissive = QualityPolicy(
            minimum_cases=1, minimum_categories=1, minimum_clean_cases=1,
            minimum_evidence_scored_cases=0, minimum_baseline_rejection_rate=0,
            minimum_repair_rate=0, minimum_correct_no_change_rate=1,
            minimum_first_attempt_repair_rate=0, minimum_evidence_precision=0,
        )
        with tempfile.TemporaryDirectory() as directory:
            receipt = run_model_evaluation(
                ROOT, Path(directory) / "evaluation", Path("unused.json"),
                lambda _: ModelAgentSet(ScriptedModelProvider([planner()])),
                catalog_override=verified, sealed_binding=binding,
                quality_policy=permissive, policy=EvaluationPolicy(pace_seconds=0),
            )
        public = json.dumps(receipt)
        self.assertEqual("passed", receipt["status"])
        self.assertEqual(1, receipt["correct_no_changes"])
        self.assertEqual(0, receipt["false_acceptances"])
        self.assertEqual("qualified", receipt["quality_gate"]["status"])
        self.assertNotIn("secret-clean-case", public)
        self.assertNotIn("secret-category", public)

    def test_quality_gate_blocks_public_calibration_and_comparison_is_safety_first(self) -> None:
        result = {
            "expectation": "reject-and-repair", "baseline_rejected": True,
            "autonomously_repaired": True, "correct_no_change": False,
            "false_acceptance": False, "attempts": 1, "input_tokens": 100,
            "estimated_cost_usd": 0.01, "private_evidence_leaks": 0,
            "unauthorized_edit_attempts": 0,
            "evidence_selection": {"available": True, "precision": 1.0},
        }
        policy = QualityPolicy(
            minimum_cases=1, minimum_categories=1, minimum_clean_cases=0,
            minimum_evidence_scored_cases=1, minimum_baseline_rejection_rate=1,
            minimum_repair_rate=1, minimum_correct_no_change_rate=0,
            minimum_first_attempt_repair_rate=1, minimum_evidence_precision=1,
        )
        gate = quality_scorecard(
            "public-calibration", {"layout": 1}, [result], policy, None
        )
        self.assertEqual("blocked", gate["status"])
        self.assertIn("sealed_evidence", gate["gaps"])
        safe = {
            "evaluation_id": "safe", "evaluation_class": "sealed-holdout",
            "status": "passed", "content_sha256": "a" * 64,
            "quality_gate": {"status": "qualified", "metrics": {
                "repair_rate": 0.8, "false_acceptances": 0,
                "correct_no_change_rate": 1.0, "evidence_selection_precision": 0.8,
                "average_input_tokens": 50,
            }}, "totals": {"estimated_cost_usd": 1.0},
        }
        unsafe = json.loads(json.dumps(safe))
        unsafe["evaluation_id"] = "unsafe"
        unsafe["content_sha256"] = "b" * 64
        unsafe["quality_gate"]["metrics"]["repair_rate"] = 1.0
        unsafe["quality_gate"]["metrics"]["false_acceptances"] = 1
        comparison = compare_evaluations([unsafe, safe])
        self.assertEqual("a" * 64, comparison["recommended_receipt_sha256"])

    def test_evaluation_store_projects_quality_receipts(self) -> None:
        receipt = {
            "evaluation_id": "sealed:opaque", "evaluation_class": "sealed-holdout",
            "status": "passed", "cases": 20, "repair_rate": 0.9,
            "correct_no_change_rate": 1.0, "false_acceptances": 0,
            "content_sha256": "c" * 64,
            "quality_gate": {"status": "qualified", "metrics": {
                "repair_rate": 0.9, "correct_no_change_rate": 1.0,
                "false_acceptances": 0, "average_input_tokens": 42000,
            }},
            "totals": {"estimated_cost_usd": 2.5},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run" / "evaluation.receipt.json"
            path.parent.mkdir()
            path.write_text(json.dumps(receipt), encoding="utf-8")
            store = EvaluationStore(Path(directory))
            rows = store.list_evaluations()
            detail = store.evaluation(rows[0]["evaluation_key"])
        self.assertEqual("qualified", rows[0]["quality_status"])
        self.assertEqual("sealed:opaque", detail["evaluation_id"])

    def test_workcell_schemas_are_versioned(self) -> None:
        for name in (
            "model-call-evidence.schema.json",
            "evaluation-catalog.schema.json",
            "evaluation-receipt.schema.json",
            "evaluation-checkpoint.schema.json",
            "sealed-evaluation-envelope.schema.json",
            "factory-quality-policy.schema.json",
            "factory-quality-gate.schema.json",
            "evaluation-comparison.schema.json",
            "agent-exchange.schema.json",
        ):
            schema = json.loads((ROOT / "factory" / "schema" / name).read_text())
            self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])
            self.assertRegex(schema["$id"], r"-(?:1\.[01]|2\.0)\.json$")

    def test_factory_ui_projects_intelligence_without_becoming_authority(self) -> None:
        html = (ROOT / "knowledge" / "viewer" / "index.html").read_text()
        script = (ROOT / "knowledge" / "viewer" / "app.js").read_text()
        self.assertIn('id="factory-intelligence"', html)
        self.assertIn('id="evaluation-tab"', html)
        self.assertIn('id="evaluation-checks"', html)
        self.assertIn("renderFactoryIntelligence", script)
        self.assertIn("loadEvaluations", script)
        self.assertIn("independently receipted call", script)


if __name__ == "__main__":
    unittest.main()
