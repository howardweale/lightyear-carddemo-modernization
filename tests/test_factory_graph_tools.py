"""CI-only G2 dry runs: scripted responses and synthetic gates, never model spend.

The ephemeral GraphFixture signatures authorize only this fixture projection.
No test output is an operator activation or qualifying production receipt.
"""
import base64
import copy
import gzip
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

from tests.verify_graph_support import GraphFixture, digest, leak_check
from lightyear_factory.agents import ModelAgentSet
from lightyear_factory.context import GraphContextAssembler
from lightyear_factory.contracts import ContractError, WorkOrder, canonical_hash
from lightyear_factory.graph_tools import FactoryGraphSession, graph_policy, graph_summary, encoded
from lightyear_factory.isolation_scan import scan
from lightyear_factory.ledger import RunLedger
from lightyear_factory.orchestrator import FactoryOrchestrator
from lightyear_factory.providers import ScriptedModelProvider
from lightyear_toolkit.graph import GraphTools

CANARIES = {key: "g2-fixture-" + key + "-" + "x" * 64
            for key in ("expected-state", "reference-output", "session-answer")}


def request(tool, **arguments):
    return dict(graph_calls=[dict(tool=tool, arguments_json=json.dumps(arguments))], answer=None)


def answer(value):
    return dict(graph_calls=[], answer=value)


def report(passed):
    return dict(status="passed" if passed else "failed", gates=[dict(
        id="toy", status="passed" if passed else "failed", exit_code=0 if passed else 1,
        timed_out=False, output_sha256="a" * 64, expose_output_to_builder=False)])


