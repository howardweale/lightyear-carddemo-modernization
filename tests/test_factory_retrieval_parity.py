"""Three real controller paths, scripted providers, public sources and stub gates.

This is CI compatibility evidence, never a comparison result or spend approval.
"""
import copy
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
from unittest.mock import patch

from tests import test_factory_graph_tools as g2
from tests.verify_graph_support import GraphFixture, ROOT
from tests.test_factory_plain_search import request, answer, gate
from lightyear_factory.agents import ModelAgentSet
from lightyear_factory.contracts import ContractError, WorkOrder, canonical_hash
from lightyear_factory.graph_tools import encoded, graph_summary
from lightyear_factory.ledger import RunLedger
from lightyear_factory.orchestrator import FactoryOrchestrator
from lightyear_factory.providers import ScriptedModelProvider


def require(condition):
    if not condition:
        raise ContractError("fixture-retrieval-parity-refused")


def audit(trials, approved_sources, projection, corpus):
    """Audit captured bytes and persisted events, not model-reported measurements."""
    require(set(trials) == {"on-demand", "packed", "plain-search"})
    manifest = {p: hashlib.sha256(raw).hexdigest() for p, raw in corpus.items()}
    aliases = {}
    for key, row in approved_sources.items():
        require(manifest.get(row["file"]) == row["sha256"])
        path = key.rsplit(":", 1)[1]
        require(path not in aliases)
        aliases[path] = corpus[row["file"]].decode("utf-8").splitlines()
    # Compare every projection excerpt with the identical pinned source bytes.
    source_count = 0
    for node in projection["nodes"]:
        for source in node.get("source", []):
            require(source["path"] in aliases and "text" in source)
            lines = aliases[source["path"]]
            start, end = source["line_start"], source["line_end"]
            require(1 <= start <= end <= len(lines))
            require(source["text"] == "\n".join(lines[start-1:end]))
            source_count += 1
    require(source_count > 0)
    common_order, instructions, schemas, output = None, {}, {}, {}
    for mode, trial in trials.items():
        order, ledger, provider = trial["order"], trial["ledger"], trial["provider"]
        require(type(provider) is ScriptedModelProvider and not order.allow_network)
        require(trial["manifest"] == manifest)
        boundary = [e["payload"] for e in ledger.events if e["kind"] == "workspace_read_manifest"]
        require(len(boundary) == 1 and boundary[0]["files"] == manifest)
        summary = graph_summary(order, ledger, trial["run_id"])
        require(summary == trial["receipt"]["graph"] and summary["mode"] == mode)
        require(trial["receipt"]["status"] == "passed" and summary["refused_tool_calls"] == 0)
        normalized = copy.deepcopy(order.to_dict())
        normalized["scope"]["graph_node_ids"] = []
        normalized["metadata"].pop("graph", None)
        normalized["metadata"].pop("graph_policy", None)
        if common_order is None:
            common_order = normalized
        require(normalized == common_order)
        if mode != "packed":
            require(summary["call_budget"] == 8 and summary["response_bytes"] == 8192)
        else:
            require(summary["tool_calls"] == 0)
        calls = [e["payload"] for e in ledger.events
                 if e["kind"] in ("graph_tool_finished", "plain_tool_finished")]
        require(len(calls) == summary["tool_calls"])
        delivered = [r["payload"]["graph_result"]["result"] for r in provider.requests
                     if "graph_result" in r["payload"]]
        require(len(delivered) == len(calls))
        total = 0
        for row, result in zip(calls, delivered):
            raw = encoded(result)
            require(row["result_bytes"] == len(raw) <= 8192 and row["scanned"] is True)
            require(row["result_sha256"] == hashlib.sha256(raw).hexdigest())
            scans = [e for e in ledger.events if e["kind"] == "model_isolation_scan_passed"]
            require(any(any(s.get("artifact") == row["scan_artifact"] and
                            s.get("sha256") == row["result_sha256"]
                            for s in e["payload"].get("scanned", [])) for e in scans))
            total += len(raw)
        require(total <= 65536)
        prompts = []
        for req in provider.requests:
            role = req["role"]
            instruction = req["instruction"].split(" You may request ONE read-only retrieval tool", 1)[0]
            schema = copy.deepcopy(req["schema"])
            if "graph_calls" in schema.get("properties", {}):
                require(role in ("planner", "failure_analyst") and mode != "packed")
                schema = schema["properties"]["answer"]
                schema["type"] = "object"
            require(instructions.setdefault(role, instruction) == instruction)
            require(schemas.setdefault(role, schema) == schema)
            if role == "builder":
                require("graph_calls" not in req["schema"]["properties"])
            raw = encoded(req)
            prompts.append(dict(role=role, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()))
        # Include every repeated prompt in accounting; unequal actual use is expected.
        packed_evidence = next(r for r in provider.requests if r["role"] == "builder")["payload"]["graph_context"]
        evidence_bytes = len(encoded(packed_evidence))
        require(evidence_bytes <= 65536)
        if mode == "plain-search":
            require(not packed_evidence["nodes"] and not packed_evidence["edges"] and
                    packed_evidence["semantic_memory"] is None)
        output[mode] = dict(prompt_inventory=prompts, complete_prompt_bytes=sum(p["bytes"] for p in prompts),
            retrieval_calls=len(calls), retrieval_bytes=total, builder_evidence_bytes=evidence_bytes,
            persisted_summary=summary, captured_requests_sha256=hashlib.sha256(encoded(provider.requests)).hexdigest())
    return dict(schema="g3-zero-model-parity/1", fixture_only=True, paid_model_calls=0,
        production_ready=False, corpus_sha256=canonical_hash(manifest), source_files=len(manifest),
        projection_excerpts_checked=source_count, non_context_order_sha256=canonical_hash(common_order),
        instructions_sha256=canonical_hash(instructions), schemas_sha256=canonical_hash(schemas), arms=output)


