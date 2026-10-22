"""Controller-owned, read-only graph queries for Planner and failure Analyst.

No judge client, worker log, model endpoint, source graph or evidence pack is
reachable here. Operator approval is supplied through the existing trusted
projection configuration. CI fixtures do not authorize production activation.
"""
import copy
import hashlib
import json
import re
from pathlib import Path

from .contracts import ContractError, canonical_hash
from .ledger import RunLedger

TOOLS = ("graph_search", "graph_neighbors", "graph_node", "graph_references", "graph_guidance")
ROLES = ("planner", "failure_analyst")
PRIVATE = re.compile(
    r"expected[\s_-]*(?:states?|outputs?|values?)|reference[\s_-]*(?:traces?|outputs?)|"
    r"session[\s_-]*answers?|prior[\s_-]*receipts?|get[\s_-]*verdict", re.I)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def graph_policy(order):
    mode = order.metadata.get("graph", "packed")
    if mode == "plain-search":
        from .plain_search import plain_policy
        return plain_policy(order)
    if mode not in ("packed", "on-demand"):
        raise ContractError("factory-graph-mode")
    config = order.metadata.get("graph_policy", {})
    if mode == "packed":
        if config:
            raise ContractError("factory-graph-packed-policy")
        return dict(mode=mode, call_budget=0, response_bytes=0, projection_sha256=None)
    if (not isinstance(config, dict) or set(config) !=
            {"call_budget", "response_bytes", "projection_sha256"} or
            type(config["call_budget"]) is not int or not 1 <= config["call_budget"] <= 32 or
            type(config["response_bytes"]) is not int or not 1024 <= config["response_bytes"] <= 32768 or
            not isinstance(config["projection_sha256"], str) or
            not re.fullmatch("[a-f0-9]{64}", config["projection_sha256"]) or
            order.metadata.get("context_schema") != "1.1" or order.allow_network):
        raise ContractError("factory-graph-policy")
    return dict(mode=mode, **config)


def graph_summary(order, ledger, run_id):
    """Count only persisted controller events, never a model's claimed count."""
    if order.metadata.get("graph") == "plain-search":
        from .plain_search import plain_summary
        return plain_summary(order, ledger, run_id)
    persisted = RunLedger(ledger.path)
    if persisted.events != ledger.events:
        raise ContractError("factory-graph-ledger-changed")
    policy = graph_policy(order)
    bindings = [e["payload"] for e in persisted.events if e["kind"] == "graph_policy_bound"]
    calls = [e["payload"] for e in persisted.events if e["kind"] == "graph_tool_finished"]
    expected = dict(policy, run_id=run_id, work_order_sha256=order.content_sha256)
    # Pre-G2 packed runs have no graph events; retain their receipt compatibility.
    legacy_packed = policy["mode"] == "packed" and not bindings and not calls
    if not legacy_packed and (bindings != [expected] or len(calls) > policy["call_budget"]):
        raise ContractError("factory-graph-ledger-binding")
    for number, row in enumerate(calls, 1):
        if (row.get("call") != number or row.get("run_id") != run_id or
                row.get("work_order_sha256") != order.content_sha256 or
                row.get("projection_sha256") != policy["projection_sha256"] or
                row.get("role") not in ROLES or type(row.get("attempt")) is not int or
                not 0 <= row["attempt"] <= order.max_attempts or
                row.get("tool") not in TOOLS or row.get("status") not in ("passed", "refused")):
            raise ContractError("factory-graph-ledger-call")
        if row["status"] == "passed" and (
                row.get("arguments_sha256") != canonical_hash(row.get("arguments")) or
                not re.fullmatch("[a-f0-9]{64}", row.get("result_sha256", "")) or
                type(row.get("result_bytes")) is not int or
                not 0 < row["result_bytes"] <= policy["response_bytes"] or
                row.get("scanned") is not True):
            raise ContractError("factory-graph-ledger-result")
    return dict(policy, tool_calls=len(calls),
                successful_tool_calls=sum(r["status"] == "passed" for r in calls),
                refused_tool_calls=sum(r["status"] == "refused" for r in calls),
                tool_events=[e["event_sha256"] for e in persisted.events
                             if e["kind"] == "graph_tool_finished"])


