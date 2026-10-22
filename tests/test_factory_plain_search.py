"""Synthetic CI-only retrieval boundaries; no paid provider or candidate process."""
import base64
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lightyear_factory.agents import ModelAgentSet
from lightyear_factory.contracts import ContractError, WorkOrder, canonical_hash
from lightyear_factory.graph_tools import graph_policy, graph_summary, encoded
from lightyear_factory.isolation_scan import scan
from lightyear_factory.ledger import RunLedger
from lightyear_factory.orchestrator import FactoryOrchestrator
from lightyear_factory.plain_search import FactoryPlainSession, plain_context
from lightyear_factory.providers import ScriptedModelProvider

CANARIES = {"session-answer": "plain-fixture-secret-" + "x" * 64,
            "expected-state": "plain-fixture-expected-state-" + "x" * 64,
            "reference-output": "plain-fixture-reference-output-" + "x" * 64}


def request(tool, **arguments):
    return dict(graph_calls=[dict(tool=tool, arguments_json=json.dumps(arguments))], answer=None)


def answer(value):
    return dict(graph_calls=[], answer=value)


def gate(passed):
    return dict(status="passed" if passed else "failed", gates=[dict(id="toy",
        status="passed" if passed else "failed", exit_code=0 if passed else 1,
        timed_out=False, output_sha256="a" * 64, expose_output_to_builder=False)])


class PlainSearchTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.source = self.root / "source"
        (self.source / "candidate").mkdir(parents=True)
        self.raw = b"wrong\nRATE = 7\nrate = 8\n"
        (self.source / "candidate/toy.txt").write_bytes(self.raw)
        self.manifest = {"candidate/toy.txt": hashlib.sha256(self.raw).hexdigest()}

    def order(self, budget=8, cap=8192, baseline=False):
        return WorkOrder.from_dict(dict(schema_version="1.0", id="plain-fixture", title="Plain fixture",
            goal="Repair public toy", scope=dict(allowed_paths=["candidate"], graph_node_ids=[]),
            acceptance=dict(max_attempts=2, baseline_first=baseline,
                gates=[dict(id="toy", command=["python", "-c", "pass"])]),
            policy=dict(max_context_bytes=80000, max_model_calls=14, max_model_tokens=1000000,
                max_model_input_bytes=1000000, max_model_output_bytes=1000000,
                max_model_cost_usd=0, max_elapsed_seconds=120),
            metadata=dict(context_schema="1.1", graph="plain-search", graph_policy=dict(
                call_budget=budget, response_bytes=cap, corpus_sha256=canonical_hash(self.manifest)))))

    def session(self, order=None):
        order = order or self.order()
        context = plain_context(order)
        ledger = RunLedger(self.root / ("events-" + str(len(list(self.root.glob("events-*")))) + ".jsonl"))
        def scanner(name, raw):
            ledger.append("RUNNING", "model_isolation_scan_passed", scan([(name, raw)], CANARIES, ()))
        session = FactoryPlainSession(order, "fixture", ledger, context, self.manifest, scanner, self.source)
        return session, ledger, context

    def plan(self, capsule):
        return dict(summary="Use public source", tasks=[dict(id="toy", objective="Repair toy",
            paths=["candidate"], graph_node_ids=[], evidence_capsule_ids=[capsule])], risks=[])

    @staticmethod
    def edit():
        return dict(summary="Toy edit", edits=[dict(path="candidate/toy.txt", find="wrong",
            replace="fixed", rationale="Fixture")], blocked_reason=None)

    def test_literal_search_read_and_snapshot_have_no_graph_hints(self):
        session, ledger, context = self.session()
        result = session.call("planner", 0, "search_code", dict(query="RATE"))
        self.assertEqual([2], [r["line_start"] for r in result["items"]])
        self.assertEqual([], result["items"][0]["supports"])
        (self.source / "candidate/toy.txt").write_text("changed")
        result = session.call("failure_analyst", 1, "read_file",
                              dict(path="candidate/toy.txt", line_start=1, line_end=3))
        self.assertEqual("wrong", result["items"][0]["lines"][0]["text"])
        self.assertEqual([], context["nodes"])
        self.assertEqual([], context["edges"])
        self.assertIsNone(context["semantic_memory"])
        summary = graph_summary(session.order, ledger, "fixture")
        self.assertEqual(2, summary["tool_calls"])
        calls = [e["payload"] for e in ledger.events if e["kind"] == "plain_tool_finished"]
        self.assertEqual(sum(c["result_bytes"] for c in calls), summary["result_bytes"])
        self.assertEqual(hashlib.sha256(encoded(result)).hexdigest(), calls[-1]["result_sha256"])

    def test_controller_planner_and_analyst_share_tools_builder_has_none(self):
        order = self.order(baseline=True)
        capsule = "source:" + canonical_hash(dict(path="candidate/toy.txt",
            sha256=self.manifest["candidate/toy.txt"], start=1, end=1))
        provider = ScriptedModelProvider([
            request("read_file", path="candidate/toy.txt", line_start=1, line_end=1), answer(self.plan(capsule)),
            request("search_code", query="RATE"), answer(dict(summary="Public issue", failure_codes=["toy"],
                builder_guidance="Repair toy", risk="low")), self.edit()])
        agents = ModelAgentSet(provider)
        controller = FactoryOrchestrator(self.source, self.root / "runs", agents,
                                         workspace_read_manifest=self.manifest)
        with patch.object(controller, "_run_gates", side_effect=[gate(False), gate(True)]):
            receipt = controller.run(order, "plain")
        self.assertEqual("passed", receipt["status"])
        self.assertEqual(2, receipt["graph"]["tool_calls"])
        self.assertNotIn("factory_build_receipt", receipt)
        self.assertFalse(receipt["execution_security"]["production_ready"])
        self.assertEqual("builder", provider.requests[-1]["role"])
        self.assertNotIn("graph_calls", provider.requests[-1]["schema"]["properties"])
        builder = provider.requests[-1]["payload"]["graph_context"]
        self.assertEqual([capsule], builder["selected_evidence_capsule_ids"])
        self.assertEqual([], builder["nodes"])
        ledger = RunLedger(self.root / "runs/plain/events.jsonl")
        self.assertEqual(receipt["graph"], graph_summary(order, ledger, "plain"))

    def test_builder_graph_tools_and_budget_overrun_are_refused(self):
        session, ledger, context = self.session(self.order(budget=1))
        for role, tool in (("builder", "read_file"), ("planner", "graph_search"), ("planner", "get_verdict")):
            with self.assertRaisesRegex(ContractError, "factory-plain-tool-forbidden"):
                session.call(role, 0, tool, {})
        self.assertEqual(0, session.count)
        session.call("planner", 0, "search_code", dict(query="RATE"))
        with self.assertRaisesRegex(ContractError, "factory-plain-call-budget"):
            session.call("failure_analyst", 1, "search_code", dict(query="rate"))
        self.assertEqual(1, graph_summary(session.order, ledger, "fixture")["tool_calls"])

    def test_private_arguments_encoded_results_and_large_results_stop_disclosure(self):
        for value in ("expected states", "reference traces", "session answers", "prior receipts"):
            session, ledger, context = self.session()
            with self.assertRaisesRegex(ContractError, "factory-plain-query-refused"):
                session.call("planner", 0, "search_code", dict(query=value))
            self.assertNotIn(value, ledger.path.read_text())
            self.assertEqual([], context["source_excerpts"])
        for value in (base64.b64encode(CANARIES["session-answer"].encode()).decode(), "p" * 8193):
            session, ledger, context = self.session()
            session.dispatch["search_code"] = lambda **kw: dict(items=[], extension=value)
            with self.assertRaisesRegex(ContractError, "factory-plain-query-refused"):
                session.call("planner", 0, "search_code", dict(query="RATE"))
            self.assertNotIn(value, ledger.path.read_text())
            self.assertEqual([], context["source_excerpts"])
            with self.assertRaisesRegex(ContractError, "factory-plain-tool-forbidden"):
                session.call("planner", 0, "search_code", dict(query="RATE"))

    def test_invalid_paths_ranges_unknown_arguments_and_regex_are_not_authorized(self):
        cases = [dict(path=p, line_start=1, line_end=1) for p in
                 ("../secret", "/secret", "C:/secret", "candidate\\toy.txt", "unknown")]
        cases += [dict(path="candidate/toy.txt", line_start=s, line_end=e)
                  for s, e in ((True, 1), (0, 1), (2, 1), (1, 201), (1, 4))]
        for args in cases:
            session, _, _ = self.session()
            with self.assertRaisesRegex(ContractError, "factory-plain-query-refused"):
                session.call("planner", 0, "read_file", args)
        session, _, _ = self.session()
        self.assertEqual([], session.call("planner", 0, "search_code", dict(query="R.*"))["items"])
        with self.assertRaisesRegex(ContractError, "factory-plain-query-refused"):
            session.call("planner", 0, "search_code", dict(query="RATE", mode="regex"))

    def test_manifest_hash_network_binding_and_tampering_fail_closed(self):
        order = self.order()
        order.metadata["graph_policy"]["corpus_sha256"] = "0" * 64
        with self.assertRaisesRegex(ContractError, "factory-plain-corpus-binding"):
            self.session(order)
        for key, value in (("call_budget", True), ("call_budget", 9), ("response_bytes", 8193)):
            order = self.order()
            order.metadata["graph_policy"][key] = value
            with self.assertRaisesRegex(ContractError, "factory-plain-policy"):
                graph_policy(order)
        payload = self.order().to_dict()
        payload["policy"]["allow_network"] = True
        with self.assertRaisesRegex(ContractError, "factory-plain-policy"):
            graph_policy(WorkOrder.from_dict(payload))
        session, ledger, _ = self.session()
        session.call("planner", 0, "search_code", dict(query="RATE"))
        ledger.events[-1]["payload"]["result_bytes"] = 1
        with self.assertRaisesRegex(ContractError, "factory-plain-ledger-changed"):
            graph_summary(session.order, ledger, "fixture")
        (self.source / "candidate/toy.txt").write_bytes(b"different")
        with self.assertRaisesRegex(ContractError, "factory-plain-hash"):
            self.session()

    def test_full_inventory_scan_and_link_refusal(self):
        raw = ("harmless\n" + base64.b64encode(CANARIES["session-answer"].encode()).decode()).encode()
        (self.source / "candidate/toy.txt").write_bytes(raw)
        self.manifest["candidate/toy.txt"] = hashlib.sha256(raw).hexdigest()
        with self.assertRaisesRegex(ContractError, "isolation-breach"):
            self.session()
        path = self.source / "candidate/toy.txt"
        path.unlink()
        target = self.root / "outside.txt"
        target.write_bytes(self.raw)
        try:
            path.symlink_to(target)
        except OSError:
            self.skipTest("Host cannot create symbolic links; Linux boundary CI covers this")
        with self.assertRaisesRegex(ContractError, "factory-plain-path"):
            self.session()

    def test_unbound_agent_and_graph_context_are_refused(self):
        order = self.order()
        with self.assertRaisesRegex(ContractError, "factory-graph-controller-binding-required"):
            ModelAgentSet(ScriptedModelProvider([])).plan(order, plain_context(order))
        context = plain_context(order)
        context["nodes"].append(dict(id="hint"))
        with self.assertRaisesRegex(ContractError, "factory-plain-context-binding"):
            FactoryPlainSession(order, "fixture", RunLedger(self.root / "bound.jsonl"), context,
                                self.manifest, lambda *args: None, self.source)

    def test_controller_overrun_cannot_reach_builder(self):
        order = self.order(budget=1)
        provider = ScriptedModelProvider([request("search_code", query="RATE"),
                                          request("search_code", query="rate"), self.edit()])
        agents = ModelAgentSet(provider)
        controller = FactoryOrchestrator(self.source, self.root / "runs", agents,
                                         workspace_read_manifest=self.manifest)
        with self.assertRaises(ContractError):
            controller.run(order, "overrun")
        self.assertEqual(["planner", "planner"], [r["role"] for r in provider.requests])
        self.assertEqual(1, agents.graph_session.count)
        receipt = json.loads((self.root / "runs/overrun/receipt.json").read_text())
        self.assertEqual("blocked", receipt["status"])
        self.assertFalse(receipt["qualifies_for_factory_receipt"])

    def test_graph_derived_files_outside_the_bound_corpus_are_unreachable(self):
        derived = ("graph/index.json", "graph/summary.txt", "graph/packed-context.json")
        for path in derived:
            target = self.source / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("DERIVED_GRAPH_HINT_ONLY", encoding="utf-8")
        session, _, _ = self.session()
        result = session.call("planner", 0, "search_code", dict(query="DERIVED_GRAPH_HINT_ONLY"))
        self.assertEqual([], result["items"])
        self.assertEqual(set(self.manifest), set(session.corpus))
        for path in derived:
            session, _, _ = self.session()
            with self.assertRaisesRegex(ContractError, "factory-plain-query-refused"):
                session.call("planner", 0, "read_file", dict(path=path, line_start=1, line_end=1))