class RetrievalParityTests(GraphFixture):
    def setUp(self):
        super().setUp()
        self.manifest = self.build()
        # Create the real public-fixture scan before requesting fixture approval.
        leak_report = g2.leak_check(self.out, g2.digest(self.lane), set(g2.CANARIES.values()),
            self.signer, evaluation_inventory_sha256=canonical_hash(g2.CANARIES))
        self.assertTrue(leak_report["passed"])
        proof, trust = self.approve(self.manifest)
        self.approved = (self.out, proof, trust)
        self.projection = json.loads(g2.gzip.decompress((self.out / "projection.json.gz").read_bytes()))
        self.node = next(n for n in self.projection["nodes"]
                         if n["kind"] == "cobol_field" and len(encoded(n)) < 2500
                         and any(s.get("text") for s in n["source"]))
        self.source = self.root / "source"
        (self.source / "candidate").mkdir(parents=True)
        (self.source / "candidate/toy.txt").write_bytes(b"wrong\n")
        self.read_manifest = {"candidate/toy.txt": hashlib.sha256(b"wrong\n").hexdigest()}
    graph_order = g2.FactoryGraphTests.order
    graph_plan = g2.FactoryGraphTests.plan
    edit = staticmethod(g2.FactoryGraphTests.edit)

    def trials(self):
        corpus = {row["file"]: (ROOT / row["file"]).read_bytes()
                  for row in self.lane["approved_sources"].values()}
        corpus["candidate/toy.txt"] = b"wrong\n"
        manifest = {p: hashlib.sha256(raw).hexdigest() for p, raw in corpus.items()}
        for path, raw in corpus.items():
            f = self.source / path
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(raw)
        trials = {}
        for mode in ("on-demand", "packed", "plain-search"):
            payload = self.graph_order(mode="packed", baseline=True).to_dict()
            payload["metadata"]["graph"] = mode
            payload["policy"]["max_context_bytes"] = 65536
            payload["policy"]["max_model_calls"] = 14
            payload["acceptance"]["max_attempts"] = 3
            payload["policy"]["max_model_tokens"] = 700000
            payload["policy"]["max_elapsed_seconds"] = 7190
            if mode == "on-demand":
                payload["metadata"]["graph_policy"] = dict(call_budget=8, response_bytes=8192,
                    projection_sha256=self.manifest["projection_sha256"])
            if mode == "packed":
                payload["scope"]["graph_node_ids"] = [self.node["id"]]
            if mode == "plain-search":
                payload["metadata"]["graph_policy"] = dict(call_budget=8, response_bytes=8192,
                    corpus_sha256=canonical_hash(manifest))
            order = WorkOrder.from_dict(payload)
            plan = self.graph_plan()
            if mode == "plain-search":
                capsule = "source:" + canonical_hash(dict(path="candidate/toy.txt",
                    sha256=manifest["candidate/toy.txt"], start=1, end=1))
                plan["tasks"][0].update(graph_node_ids=[], evidence_capsule_ids=[capsule])
            analysis = dict(summary="Observed public toy issue", failure_codes=["toy"],
                            builder_guidance="Repair toy", risk="low")
            if mode == "packed":
                outputs = [plan, analysis, self.edit()]
            elif mode == "on-demand":
                outputs = [request("graph_node", node_id=self.node["id"], include_source=True), answer(plan),
                    request("graph_node", node_id=self.node["id"], include_source=True), answer(analysis), self.edit()]
            else:
                outputs = [request("read_file", path="candidate/toy.txt", line_start=1, line_end=1), answer(plan),
                    request("search_code", query="wrong"), answer(analysis), self.edit()]
            provider = ScriptedModelProvider(outputs)
            controller = FactoryOrchestrator(self.source, self.root / "runs", ModelAgentSet(provider),
                workspace_read_manifest=manifest, approved_projection=self.approved)
            # Plain search must work with every graph loading/assembly entry point
            # poisoned. Supplying a real approved graph to the controller is deliberate:
            # it must remain inaccessible, rather than being assembled then redacted.
            with ExitStack() as guards:
                forbidden = []
                if mode == "plain-search":
                    for target in (
                        "lightyear_factory.orchestrator.FactoryOrchestrator._context",
                        "lightyear_factory.context.GraphContextAssembler.assemble",
                        "lightyear_factory.context.GraphContextAssembler._assemble_annotated",
                        "lightyear_factory.context.GraphExplorerIndex",
                        "lightyear_toolkit.graph_approval.load_approved",
                        "lightyear_factory.graph_tools.FactoryGraphSession",
                    ):
                        forbidden.append(guards.enter_context(patch(target,
                            side_effect=AssertionError("plain-search-graph-access"))))
                guards.enter_context(patch.object(controller, "_run_gates",
                    side_effect=[gate(False), gate(True)]))
                receipt = controller.run(order, mode)
                for entry in forbidden:
                    entry.assert_not_called()
                if mode == "plain-search":
                    self.assertEqual(set(manifest), set(controller.agents.graph_session.corpus))
                    for req in provider.requests:
                        context = req["payload"].get("graph_context", {})
                        self.assertFalse(context.get("nodes"))
                        self.assertFalse(context.get("edges"))
                        self.assertFalse(context.get("semantic_memory"))
                        for excerpt in context.get("source_excerpts", []):
                            self.assertIn(excerpt["path"], manifest)
                            self.assertEqual([], excerpt["supports"])
            trials[mode] = dict(order=order, manifest=manifest.copy(), provider=provider, receipt=receipt,
                ledger=RunLedger(self.root / "runs" / mode / "events.jsonl"), run_id=mode)
        return trials, corpus

    def test_three_modes_source_prompt_disclosure_and_refusal_parity(self):
        trials, corpus = self.trials()
        report = audit(trials, self.lane["approved_sources"], self.projection, corpus)
        self.assertEqual({"on-demand": 2, "packed": 0, "plain-search": 2},
                         {k: v["retrieval_calls"] for k, v in report["arms"].items()})
        self.assertFalse(report["production_ready"])
        # Source drift, policy drift, prompt drift and unaccounted result bytes must fail.
        bad_corpus = dict(corpus)
        key = next(iter(self.lane["approved_sources"].values()))["file"]
        bad_corpus[key] += b"\nchanged"
        with self.assertRaisesRegex(ContractError, "fixture-retrieval-parity-refused"):
            audit(trials, self.lane["approved_sources"], self.projection, bad_corpus)
        manifest = trials["plain-search"]["manifest"]
        manifest["extra.txt"] = "0" * 64
        with self.assertRaisesRegex(ContractError, "fixture-retrieval-parity-refused"):
            audit(trials, self.lane["approved_sources"], self.projection, corpus)
        del manifest["extra.txt"]
        saved_order = trials["plain-search"]["order"]
        changed = saved_order.to_dict()
        changed["policy"]["max_model_calls"] = 13
        trials["plain-search"]["order"] = WorkOrder.from_dict(changed)
        with self.assertRaises(ContractError):
            audit(trials, self.lane["approved_sources"], self.projection, corpus)
        trials["plain-search"]["order"] = saved_order
        provider = trials["plain-search"]["provider"]
        original = copy.deepcopy(provider.requests)
        provider.requests[-1]["instruction"] += " Extra help"
        with self.assertRaisesRegex(ContractError, "fixture-retrieval-parity-refused"):
            audit(trials, self.lane["approved_sources"], self.projection, corpus)
        provider.requests = copy.deepcopy(original)
        provider.requests[1]["payload"]["graph_result"]["result"]["extra"] = "unaccounted"
        with self.assertRaisesRegex(ContractError, "fixture-retrieval-parity-refused"):
            audit(trials, self.lane["approved_sources"], self.projection, corpus)
        provider.requests = original
        # Emit full public fixture request bytes for inspectable diffs, plus their hash inventory.
        destination = os.environ.get("G3_PARITY_OUTPUT")
        if destination:
            directory = Path(destination)
            directory.mkdir(parents=True, exist_ok=True)
            report["ci"] = dict(source_sha=os.environ.get("G3_CI_SOURCE_SHA"),
                run_id=os.environ.get("G3_CI_RUN_ID"), attempt=os.environ.get("G3_CI_RUN_ATTEMPT"))
            (directory / "parity.json").write_bytes(encoded(report) + b"\n")
            for mode, trial in trials.items():
                (directory / (mode + "-requests.json")).write_bytes(encoded(trial["provider"].requests) + b"\n")