class FactoryGraphSession:
    def __init__(self, order, run_id, ledger, context, approved_projection,
                 read_manifest, scanner, workspace):
        from lightyear_toolkit.graph import GraphTools
        from lightyear_toolkit.graph_approval import load_approved
        self.policy = graph_policy(order)
        if (self.policy["mode"] != "on-demand" or approved_projection is None or
                read_manifest is None or not callable(scanner)):
            raise ContractError("factory-graph-boundary-required")
        self.order, self.run_id, self.ledger = order, run_id, ledger
        self.context, self.scanner = context, scanner
        self.count = 0
        self.failed = False
        projection, manifest, decision = load_approved(*approved_projection)
        if (manifest["projection_sha256"] != self.policy["projection_sha256"] or
                context.get("context_projection_sha256") != manifest["projection_sha256"] or
                context.get("schema_version") != "1.1" or
                projection["customer_id"] != order.metadata.get("customer_id")):
            raise ContractError("factory-graph-projection-binding")
        # Inspect every complete member, including unknown extension fields.
        # Keeping members separate avoids an aggregate JSON-node limit bypass.
        for key, value in projection.items():
            for index, member in enumerate(value if isinstance(value, list) else [value]):
                raw = encoded({key: member})
                if PRIVATE.search(raw.decode("utf-8")):
                    raise ContractError("factory-graph-private-material")
                scanner("graph-inventory-" + canonical_hash(dict(member=key, index=index)), raw)
        revocations = None
        if projection.get("annotations"):
            from lightyear_toolkit.revocations import RevocationReader
            revocations = RevocationReader(Path(approved_projection[0]) / "revocations",
                projection["revocation_binding"], manifest["projection_sha256"],
                state_directory=approved_projection[2].get("revocation_state_directory"))
            revocations.read()
        self.tools = GraphTools(projection, manifest, decision, workspace, None,
                                cap=self.policy["response_bytes"], revocations=revocations)
        # Explicit dispatch: never GraphTools.call/getattr, explain_divergence or a client.
        self.dispatch = dict(graph_search=self.tools._graph_search,
            graph_neighbors=self.tools._graph_neighbors, graph_node=self.tools._graph_node,
            graph_references=self.tools._graph_references, graph_guidance=self.tools._graph_guidance)
        ledger.append("PLANNED", "graph_policy_bound",
                      dict(self.policy, run_id=run_id, work_order_sha256=order.content_sha256))

    def call(self, role, attempt, tool, arguments):
        if (self.failed or role not in ROLES or tool not in self.dispatch or
                type(attempt) is not int or not 0 <= attempt <= self.order.max_attempts):
            raise ContractError("factory-graph-tool-forbidden")
        if self.count >= self.policy["call_budget"]:
            self.failed = True
            raise ContractError("factory-graph-call-budget")
        self.count += 1
        identity = dict(run_id=self.run_id, work_order_sha256=self.order.content_sha256,
                        projection_sha256=self.policy["projection_sha256"], call=self.count,
                        role=role, attempt=attempt, tool=tool)
        label = "graph-tool-" + str(self.count)
        try:
            raw_args = encoded(arguments)
            if (not isinstance(arguments, dict) or len(raw_args) > 8192 or
                    PRIVATE.search(raw_args.decode("utf-8")) or
                    (tool == "graph_search" and arguments.get("mode", "lexical") != "lexical")):
                raise ContractError("factory-graph-arguments-refused")
            self.scanner(label + "-arguments", raw_args)
            if not self.tools.active():
                raise ContractError("factory-graph-approval-expired")
            if self.tools.revocations:
                self.tools.revocations.read()
            result = self.dispatch[tool](**arguments)
            raw = encoded(result)
            # Inspect the complete response before any catalog expansion/disclosure.
            self.scanner(label + "-raw-result", raw)
            if PRIVATE.search(raw.decode("utf-8")):
                raise ContractError("factory-graph-private-material")
            result, expanded = self._citations(result)
            raw = encoded(result)
            if len(raw) > self.policy["response_bytes"]:
                raise ContractError("factory-graph-response-cap")
            self.scanner(label + "-result", raw)
            self.context.clear()
            self.context.update(expanded)
            self.ledger.append("PLANNED" if role == "planner" else "REPAIRING",
                "graph_tool_finished", dict(identity, status="passed", arguments=arguments,
                    arguments_sha256=canonical_hash(arguments),
                    result_sha256=hashlib.sha256(raw).hexdigest(), result_bytes=len(raw),
                    scan_artifact=label + "-result", scanned=True))
            return result
        except Exception:
            self.failed = True
            # Neither rejected arguments, result contents nor exception text is persisted.
            self.ledger.append("BLOCKED", "graph_tool_finished",
                               dict(identity, status="refused", reason="graph-tool-refused"))
            raise

    def _citations(self, result):
        from .context import GraphContextAssembler
        expanded = copy.deepcopy(self.context)
        known = {n["id"] for n in expanded["nodes"]}
        capsules = {s["capsule_id"] for s in expanded["source_excerpts"]}
        catalog = []
        for row in result.get("items", []):
            node_id = row.get("id")
            if node_id not in self.tools.index.node_by_id:
                continue
            node = self.tools.index.node(node_id, audience="implementer")
            # Use the admitted original node, never a response-supplied replacement.
            node = self.tools.index.node_by_id[node_id]
            if node_id not in known:
                expanded["nodes"].append(copy.deepcopy(node))
                known.add(node_id)
            for source in node.get("source", []):
                if "text" not in source:
                    continue
                capsule = dict(capsule_id="projection:" + canonical_hash(dict(node=node_id, source=source)),
                    path=source["path"], line_start=source["line_start"], line_end=source["line_end"],
                    confidence="observed", language=Path(source["path"]).suffix.lstrip("."),
                    lines=[dict(number=source["line_start"] + i, text=line, highlighted=i == 0)
                           for i, line in enumerate(source["text"].splitlines())],
                    supports=[dict(owner_type="node", owner_id=node_id)])
                if capsule["capsule_id"] not in capsules:
                    expanded["source_excerpts"].append(capsule)
                    capsules.add(capsule["capsule_id"])
                catalog.append(dict(node_id=node_id, capsule_id=capsule["capsule_id"]))
        expanded.pop("content_sha256", None)
        expanded = GraphContextAssembler._finish(expanded, self.order)
        if len(encoded(expanded)) > self.order.max_context_bytes:
            raise ContractError("factory-graph-context-cap")
        self.scanner("graph-query-context-" + str(self.count), encoded(expanded))
        return dict(result, evidence_catalog=catalog), expanded