class FactoryGraphTests(GraphFixture):
    def setUp(self):
        super().setUp()
        self.manifest = self.build()
        # Create the real public-fixture scan before requesting fixture approval.
        leak_report = leak_check(self.out, digest(self.lane), set(CANARIES.values()),
            self.signer, evaluation_inventory_sha256=canonical_hash(CANARIES))
        self.assertTrue(leak_report["passed"])
        proof, trust = self.approve(self.manifest)
        self.approved = (self.out, proof, trust)
        self.projection = json.loads(gzip.decompress((self.out / "projection.json.gz").read_bytes()))
        self.node = next(n for n in self.projection["nodes"]
                         if n["kind"] == "cobol_field" and len(encoded(n)) < 2500
                         and any(s.get("text") for s in n["source"]))
        self.source = self.root / "source"
        (self.source / "candidate").mkdir(parents=True)
        (self.source / "candidate/toy.txt").write_bytes(b"wrong\n")
        self.read_manifest = {"candidate/toy.txt": hashlib.sha256(b"wrong\n").hexdigest()}

    def order(self, *, budget=4, mode="on-demand", baseline=False):
        metadata = dict(context_schema="1.1", customer_id="carddemo-reference", graph=mode)
        if mode == "on-demand":
            metadata["graph_policy"] = dict(call_budget=budget, response_bytes=32768,
                projection_sha256=self.manifest["projection_sha256"])
        return WorkOrder.from_dict(dict(schema_version="1.0", id="g2-fixture", title="G2 fixture",
            goal="Repair public toy", scope=dict(allowed_paths=["candidate"], graph_node_ids=[]),
            acceptance=dict(max_attempts=2, baseline_first=baseline,
                gates=[dict(id="toy", command=["python", "-c", "pass"])]),
            policy=dict(max_context_bytes=80000, max_model_calls=12, max_model_tokens=1000000,
                        max_model_input_bytes=1000000, max_model_output_bytes=1000000,
                        max_model_cost_usd=0, max_elapsed_seconds=120),
            metadata=metadata))

    def plan(self, node=None):
        node = node or self.node
        capsules = ["projection:" + canonical_hash(dict(node=node["id"], source=s))
                    for s in node.get("source", []) if "text" in s]
        return dict(summary="Use public graph evidence", tasks=[dict(id="toy", objective="Repair toy",
            paths=["candidate"], graph_node_ids=[node["id"]], evidence_capsule_ids=capsules)], risks=[])

    @staticmethod
    def edit():
        return dict(summary="Toy edit", edits=[dict(path="candidate/toy.txt", find="wrong",
                    replace="fixed", rationale="Fixture")], blocked_reason=None)

    def controller(self, order, outputs, *, prepare=None, gates=None):
        provider = ScriptedModelProvider(outputs)
        agents = ModelAgentSet(provider)
        controller = FactoryOrchestrator(self.source, self.root / "runs", agents,
            approved_projection=self.approved, workspace_read_manifest=self.read_manifest,
            prepare_workspace=prepare)
        self.enterContext(patch.object(controller, "_run_gates", side_effect=gates or [report(True)]))
        return controller, agents, provider

    def session(self, order=None):
        order = order or self.order()
        context = GraphContextAssembler(None, None, approved_projection=self.approved).assemble(order, self.source)
        directory = self.root / ("session-" + str(len(tuple(self.root.glob("session-*")))))
        ledger = RunLedger(directory / "events.jsonl")
        def scanner(name, raw):
            result = scan([(name, raw)], CANARIES, ())
            ledger.append("RUNNING", "model_isolation_scan_passed", result)
        session = FactoryGraphSession(order, "fixture", ledger, context,
            self.approved, self.read_manifest, scanner, self.source)
        return session, ledger, context

    def test_planner_queries_and_cites_returned_node_in_real_controller(self):
        order = self.order()
        controller, agents, provider = self.controller(order, [
            request("graph_node", node_id=self.node["id"], include_source=True),
            answer(self.plan()), self.edit()])
        receipt = controller.run(order, "planner")
        self.assertEqual("passed", receipt["status"])
        self.assertEqual(1, receipt["graph"]["tool_calls"])
        self.assertFalse(receipt["execution_security"]["production_ready"])
        self.assertNotIn("factory_build_receipt", receipt)
        self.assertEqual("builder", provider.requests[-1]["role"])
        self.assertNotIn("graph_calls", provider.requests[-1]["schema"]["properties"])
        self.assertEqual(self.node["id"], provider.requests[1]["payload"]["graph_result"]["result"]["items"][0]["id"])
        self.assertIn(self.node["id"], [n["id"] for n in agents.implementer_context["nodes"]])
        ledger = RunLedger(self.root / "runs/planner/events.jsonl")
        self.assertEqual(receipt["graph"], graph_summary(order, ledger, "planner"))
        plans = list((self.root / "runs/planner/artifacts").glob("*-plan.json"))
        self.assertEqual(graph_policy(order), json.loads(plans[0].read_text())["content"]["graph"])
        self.assertFalse((self.root / "runs/planner/workspace/graph-queries.jsonl").exists())

    def test_analyst_references_identify_public_divergence_with_shared_budget(self):
        field = next(n for n in self.projection["nodes"] if n["kind"] == "cobol_field" and any(
            n["name"] in s.get("text", "") for candidate in self.projection["nodes"]
            if candidate["kind"] in ("cobol_paragraph", "cobol_program") for s in candidate["source"]))
        order = self.order(baseline=True)
        controller, agents, provider = self.controller(order, [
            request("graph_node", node_id=self.node["id"]),
            answer(self.plan()),
            request("graph_references", node_id=field["id"]),
            answer(dict(summary="Inspect observed references", failure_codes=["toy"],
                        builder_guidance="Repair the public reference-linked calculation", risk="low")),
            self.edit()], gates=[report(False), report(True)])
        receipt = controller.run(order, "analyst")
        self.assertEqual("passed", receipt["status"])
        self.assertEqual(2, receipt["graph"]["tool_calls"])
        result = provider.requests[3]["payload"]["graph_result"]["result"]
        self.assertTrue(result["items"])
        self.assertTrue(any(row.get("line_ranges") for row in result["items"]))
        calls = [e["payload"] for e in RunLedger(self.root / "runs/analyst/events.jsonl").events
                 if e["kind"] == "graph_tool_finished"]
        self.assertEqual(["planner", "failure_analyst"], [r["role"] for r in calls])
        self.assertEqual([0, 0], [r["attempt"] for r in calls])
        self.assertNotIn("factory_build_receipt", receipt)

    def test_budget_overrun_stops_before_next_tool_or_builder(self):
        order = self.order(budget=1)
        controller, agents, provider = self.controller(order, [
            request("graph_node", node_id=self.node["id"]),
            request("graph_node", node_id=self.node["id"]), self.edit()])
        with self.assertRaisesRegex(ContractError, "factory-isolation-run-refused"):
            controller.run(order, "budget")
        self.assertEqual(1, agents.graph_session.count)
        self.assertEqual(["planner", "planner"], [r["role"] for r in provider.requests])
        receipt = json.loads((self.root / "runs/budget/receipt.json").read_text())
        self.assertFalse(receipt["qualifies_for_factory_receipt"])
        self.assertEqual("blocked", receipt["status"])

    def test_encoded_canary_in_complete_result_fails_isolation_breach(self):
        session, ledger, context = self.session()
        token = CANARIES["session-answer"]
        session.dispatch["graph_node"] = lambda **kw: dict(items=[], extension=base64.b64encode(token.encode()).decode())
        with self.assertRaisesRegex(ContractError, "isolation-breach"):
            session.call("planner", 0, "graph_node", dict(node_id=self.node["id"]))
        self.assertEqual("refused", ledger.events[-1]["payload"]["status"])
        self.assertNotIn(token, ledger.path.read_text())
        self.assertNotIn(base64.b64encode(token.encode()).decode(), ledger.path.read_text())
        self.assertEqual([], context["nodes"])
        with self.assertRaisesRegex(ContractError, "factory-graph-tool-forbidden"):
            session.call("planner", 0, "graph_node", dict(node_id=self.node["id"]))

    def test_four_private_categories_and_builder_are_refused(self):
        for forbidden in ("expected states", "reference traces", "session answers", "prior receipts"):
            with self.subTest(forbidden=forbidden):
                session, ledger, _ = self.session()
                with self.assertRaisesRegex(ContractError, "factory-graph-arguments-refused"):
                    session.call("planner", 0, "graph_search", dict(query=forbidden))
                self.assertNotIn(forbidden, ledger.path.read_text())
        for forbidden in ("expected states", "reference traces", "session answers", "prior receipts"):
            with self.subTest(result_category=forbidden):
                session, ledger, _ = self.session()
                session.dispatch["graph_node"] = lambda **kw: dict(items=[], extension=forbidden)
                with self.assertRaisesRegex(ContractError, "factory-graph-private-material"):
                    session.call("failure_analyst", 1, "graph_node", dict(node_id=self.node["id"]))
                self.assertNotIn(forbidden, ledger.path.read_text())
        session, ledger, _ = self.session()
        for role, tool in (("builder", "graph_node"), ("planner", "explain_divergence"),
                           ("planner", "get_verdict"), ("planner", "references")):
            with self.assertRaisesRegex(ContractError, "factory-graph-tool-forbidden"):
                session.call(role, 0, tool, dict(node_id=self.node["id"]))
        self.assertEqual(0, session.count)

    def test_packed_fallback_has_no_tool_envelope_or_queries(self):
        order = self.order(mode="packed")
        plain = dict(summary="Packed plan", tasks=[dict(id="toy", objective="Toy", paths=["candidate"],
                     graph_node_ids=[], evidence_capsule_ids=[])], risks=[])
        controller, agents, provider = self.controller(order, [plain, self.edit()])
        receipt = controller.run(order, "packed")
        self.assertEqual("packed", receipt["graph"]["mode"])
        self.assertEqual(0, receipt["graph"]["tool_calls"])
        self.assertIsNone(agents.graph_session)
        self.assertNotIn("graph_calls", provider.requests[0]["schema"]["properties"])
        self.assertNotIn("factory_build_receipt", receipt)

    def test_projection_binding_cap_and_ledger_tamper_fail_closed(self):
        order = self.order()
        order.metadata["graph_policy"]["projection_sha256"] = "0" * 64
        with self.assertRaisesRegex(ContractError, "factory-graph-projection-binding"):
            self.session(order)
        session, ledger, _ = self.session()
        session.dispatch["graph_node"] = lambda **kw: dict(items=[], padding="p" * 32769)
        with self.assertRaisesRegex(ContractError, "factory-graph-response-cap"):
            session.call("planner", 0, "graph_node", dict(node_id=self.node["id"]))
        ledger.events[-1]["payload"]["status"] = "passed"
        with self.assertRaisesRegex(ContractError, "factory-graph-ledger-changed"):
            graph_summary(session.order, ledger, "fixture")

    def test_network_or_missing_controller_boundary_cannot_enable_tools(self):
        order = self.order()
        for key, value in (("call_budget", True), ("response_bytes", 32769)):
            changed = copy.deepcopy(order)
            changed.metadata["graph_policy"][key] = value
            with self.assertRaisesRegex(ContractError, "factory-graph-policy"):
                graph_policy(changed)
        payload = order.to_dict()
        payload["policy"]["allow_network"] = True
        with self.assertRaisesRegex(ContractError, "factory-graph-policy"):
            graph_policy(WorkOrder.from_dict(payload))
        agents = ModelAgentSet(ScriptedModelProvider([]))
        with self.assertRaisesRegex(ContractError, "factory-graph-controller-binding-required"):
            agents.plan(order, GraphContextAssembler(None, None, approved_projection=self.approved).assemble(order, self.source))
