import copy
import io
import json
import unittest
from dataclasses import replace
from datetime import timedelta
from unittest.mock import Mock
import test_graph_memory as fixtures
from lightyear_control_tower.decisions import digest
from lightyear_factory.benchmark import benchmark_work_order
from lightyear_factory.contracts import canonical_hash, ContractError
from lightyear_factory.providers import (
    ProviderError,
    ProviderResult,
)
from lightyear_factory.budgeted_providers import (
    AccountedModelProvider as BoundedModelProvider,
)
from lightyear_factory.additional_providers import (
    AnthropicMessagesProvider,
    GeminiProvider,
)
from lightyear_factory.routing import TaskRouter
from lightyear_factory.evaluation_matrix import aggregate, run_matrix
from lightyear_factory.parallel_queue import InMemoryWorkQueue
from lightyear_factory.agents import ModelAgentSet

SCHEMA = dict(
    type="object",
    properties={"result": dict(type="string")},
    required=["result"],
    additionalProperties=False,
)


def hashed(body):
    return {**body, "content_sha256": canonical_hash(body)}


class ProviderTests(unittest.TestCase):
    def test_configuration_refuses_nonfinite_openai_prices_without_call(self):
        from lightyear_factory.model_config import configured_models

        with self.assertRaises(ValueError):
            configured_models(
                dict(
                    models={
                        "default": dict(
                            provider="openai",
                            model="configured",
                            input_usd_per_million=float("nan"),
                            output_usd_per_million=1,
                            max_output_tokens=10,
                        )
                    }
                )
            )

    def provider(self, cls, body):
        opener = Mock(side_effect=lambda *a, **k: io.BytesIO(json.dumps(body).encode()))
        return cls(
            "configured-model",
            api_key="synthetic-token",
            input_usd_per_million=1,
            output_usd_per_million=2,
            max_output_tokens=10,
            opener=opener,
        )

    def fixture(self, cls):
        return (
            dict(
                stop_reason="end_turn",
                content=[dict(type="text", text='{"result":"ok"}')],
                usage=dict(input_tokens=10, output_tokens=5, cache_read_input_tokens=2),
            )
            if cls == AnthropicMessagesProvider
            else dict(
                candidates=[
                    dict(
                        finishReason="STOP",
                        content=dict(parts=[dict(text='{"result":"ok"}')]),
                    )
                ],
                usageMetadata=dict(
                    promptTokenCount=10,
                    candidatesTokenCount=5,
                    cachedContentTokenCount=2,
                ),
            )
        )

    def test_provider_evidence_credentials_and_call_limit(self):
        for cls in (AnthropicMessagesProvider, GeminiProvider):
            p = self.provider(cls, self.fixture(cls))
            order = replace(benchmark_work_order("rounding-mode"), max_model_calls=1)
            b = BoundedModelProvider(p, order)
            r = b.complete("planner", "Instruction", {}, SCHEMA)
            self.assertEqual(r.content, {"result": "ok"})
            self.assertEqual(r.evidence["cached_input_tokens"], 2)
            self.assertNotIn("synthetic-token", json.dumps(r.evidence))
            self.assertEqual(
                r.evidence["content_sha256"],
                canonical_hash(r.evidence, {"content_sha256"}),
            )
            with self.assertRaises(ContractError):
                b.complete("planner", "Instruction", {}, SCHEMA)
            self.assertEqual(p.opener.call_count, 1)

    def test_byte_token_and_cost_admission_limits_before_call(self):
        for limit in (
            dict(max_model_input_bytes=1),
            dict(max_model_tokens=1),
            dict(max_model_cost_usd=0.000001),
        ):
            p = self.provider(GeminiProvider, self.fixture(GeminiProvider))
            b = BoundedModelProvider(
                p, replace(benchmark_work_order("rounding-mode"), **limit)
            )
            with self.assertRaises(ContractError):
                b.complete("builder", "Instruction", {}, SCHEMA)
            p.opener.assert_not_called()

    def test_bad_result_is_not_provider_error_and_is_charged(self):
        p = self.provider(
            AnthropicMessagesProvider,
            {**self.fixture(AnthropicMessagesProvider), "stop_reason": "max_tokens"},
        )
        b = BoundedModelProvider(p, benchmark_work_order("rounding-mode"))
        with self.assertRaises(ContractError) as e:
            b.complete("builder", "Instruction", {}, SCHEMA)
        self.assertNotIsInstance(e.exception, ProviderError)
        self.assertEqual(len(b.calls), 1)
        self.assertGreater(b.estimated_cost_usd, 0)

    def test_output_budget_failure_retains_call(self):
        p = self.provider(GeminiProvider, self.fixture(GeminiProvider))
        b = BoundedModelProvider(
            p, replace(benchmark_work_order("rounding-mode"), max_model_output_bytes=1)
        )
        with self.assertRaises(ContractError):
            b.complete("builder", "Instruction", {}, SCHEMA)
        self.assertEqual(len(b.calls), 1)


