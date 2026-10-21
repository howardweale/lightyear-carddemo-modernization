"""Pinned public-source retrieval. No graph, judge, subprocess or provider access."""
import copy
import hashlib
import os
import re
import stat
from pathlib import Path

from .contracts import ContractError, canonical_hash
from .context import GraphContextAssembler
from .graph_tools import PRIVATE, ROLES, encoded
from .ledger import RunLedger
from .workspace import IsolatedWorkspace

TOOLS = ("search_code", "read_file")


def plain_policy(order):
    config = order.metadata.get("graph_policy")
    if (order.metadata.get("graph") != "plain-search" or not isinstance(config, dict) or
            set(config) != {"call_budget", "response_bytes", "corpus_sha256"} or
            type(config["call_budget"]) is not int or not 1 <= config["call_budget"] <= 8 or
            type(config["response_bytes"]) is not int or not 1024 <= config["response_bytes"] <= 8192 or
            not isinstance(config["corpus_sha256"], str) or
            not re.fullmatch("[a-f0-9]{64}", config["corpus_sha256"]) or
            order.metadata.get("context_schema") != "1.1" or order.graph_node_ids or
            order.allow_network):
        raise ContractError("factory-plain-policy")
    return dict(mode="plain-search", **config)


def plain_context(order):
    plain_policy(order)
    # Build from scratch: never assemble a graph or memory and then redact it.
    return GraphContextAssembler._finish(dict(schema_version="1.0",
        context_type="lightyear-public-source-context", audience="implementer",
        graph_content_sha256=None, evidence_pack_sha256=None, approved_roots=[],
        nodes=[], edges=[], source_excerpts=[], allowed_files=[], semantic_memory=None,
        truncated=False, limitations=["Only pinned public source; no graph hints or memory."]), order)


def load_corpus(workspace, manifest, scanner):
    """Snapshot every admitted file once; later candidate edits cannot change retrieval."""
    if not isinstance(manifest, dict) or not manifest or len(manifest) > 4096 or not callable(scanner):
        raise ContractError("factory-plain-boundary-required")
    root = Path(workspace)
    if root.is_symlink() or getattr(root, "is_junction", lambda: False)():
        raise ContractError("factory-plain-path")
    root = root.resolve()
    identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_nlink)
    total, planned, corpus = 0, [], {}
    for relative, expected in sorted(manifest.items()):
        IsolatedWorkspace._strict_relative(relative)
        if not isinstance(expected, str) or not re.fullmatch("[a-f0-9]{64}", expected):
            raise ContractError("factory-plain-manifest")
        path = root / relative
        for part in (path, *path.parents):
            if part == root:
                break
            if part.is_symlink() or getattr(part, "is_junction", lambda: False)():
                raise ContractError("factory-plain-path")
        info = path.stat()
        total += info.st_size
        if (root not in path.resolve().parents or not stat.S_ISREG(info.st_mode) or
                info.st_nlink != 1 or info.st_size > 8 * 1024 * 1024 or total > 32 * 1024 * 1024):
            raise ContractError("factory-plain-file-limit")
        planned.append((relative, path, expected, info))
    for relative, path, expected, info in planned:
        with path.open("rb") as handle:
            if identity(os.fstat(handle.fileno())) != identity(info):
                raise ContractError("factory-plain-file-changed")
            raw = handle.read(info.st_size + 1)
            if identity(os.fstat(handle.fileno())) != identity(info):
                raise ContractError("factory-plain-file-changed")
        if (identity(path.stat()) != identity(info) or len(raw) != info.st_size or
                hashlib.sha256(raw).hexdigest() != expected):
            raise ContractError("factory-plain-hash")
        try:
            source = raw.decode("utf-8")
        except UnicodeError:
            raise ContractError("factory-plain-utf8") from None
        scanner("plain-source-" + canonical_hash(relative), raw)
        scanner("plain-path-" + canonical_hash(relative), encoded(relative))
        if PRIVATE.search(source) or PRIVATE.search(relative):
            raise ContractError("factory-plain-private-material")
        corpus[relative] = source
    return corpus