class FakeProvider:
    provider_id = "offline-fake"
    manage_failure_budget = True
    input_usd_per_million = 1
    output_usd_per_million = 1
    max_output_tokens = 10

    def __init__(self, model, error=None):
        self.model = model
        self.error = error
        self.calls = 0

    def complete(self, role, instruction, payload, schema):
        self.calls += 1
        if self.error:
            raise self.error
        return ProviderResult(
            {"result": "bad-business-result"},
            hashed(
                dict(
                    model=self.model,
                    input_tokens=10,
                    output_tokens=5,
                    estimated_cost_usd=0.000015,
                    cost_estimate_available=True,
                )
            ),
        )


class RoutingTests(unittest.TestCase):
    setUp = fixtures.MemoryTests.setUp
    proof = fixtures.MemoryTests.proof

    def router(self, providers, *, approved=True, clock=None):
        matrix = dict(
            schema="factory-evaluation-matrix/1",
            false_acceptances=0,
            cells=[dict(model=m, task_type="plan") for m in providers],
        )
        matrix["content_sha256"] = digest(matrix)
        policy = dict(
            schema="factory-routing-policy/1",
            routes={
                "plan": dict(
                    primary="primary",
                    fallback="fallback",
                    matrix_receipts=[matrix["content_sha256"]],
                )
            },
        )
        proof = (
            self.proof(
                "model-routing-policy",
                dict(policy=policy, matrix_receipt=matrix),
                "approved",
            )
            if approved
            else None
        )
        trust = dict(
            tower_key=self.console.public_key.decode(),
            scope="graph-memory",
            trusted_head=proof["journal"]["journal_head_sha256"] if proof else None,
        )
        return TaskRouter(
            providers,
            "default",
            policy=policy,
            matrix=matrix,
            proof=proof,
            trust=trust,
            now=clock,
        )

    def test_unapproved_expired_default_only(self):
        for approved, clock in (
            (False, None),
            (True, lambda: self.now + timedelta(days=11)),
        ):
            providers = {m: FakeProvider(m) for m in ("default", "primary", "fallback")}
            b = self.router(providers, approved=approved, clock=clock).bind_order(
                benchmark_work_order("rounding-mode")
            )
            b.complete("planner", "", {}, SCHEMA)
            self.assertEqual(providers["default"].calls, 1)
            self.assertIsNone(b.summary()["routing"][0]["policy_sha256"])

    def test_provider_error_only_fallback_and_shared_budget(self):
        providers = {m: FakeProvider(m) for m in ("default", "primary", "fallback")}
        providers["primary"].error = ProviderError("planner", "network")
        b = self.router(providers).bind_order(benchmark_work_order("rounding-mode"))
        b.complete("planner", "", {}, SCHEMA)
        self.assertEqual(len(b.calls), 2)
        self.assertEqual(
            [r["model"] for r in b.summary()["routing"]], ["primary", "fallback"]
        )
        self.assertEqual(b.calls[0]["status"], "failed")
        providers = {m: FakeProvider(m) for m in ("default", "primary", "fallback")}
        b = self.router(providers).bind_order(benchmark_work_order("rounding-mode"))
        b.complete("planner", "", {}, SCHEMA)
        self.assertEqual(
            providers["fallback"].calls, 0
        )  # Bad business result is left to judge.

    def test_agent_retains_failed_primary_and_fallback_records(self):
        providers = {m: FakeProvider(m) for m in ("default", "primary", "fallback")}
        providers["primary"].error = ProviderError("planner", "network")
        agents = ModelAgentSet(self.router(providers))
        agents._call(benchmark_work_order("rounding-mode"), "planner", "", {}, SCHEMA)
        self.assertEqual(len(agents.drain_evidence()), 2)
        self.assertEqual(agents.intelligence_summary()["calls"], 2)

    def test_same_budget_blocks_fallback_and_campaigns_refused(self):
        providers = {m: FakeProvider(m) for m in ("default", "primary", "fallback")}
        providers["primary"].error = ProviderError("planner", "network")
        router = self.router(providers)
        b = router.bind_order(
            replace(benchmark_work_order("rounding-mode"), max_model_calls=1)
        )
        with self.assertRaises(ContractError):
            b.complete("planner", "", {}, SCHEMA)
        self.assertEqual(providers["fallback"].calls, 0)
        with self.assertRaises(ContractError):
            router.bind_order(
                replace(
                    benchmark_work_order("rounding-mode"),
                    metadata={"campaign_id": "B06"},
                )
            )

    def test_matrix_missing_call_catalog_mismatch_and_hashes(self):
        call = hashed(
            dict(
                model="primary",
                input_tokens=10,
                output_tokens=5,
                estimated_cost_usd=0.01,
            )
        )
        run = hashed(
            dict(
                status="passed",
                started_at="2026-10-06T00:00:00+00:00",
                completed_at="2026-10-06T00:00:01+00:00",
                intelligence=dict(
                    calls=1, call_evidence_sha256=[call["content_sha256"]]
                ),
            )
        )
        result = dict(
            receipt_sha256=run["content_sha256"],
            status="passed",
            false_acceptance=False,
            first_attempt_repair=True,
        )
        evaluation = hashed(
            dict(
                catalog_sha256="a" * 64,
                evaluation_class="public-calibration",
                workload_id="INTCALC",
                results=[result],
                false_acceptances=0,
                totals=dict(input_tokens=10, output_tokens=5, estimated_cost_usd=0.01),
            )
        )
        plan = dict(
            cells=[
                dict(
                    catalog_sha256="a" * 64,
                    evaluation_class="public-calibration",
                    workload="INTCALC",
                    model="primary",
                    task_type="implement",
                )
            ]
        )
        cell = dict(evaluation=evaluation, runs=[run], model_calls=[call])
        self.assertEqual(aggregate(plan, [cell])["cells"][0]["pass_rate"], 1)
        self.assertEqual(aggregate(plan, [cell])["cells"][0]["wall_time_ms"], 1000)
        with self.assertRaises(ContractError):
            aggregate(plan, [{**cell, "model_calls": []}])
        changed = copy.deepcopy(plan)
        changed["cells"][0]["catalog_sha256"] = "b" * 64
        with self.assertRaises(ContractError):
            aggregate(changed, [cell])