class FactoryPlainSession:
    def __init__(self, order, run_id, ledger, context, read_manifest, scanner, workspace):
        self.policy = plain_policy(order)
        if canonical_hash(read_manifest) != self.policy["corpus_sha256"]:
            raise ContractError("factory-plain-corpus-binding")
        if context != plain_context(order):
            raise ContractError("factory-plain-context-binding")
        self.corpus = load_corpus(workspace, read_manifest, scanner)
        self.manifest = dict(read_manifest)
        self.order, self.run_id, self.ledger = order, run_id, ledger
        self.context, self.scanner = context, scanner
        self.count, self.result_bytes, self.failed = 0, 0, False
        self.dispatch = dict(search_code=self.search_code, read_file=self.read_file)
        ledger.append("PLANNED", "plain_policy_bound", dict(self.policy,
            run_id=run_id, work_order_sha256=order.content_sha256))

    def excerpt(self, path, start, end):
        lines = self.corpus[path].splitlines()
        return dict(capsule_id="source:" + canonical_hash(dict(path=path,
            sha256=self.manifest[path], start=start, end=end)), path=path,
            source_sha256=self.manifest[path], line_start=start, line_end=end,
            confidence="observed", language=Path(path).suffix.lstrip("."), supports=[],
            lines=[dict(number=i, text=lines[i-1], highlighted=True) for i in range(start, end+1)])

    def search_code(self, query):
        if not isinstance(query, str) or not query or len(query.encode("utf-8")) > 512 or "\n" in query:
            raise ContractError("factory-plain-query")
        # Literal case-sensitive matching over ALL pinned files, in stable path/line order.
        # Refuse a large result rather than silently selecting or truncating hits.
        items = []
        for path, text in self.corpus.items():
            for line, source in enumerate(text.splitlines(), 1):
                if query in source:
                    items.append(self.excerpt(path, line, line))
                    if len(encoded(items)) > self.policy["response_bytes"]:
                        raise ContractError("factory-plain-response-cap")
        return dict(items=items, truncated=False)

    def read_file(self, path, line_start, line_end):
        if (not isinstance(path, str) or path not in self.corpus or
                type(line_start) is not int or type(line_end) is not int or
                not 1 <= line_start <= line_end <= len(self.corpus[path].splitlines()) or
                line_end - line_start >= 200):
            raise ContractError("factory-plain-read-range")
        return dict(items=[self.excerpt(path, line_start, line_end)], truncated=False)

    def call(self, role, attempt, tool, arguments):
        if (self.failed or role not in ROLES or tool not in self.dispatch or
                type(attempt) is not int or not 0 <= attempt <= self.order.max_attempts):
            raise ContractError("factory-plain-tool-forbidden")
        if self.count >= self.policy["call_budget"]:
            self.failed = True
            raise ContractError("factory-plain-call-budget")
        self.count += 1
        identity = dict(run_id=self.run_id, work_order_sha256=self.order.content_sha256,
            corpus_sha256=self.policy["corpus_sha256"], call=self.count, role=role,
            attempt=attempt, tool=tool)
        label = "plain-tool-" + str(self.count)
        try:
            raw_args = encoded(arguments)
            if not isinstance(arguments, dict) or len(raw_args) > 8192 or PRIVATE.search(raw_args.decode()):
                raise ContractError("factory-plain-arguments-refused")
            self.scanner(label + "-arguments", raw_args)
            result = self.dispatch[tool](**arguments)
            result["corpus_sha256"] = self.policy["corpus_sha256"]
            result["evidence_catalog"] = [dict(capsule_id=r["capsule_id"]) for r in result["items"]]
            raw = encoded(result)
            self.scanner(label + "-result", raw)
            if PRIVATE.search(raw.decode()):
                raise ContractError("factory-plain-private-material")
            if len(raw) > self.policy["response_bytes"] or self.result_bytes + len(raw) > 65536:
                raise ContractError("factory-plain-response-cap")
            expanded = copy.deepcopy(self.context)
            known = {r["capsule_id"] for r in expanded["source_excerpts"]}
            for row in result["items"]:
                if row["capsule_id"] not in known:
                    expanded["source_excerpts"].append(copy.deepcopy(row))
                    known.add(row["capsule_id"])
            expanded.pop("content_sha256", None)
            expanded = GraphContextAssembler._finish(expanded, self.order)
            if len(encoded(expanded)) > min(self.order.max_context_bytes, 65536):
                raise ContractError("factory-plain-context-cap")
            self.scanner(label + "-context", encoded(expanded))
            self.context.clear()
            self.context.update(expanded)
            self.result_bytes += len(raw)
            self.ledger.append("PLANNED" if role == "planner" else "REPAIRING", "plain_tool_finished",
                dict(identity, status="passed", arguments=arguments, arguments_sha256=canonical_hash(arguments),
                     result_sha256=hashlib.sha256(raw).hexdigest(), result_bytes=len(raw),
                     scan_artifact=label + "-result", scanned=True))
            return result
        except Exception:
            self.failed = True
            self.ledger.append("BLOCKED", "plain_tool_finished", dict(identity, status="refused"))
            raise ContractError("factory-plain-query-refused") from None


def plain_summary(order, ledger, run_id):
    persisted = RunLedger(ledger.path)
    if persisted.events != ledger.events:
        raise ContractError("factory-plain-ledger-changed")
    policy = plain_policy(order)
    bindings = [e["payload"] for e in persisted.events if e["kind"] == "plain_policy_bound"]
    calls = [e["payload"] for e in persisted.events if e["kind"] == "plain_tool_finished"]
    if (bindings != [dict(policy, run_id=run_id, work_order_sha256=order.content_sha256)] or
            len(calls) > policy["call_budget"]):
        raise ContractError("factory-plain-ledger-binding")
    for number, row in enumerate(calls, 1):
        if (row.get("call") != number or row.get("run_id") != run_id or
                row.get("work_order_sha256") != order.content_sha256 or
                row.get("corpus_sha256") != policy["corpus_sha256"] or row.get("role") not in ROLES or
                type(row.get("attempt")) is not int or not 0 <= row["attempt"] <= order.max_attempts or
                row.get("tool") not in TOOLS or row.get("status") not in ("passed", "refused")):
            raise ContractError("factory-plain-ledger-call")
        if row["status"] == "passed" and (
                row.get("arguments_sha256") != canonical_hash(row.get("arguments")) or
                not re.fullmatch("[a-f0-9]{64}", row.get("result_sha256", "")) or
                type(row.get("result_bytes")) is not int or not 0 < row["result_bytes"] <= policy["response_bytes"] or
                row.get("scanned") is not True):
            raise ContractError("factory-plain-ledger-result")
    total = sum(r.get("result_bytes", 0) for r in calls)
    if total > 65536:
        raise ContractError("factory-plain-ledger-bytes")
    return dict(policy, tool_calls=len(calls), result_bytes=total,
        successful_tool_calls=sum(r["status"] == "passed" for r in calls),
        refused_tool_calls=sum(r["status"] == "refused" for r in calls),
        tool_events=[e["event_sha256"] for e in persisted.events if e["kind"] == "plain_tool_finished"])