class QueueTests(unittest.TestCase):
    def test_capacity_conflicts_idempotency_and_fencing(self):
        graph = dict(
            nodes=[dict(id="a"), dict(id="b"), dict(id="c")],
            edges=[dict(source="a", target="b")],
        )
        q = InMemoryWorkQueue(graph, 2)
        for name in ("a", "b", "c"):
            q.submit(
                replace(
                    benchmark_work_order("rounding-mode"),
                    order_id=name,
                    graph_node_ids=(name,),
                    allowed_paths=(name + ".py",),
                )
            )
        a = q.claim("one", "request-1", 0, 10)
        self.assertEqual(a, q.claim("one", "request-1", 1, 10))
        c = q.claim("two", "request-2", 0, 10)
        self.assertEqual(c.order_id, "c")
        self.assertIsNone(q.claim("three", "request-3", 0, 10))
        renewed = q.heartbeat(a, 1, 10)
        with self.assertRaises(ValueError):
            q.complete(a, 2, "a" * 64)
        q.complete(renewed, 2, "a" * 64)
        q.complete(renewed, 2, "a" * 64)
        self.assertEqual(q.claim("three", "request-3", 2, 10).order_id, "b")
        with self.assertRaises(ValueError):
            q.heartbeat(c, 11, 10)
