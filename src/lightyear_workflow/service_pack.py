"""Closed, declarative service journeys: observe a source, replay a target.

Declarations contain data and bounded primitives, never Python, shell commands,
routing URLs, credential headers or plugin names. The source holds only a record-reader
capability. Even GET is an invocation and belongs to the target lane.
"""
from __future__ import annotations

import concurrent.futures
import hashlib
import json
import math
import re
import time
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol
from urllib.parse import quote, urlencode, urlsplit

from lightyear_common.evidence import evidence_floor

PACK_TYPE = "lightyear-service-journey-pack"
SCHEMA_VERSION = "1.0"
MAX_BYTES = 1024 * 1024
ID = re.compile(r"[a-z][a-z0-9_-]{0,79}\Z")
METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"})
CONTROLS = frozenset({"ready", "authorize", "stop", "start", "restart", "crash_stop",
                      "restart_all", "block_delivery", "restore_delivery", "queue"})
EVIDENCE_LEVELS = ("simulated", "local_observed", "runtime_observed")
MUTATING_CONTROLS = frozenset({"stop", "start", "restart", "crash_stop", "restart_all", "block_delivery", "restore_delivery"})
GLOBAL_CONTROLS = frozenset({"ready", "authorize", "restart_all", "block_delivery", "restore_delivery"})
ARITY = {"eq": 2, "ne": 2, "lt": 2, "le": 2, "gt": 2, "ge": 2, "add": 2, "sub": 2,
         "get": 2, "in": 2, "len": 1, "int": 1, "str": 1, "hash": 1, "json": 1,
         "text": 1, "not": 1, "sort": 1, "sum": 1, "unique": 1,
         "sort_by": 2, "merge": 2, "replace_at": 3, "lookup": 3, "digits": 2, "location_id": 2, "message_id": 2, "is_int": 1, "is_object": 1,
         "is_list": 1, "is_sha256": 1, "safe_text": 1,
         "append": 2, "concat": None, "and": None, "or": None}


class PackError(ValueError):
    """Invalid declaration; no invocation is permitted."""


class JourneyFailure(Exception):
    """A bounded diagnostic, without response data or credentials."""
    def __init__(self, code: str):
        super().__init__(code if re.fullmatch(r"[a-z0-9-]{1,100}", code) else "journey-failed")


def require(condition: bool, code: str) -> None:
    if not condition:
        raise JourneyFailure(code)


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def hashed(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def _equal(left, right):
    if type(left) is not type(right): return False
    if isinstance(left, list):
        return len(left) == len(right) and all(_equal(a, b) for a, b in zip(left, right))
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(_equal(left[k], right[k]) for k in left)
    return left == right


def _object(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= value.keys() or set(value) - set(required) - set(optional):
        raise PackError(f"expected object with {sorted(required)} and optional {sorted(optional)}")


def _id(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise PackError("invalid identifier")
    return value


def _list(value, maximum=500, empty=False):
    if not isinstance(value, list) or len(value) > maximum or (not empty and not value):
        raise PackError("expected bounded nonempty list")
    return value


def _unique_ids(value, empty=False):
    values = _list(value, empty=empty)
    if any(not isinstance(v, str) for v in values) or len(set(values)) != len(values):
        raise PackError("identifiers must be unique strings")
    return {_id(v) for v in values}


def _json_tree(value, depth=0):
    if depth > 40:
        raise PackError("declaration nesting exceeds 40")
    if value is None or type(value) in (bool, int, str):
        return
    if isinstance(value, list):
        if len(value) > 500: raise PackError("collection too large")
        for v in value: _json_tree(v, depth + 1)
    elif isinstance(value, dict):
        if len(value) > 500 or any(not isinstance(k, str) for k in value): raise PackError("invalid object")
        for v in value.values(): _json_tree(v, depth + 1)
    else:
        # Integers and decimal strings only: never silently round money.
        raise PackError("only JSON objects, arrays, strings, integers, booleans and null are supported")


def _expr(value, scope):
    if isinstance(value, list):
        for v in value: _expr(v, scope)
    elif isinstance(value, dict):
        if "$ref" in value:
            _object(value, {"$ref"})
            path = value["$ref"]
            if not isinstance(path, str) or not path or path.split(".")[0] not in scope:
                raise PackError("unknown expression reference")
            if any(not re.fullmatch(r"[A-Za-z0-9_-]+", p) for p in path.split(".")):
                raise PackError("invalid reference path")
        elif "$op" in value:
            _object(value, {"$op", "args"})
            op = value["$op"]
            if not isinstance(op, str) or op not in ARITY: raise PackError("unsupported expression operation")
            args = _list(value["args"], 20)
            if ARITY[op] is not None and len(args) != ARITY[op]: raise PackError("wrong expression arity")
            for arg in args: _expr(arg, scope)
        elif "$map" in value or "$filter" in value:
            key = "$map" if "$map" in value else "$filter"
            _object(value, {key})
            item = value[key]; _object(item, {"over", "as", "value"})
            _expr(item["over"], scope); _id(item["as"])
            if item["as"] in scope: raise PackError("mapping variable shadows existing name")
            _expr(item["value"], scope | {item["as"]})
        else:
            if any(k.startswith("$") for k in value): raise PackError("unknown expression syntax")
            for v in value.values(): _expr(v, scope)


def _path(template):
    if not isinstance(template, str) or len(template) > 500 or not template.startswith("/") or template.startswith("//"):
        raise PackError("request paths must be service-relative")
    stripped = re.sub(r"\{[a-z][a-z0-9_]*\}", "x", template)
    if not re.fullmatch(r"/[A-Za-z0-9/_-]*", stripped) or any(s in {".", ".."} for s in stripped.split("/")):
        raise PackError("unsafe request path")
    return set(re.findall(r"\{([a-z][a-z0-9_]*)\}", template))


@dataclass(frozen=True)
class JourneyPack:
    """Canonical immutable snapshot. Accessors return detached values."""
    document: str

    @property
    def raw(self): return json.loads(self.document)
    @property
    def pack_id(self): return self.raw["pack_id"]
    @property
    def journeys(self): return tuple(self.raw["journeys"])
    @property
    def sha256(self): return hashlib.sha256(self.document.encode()).hexdigest()


def validate_pack(raw: dict) -> JourneyPack:
    try:
        return _validate_pack(raw)
    except PackError:
        raise
    except (TypeError, ValueError, KeyError, AttributeError, RecursionError, OverflowError) as exc:
        raise PackError("malformed service pack") from exc


def _validate_pack(raw: dict) -> JourneyPack:
    _json_tree(raw)
    _object(raw, {"pack_type", "schema_version", "pack_id", "estate", "source", "target",
                  "services", "roles", "inputs", "state", "macros", "journeys"}, {"description"})
    if raw["pack_type"] != PACK_TYPE or raw["schema_version"] != SCHEMA_VERSION:
        raise PackError("unsupported service pack type or version")
    _id(raw["pack_id"]); _id(raw["estate"])
    for name, allowed in [("source", {"observe"}), ("target", {"request", "control"})]:
        _object(raw[name], {"verbs"})
        verbs = _unique_ids(raw[name]["verbs"])
        if not verbs <= allowed: raise PackError(f"{name} lane has forbidden capabilities; source is observed, never driven")
    services = _unique_ids(raw["services"])
    roles = _unique_ids(raw["roles"], empty=True)
    if not isinstance(raw["inputs"], dict) or not isinstance(raw["state"], dict) or not isinstance(raw["macros"], dict):
        raise PackError("inputs, state and macros must be objects")
    for name, kind in raw["inputs"].items():
        _id(name)
        if kind not in ("identifier", "integer", "string"): raise PackError("unsupported input type")
    scope = set(raw["inputs"])
    for name, value in raw["state"].items():
        _id(name)
        if name in scope: raise PackError("duplicate input/state name")
        _expr(value, set(raw["inputs"])); scope.add(name)
    signatures = {}
    for name, macro in raw["macros"].items():
        _id(name); _object(macro, {"params", "steps", "return"}, {"defaults"})
        params = _unique_ids(macro["params"], empty=True)
        if params & scope: raise PackError("macro parameter shadows state/input")
        defaults = macro.get("defaults", {})
        if not isinstance(defaults, dict) or not set(defaults) <= params: raise PackError("invalid macro defaults")
        _expr(defaults, scope)
        signatures[name] = params
    graph = {name: set() for name in signatures}

    def steps(items, names, calls, polling=False, parallel=False, depth=0):
        if depth > 12: raise PackError("step nesting exceeds 12")
        names = set(names)
        for step in _list(items):
            if not isinstance(step, dict): raise PackError("step must be an object")
            op = step.get("op")
            forms = {
                "set": ({"name", "value"}, {"state"}), "assert": ({"test", "code"}, set()),
                "request": ({"service", "method", "path"}, {"params", "query", "role", "body", "headers", "save", "allow_error"}),
                "control": ({"action"}, {"service", "message", "save"}),
                "call": ({"macro", "args"}, {"save"}),
                "if": ({"test", "then", "else"}, set()),
                "each": ({"over", "as", "max_items", "steps"}, set()),
                "poll": ({"steps", "until", "attempts", "code"}, set()),
                "parallel": ({"calls", "save"}, set()),
                "ensure": ({"steps", "finally"}, set()),
            }
            if op not in forms: raise PackError("unknown step operation")
            req, opt = forms[op]; _object(step, req | {"op"}, opt)
            if op == "set":
                _id(step["name"]); _expr(step["value"], names)
                if "state" in step and type(step["state"]) is not bool: raise PackError("state must be boolean")
                if step.get("state"):
                    if step["name"] not in raw["state"] or parallel: raise PackError("invalid shared-state assignment")
                elif step["name"] in scope: raise PackError("local assignment shadows state/input")
                names.add(step["name"])
            elif op == "assert":
                _expr(step["test"], names); _code(step["code"])
            elif op == "request":
                if "request" not in raw["target"]["verbs"]: raise PackError("request capability missing")
                if step["service"] not in services or step["method"] not in METHODS: raise PackError("unknown service or HTTP method")
                if polling and step["method"] not in {"GET", "HEAD"}: raise PackError("poll may not repeat a write")
                params = step.get("params", {})
                if not isinstance(params, dict) or set(params) != _path(step["path"]): raise PackError("path parameters do not match template")
                if step.get("role") is not None and step["role"] not in roles: raise PackError("unknown credential role")
                for key in ["params", "query", "headers"]:
                    v = step.get(key, {})
                    if not isinstance(v, dict): raise PackError("request fields must be objects")
                    for name in v:
                        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,79}", name): raise PackError("invalid request field")
                        if key == "headers" and name != "Idempotency-Key": raise PackError("headers cannot carry credentials, routing or method overrides")
                        if key == "query" and re.search(r"(?i)(password|secret|token|authorization|api.?key)", name): raise PackError("credentials belong in adapter roles")
                    _expr(v, names)
                _expr(step.get("body"), names)
                if "allow_error" in step and step["allow_error"] != "http-transport-failed": raise PackError("only transport failure can be explicitly observed")
            elif op == "control":
                action = step["action"]
                if "control" not in raw["target"]["verbs"] or action not in CONTROLS: raise PackError("unknown or unavailable control capability")
                if polling and action != "queue": raise PackError("poll may only observe queues or HTTP reads")
                if action in {"stop", "start", "restart", "crash_stop"}:
                    if step.get("service") not in services or "message" in step: raise PackError("control requires a declared service")
                elif action == "queue":
                    if step.get("service") not in services or "message" not in step: raise PackError("queue requires service and message")
                    _expr(step["message"], names)
                elif "service" in step or "message" in step: raise PackError("global control does not take arguments")
            elif op == "call":
                name = step["macro"]
                if name not in signatures or not isinstance(step["args"], dict) or set(step["args"]) != signatures[name]: raise PackError("unknown macro or wrong arguments")
                _expr(step["args"], names); calls.add(name)
            elif op == "if":
                _expr(step["test"], names)
                yes = steps(step["then"], names, calls, polling, parallel, depth + 1)
                no = names if step["else"] == [] else steps(step["else"], names, calls, polling, parallel, depth + 1)
                names |= yes & no
            elif op == "each":
                _expr(step["over"], names); _id(step["as"])
                if step["as"] in names: raise PackError("loop variable shadows existing name")
                _bound(step["max_items"], 200)
                # Local accumulators exist before the loop; its body may update them.
                steps(step["steps"], names | {step["as"]}, calls, polling, parallel, depth + 1)
            elif op == "poll":
                _bound(step["attempts"], 181); _code(step["code"])
                names = steps(step["steps"], names, calls, True, parallel, depth + 1)
                _expr(step["until"], names)
            elif op == "parallel":
                if polling: raise PackError("parallel invocation cannot be polled")
                for call in _list(step["calls"], 8):
                    if not isinstance(call, dict) or call.get("op") != "call" or "save" in call: raise PackError("parallel branches must be macro calls")
                    steps([call], names, calls, False, True, depth + 1)
            elif op == "ensure":
                names = steps(step["steps"], names, calls, polling, parallel, depth + 1)
                # Cleanup must work even if the first body step fails.
                steps(step["finally"], set(scope) | (names & set(scope)), calls, False, parallel, depth + 1)
            if "save" in step:
                name = _id(step["save"])
                if name in scope: raise PackError("save shadows state/input")
                names.add(name)
        return names

    for name, macro in raw["macros"].items():
        names = steps(macro["steps"], scope | signatures[name], graph[name])
        _expr(macro["return"], names)
    ids = set()
    for journey in _list(raw["journeys"], 100):
        _object(journey, {"id", "normalized_result", "macro", "args"}, {"description"})
        ident = _id(journey["id"])
        if ident in ids: raise PackError("duplicate journey id")
        ids.add(ident)
        if not isinstance(journey["normalized_result"], str) or not journey["normalized_result"]: raise PackError("journey result label required")
        steps([{"op": "call", "macro": journey["macro"], "args": journey["args"]}], scope, set())
    visiting, visited = set(), set()
    def visit(name):
        if name in visiting: raise PackError("recursive macro calls are forbidden")
        if name in visited: return
        visiting.add(name)
        for child in graph[name]: visit(child)
        visiting.remove(name); visited.add(name)
    for name in graph: visit(name)

    # A journey that observes and checks nothing is not an executable contract.
    feature_cache = {}
    def features(name):
        if name in feature_cache: return feature_cache[name]
        found = set()
        def scan(items):
            for step in items:
                found.add(step["op"])
                if step["op"] == "call": found.update(features(step["macro"]))
                for key in ("steps", "then", "else", "finally", "calls"):
                    if key in step: scan(step[key])
        scan(raw["macros"][name]["steps"])
        feature_cache[name] = found
        return found
    for journey in raw["journeys"]:
        used = features(journey["macro"])
        if not used & {"request", "control"} or not used & {"assert", "poll"}:
            raise PackError("each journey must observe a runtime and declare a check")

    # Validate transitive effects in poll/parallel contexts, not just direct steps.
    expanded_nodes = 0
    def effects(items, polling=False, parallel=False, expansion=0):
        nonlocal expanded_nodes
        expanded_nodes += len(items)
        if expanded_nodes > 100000: raise PackError("expanded declaration too large")
        if expansion > 30: raise PackError("macro expansion too deep")
        for step in items:
            op = step["op"]
            if polling and ((op == "request" and step["method"] not in {"GET", "HEAD"}) or
                            (op == "control" and step["action"] != "queue") or op == "parallel"):
                raise PackError("poll transitively invokes a mutating capability")
            if parallel and (op == "ensure" or (op == "control" and step["action"] != "queue")):
                raise PackError("parallel branches may only issue requests and observations")
            if parallel and op == "set" and step.get("state"): raise PackError("parallel macro mutates shared state")
            if op == "call": effects(raw["macros"][step["macro"]]["steps"], polling, parallel, expansion + 1)
            for key in ("steps", "then", "else", "finally", "calls"):
                if key in step: effects(step[key], polling or op == "poll", parallel or op == "parallel", expansion + 1)
    for macro in raw["macros"].values(): effects(macro["steps"])
    if not raw["journeys"]: raise PackError("empty pack")
    encoded = canonical(raw).decode()
    if len(encoded.encode()) > MAX_BYTES: raise PackError("pack too large")
    return JourneyPack(encoded)


def _code(code):
    if not isinstance(code, str) or not re.fullmatch(r"[a-z0-9-]{1,100}", code): raise PackError("invalid failure code")


def _bound(value, maximum):
    if type(value) is not int or not 1 <= value <= maximum: raise PackError("invalid execution bound")


def load(path: str | Path) -> JourneyPack:
    with Path(path).open("rb") as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES: raise PackError("pack too large")
    def pairs(items):
        result = {}
        for k, v in items:
            if k in result: raise PackError("duplicate JSON key")
            result[k] = v
        return result
    try: raw = json.loads(data, object_pairs_hook=pairs)
    except (ValueError, UnicodeError, RecursionError) as exc: raise PackError("invalid pack JSON") from exc
    return validate_pack(raw)


def plan(pack: JourneyPack) -> dict:
    """Compute the possible footprint, including both branches and recovery.

    Paths are templates when IDs are obtained at runtime. Counts are upper
    bounds, not promises that every branch or polling attempt will execute.
    No callable, credential provider or network client is needed to plan.
    """
    raw = validate_pack(pack.raw).raw
    requests, controls = {}, {}
    def walk(items, multiplier=1):
        for s in items:
            op = s["op"]
            if op == "request":
                row = {"service": s["service"], "method": s["method"], "path": s["path"],
                       "role": s.get("role"), "query_fields": sorted(s.get("query", {})),
                       "body_present": "body" in s, "header_fields": sorted(s.get("headers", {}))}
                key = canonical(row).decode()
                requests.setdefault(key, {**row, "max_calls": 0})["max_calls"] += multiplier
            elif op == "control":
                row = {"action": s["action"], "services": raw["services"] if s["action"] in GLOBAL_CONTROLS else [s["service"]]}
                key = canonical(row).decode()
                controls.setdefault(key, {**row, "max_calls": 0})["max_calls"] += multiplier
            elif op == "call": walk(raw["macros"][s["macro"]]["steps"], multiplier)
            else:
                multiple = s.get("max_items", s.get("attempts", 1))
                for key in ("steps", "then", "else", "finally", "calls"):
                    if key in s: walk(s[key], multiplier * multiple)
    journeys = []
    for j in raw["journeys"]:
        walk(raw["macros"][j["macro"]]["steps"])
        journeys.append(j["id"])
    request_rows = sorted(requests.values(), key=lambda r: (r["service"], r["path"], r["method"], str(r["role"])))
    control_rows = sorted(controls.values(), key=lambda r: (r["action"], r["services"]))
    return {"pack_id": raw["pack_id"], "pack_sha256": pack.sha256, "estate": raw["estate"],
            "journeys": journeys, "source_reads": journeys if "observe" in raw["source"]["verbs"] else [],
            "source_invocations": [r for r in request_rows if "request" in raw["source"]["verbs"]],
            "target_requests": request_rows, "target_controls": control_rows,
            "services_touched": sorted({r["service"] for r in request_rows} | {s for r in control_rows for s in r["services"]}),
            "credential_roles": sorted({r["role"] for r in request_rows if r["role"] is not None}),
            "bounds": "conservative; includes branches, bounded loops, polls and cleanup; adapters must honor declared scope"}


class RecordReader(Protocol):
    def record(self, journey_id: str) -> dict: ...


class SourceLane:
    """Only retrieve already captured evidence. No request/control/replay capability."""
    __slots__ = ("_record",)
    def __init__(self, reader: RecordReader): self._record = reader.record
    def observe(self, pack: JourneyPack) -> dict:
        raw = validate_pack(pack.raw).raw
        observations = []
        for j in raw["journeys"]:
            row = self._record(j["id"])
            if not isinstance(row, dict) or row.get("journey") != j["id"] or "evidence" not in row:
                raise JourneyFailure("source-observation-missing-or-mismatched")
            kind = row.get("evidence_class", "simulated")
            if kind not in {"simulated", "local_observed", "runtime_observed"}: raise JourneyFailure("evidence-class-invalid")
            _json_tree(row)
            if len(canonical(row)) > MAX_BYTES: raise JourneyFailure("source-observation-too-large")
            observations.append(json.loads(canonical({**row, "evidence_class": kind})))
        return {"pack_id": pack.pack_id, "pack_sha256": pack.sha256, "lane": "source", "observations": observations,
                "evidence_class": evidence_floor(*(r["evidence_class"] for r in observations), levels=EVIDENCE_LEVELS)}


class TargetLane:
    """Only this lane can invoke. Transports and controls are explicitly supplied.

    Adapters own host allowlists, credentials, network timeouts, redirect policy
    and restoration. Declarations cannot manufacture any of those capabilities.
    """
    def __init__(self, request: Callable | None = None, *, controls: dict[str, Callable] | None = None,
                 evidence_class="simulated", restore: Callable | None = None):
        if evidence_class not in EVIDENCE_LEVELS: raise PackError("invalid target evidence class")
        self.evidence_class, self._restore = evidence_class, restore
        self._request = request
        self._controls = dict(controls or {})
        if set(self._controls) - CONTROLS or any(not callable(v) for v in self._controls.values()): raise PackError("unsupported target control")
        if request is not None and not callable(request): raise PackError("request must be a capability")
        if restore is not None and not callable(restore): raise PackError("restore must be a capability")

    def preflight(self, pack):
        footprint = plan(pack)
        if footprint["target_requests"] and self._request is None: raise PackError("target request capability required")
        actions = {c["action"] for c in footprint["target_controls"]}
        if actions - self._controls.keys(): raise PackError("target control capability required")
        if actions & MUTATING_CONTROLS and self._restore is None: raise PackError("mutating controls require restoration capability")

    def replay(self, pack: JourneyPack, inputs: dict, source_run: dict, **options):
        """Execute declared assertions, retaining origin and weakest evidence class.

        This is an invocation result, not an automatic source/target equivalence
        verdict. A business comparator can consume both lanes' evidence.
        """
        pack = validate_pack(pack.raw)
        if not isinstance(source_run, dict) or source_run.get("pack_sha256") != pack.sha256 or source_run.get("pack_id") != pack.pack_id or source_run.get("lane") != "source":
            raise PackError("source observation does not match this pack")
        rows = source_run.get("observations")
        if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows) or [r.get("journey") for r in rows] != [j["id"] for j in pack.journeys] or any("evidence" not in r for r in rows):
            raise PackError("source journey observations are incomplete")
        try: source_class = evidence_floor(*(r.get("evidence_class") for r in rows), levels=EVIDENCE_LEVELS)
        except ValueError as exc: raise PackError("invalid source evidence class") from exc
        _json_tree(source_run)
        if len(canonical(source_run)) > MAX_BYTES: raise PackError("source observation too large")
        source_hash = hashed(source_run)
        runner = Runner(pack, self, inputs, **options)
        results, failed = [], False
        recovery = {"status": "not-required"}
        try:
            for j in pack.journeys:
                if failed:
                    results.append({"id": j["id"], "status": "not-run"})
                    continue
                try:
                    evidence = runner.journey(j["id"])
                    _json_tree(evidence)
                    if len(canonical(evidence)) > MAX_BYTES: raise JourneyFailure("evidence-too-large")
                    results.append({"id": j["id"], "status": "passed", "evidence": evidence})
                except Exception as exc:
                    failed = True
                    results.append({"id": j["id"], "status": "failed", "reason": str(exc) if isinstance(exc, JourneyFailure) else "execution-failed"})
        finally:
            if self._restore is not None:
                try:
                    recovery = self._restore()
                    if not isinstance(recovery, dict) or recovery.get("status") != "restored":
                        recovery = {"status": "failed"}; failed = True
                    else: recovery = {"status": "restored"}
                except Exception:
                    recovery = {"status": "failed"}; failed = True
        return {"pack_id": pack.pack_id, "pack_sha256": pack.sha256, "lane": "target",
                "source_sha256": source_hash, "source_evidence_class": source_class,
                "target_evidence_class": self.evidence_class,
                "evidence_class": evidence_floor(source_class, self.evidence_class, levels=EVIDENCE_LEVELS),
                "status": "failed" if failed else "passed-declared-assertions", "journeys": results,
                "recovery": recovery, "source_target_comparison_performed": False}

    def request(self, service, method, path, role, body=None, headers=None):
        if self._request is None: raise JourneyFailure("target-request-unavailable")
        response = self._request(service, method, path, role, body, headers)
        require(type(response.status) is int and 100 <= response.status <= 599 and isinstance(response.body, bytes)
                and len(response.body) <= MAX_BYTES and isinstance(response.headers, dict), "response-shape-invalid")
        return {"status": response.status, "body": response.body, "headers": dict(response.headers)}

    def control(self, action, *args):
        if action not in self._controls: raise JourneyFailure("target-control-unavailable")
        return self._controls[action](*args)


class Runner:
    def __init__(self, pack: JourneyPack, lane: TargetLane, inputs: dict, *, timeout=180,
                 pause=time.sleep, clock=time.monotonic):
        self.pack = validate_pack(pack.raw)
        self.raw = self.pack.raw
        if not isinstance(lane, TargetLane): raise PackError("replay requires a target capability")
        lane.preflight(self.pack)
        if not isinstance(inputs, dict) or set(inputs) != set(self.raw["inputs"]): raise PackError("wrong pack inputs")
        for name, kind in self.raw["inputs"].items():
            v = inputs[name]
            if kind == "identifier" and (not isinstance(v, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,60}", v)): raise PackError("invalid identifier input")
            if kind == "integer" and type(v) is not int: raise PackError("invalid integer input")
            if kind == "string" and (not isinstance(v, str) or len(v) > 4000): raise PackError("invalid string input")
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 <= timeout <= 3600: raise PackError("invalid timeout")
        self.lane, self.timeout, self.pause, self.clock = lane, timeout, pause, clock
        self.inputs = dict(inputs); self.state = {}
        self.budget = 100000
        self.cleanup_budget = 10000
        self._cleanup_depth = 0
        self._budget_lock = threading.Lock()
        for name, value in self.raw["state"].items(): self.state[name] = self.value(value, {})

    def _spend(self):
        with self._budget_lock:
            if self._cleanup_depth:
                self.cleanup_budget -= 1
                require(self.cleanup_budget >= 0, "cleanup-budget-exhausted")
            else:
                self.budget -= 1
                require(self.budget >= 0, "execution-budget-exhausted")

    def value(self, expression, env):
        self._spend()
        try:
            return self._value(expression, env)
        except (KeyError, IndexError, TypeError, ValueError, OverflowError, RecursionError):
            raise JourneyFailure("observation-or-expression-invalid") from None

    def _value(self, expression, env):
        if isinstance(expression, list): return [self.value(v, env) for v in expression]
        if not isinstance(expression, dict): return expression
        if "$ref" in expression:
            parts = expression["$ref"].split(".")
            values = {**self.inputs, **self.state, **env}
            value = values[parts[0]]
            for part in parts[1:]: value = value[int(part)] if isinstance(value, list) else value[part]
            return value
        for key in ("$map", "$filter"):
            if key in expression:
                s = expression[key]; items = self.value(s["over"], env)
                require(isinstance(items, list) and len(items) <= 500, "expression-collection-invalid")
                if key == "$map": return [self.value(s["value"], {**env, s["as"]: item}) for item in items]
                return [item for item in items if self.boolean(self.value(s["value"], {**env, s["as"]: item}))]
        if "$op" not in expression: return {k: self.value(v, env) for k, v in expression.items()}
        op, args = expression["$op"], expression["args"]
        if op == "and": return all(self.boolean(self.value(a, env)) for a in args)
        if op == "or": return any(self.boolean(self.value(a, env)) for a in args)
        a = [self.value(v, env) for v in args]
        if op == "eq": return _equal(a[0], a[1])
        if op == "ne": return not (_equal(a[0], a[1]))
        if op in {"lt", "le", "gt", "ge", "add", "sub"}:
            require(all(type(v) is int for v in a), "integer-expression-required")
            if op == "lt": return a[0] < a[1]
            if op == "le": return a[0] <= a[1]
            if op == "gt": return a[0] > a[1]
            if op == "ge": return a[0] >= a[1]
            if op == "add": return a[0] + a[1]
            return a[0] - a[1]
        if op == "get": return a[0][a[1]]
        if op == "in":
            require(isinstance(a[1], list), "membership-list-required")
            return any(_equal(a[0], item) for item in a[1])
        if op == "len": return len(a[0])
        if op == "int":
            require(type(a[0]) is int or (isinstance(a[0], str) and re.fullmatch(r"-?[0-9]{1,20}", a[0]) is not None), "integer-expression-required")
            return int(a[0])
        if op == "str": return str(a[0])
        if op == "hash": return hashed(a[0])
        if op == "json":
            def pairs(items):
                result = {}
                for key, value in items:
                    if key in result: raise ValueError("duplicate response key")
                    result[key] = value
                return result
            def unsupported_number(_):
                raise ValueError("use exact integer units or decimal strings")
            try:
                value = json.loads(a[0]["body"], object_pairs_hook=pairs,
                                   parse_float=unsupported_number, parse_constant=unsupported_number)
                _json_tree(value)
                return value
            except (ValueError, UnicodeError, RecursionError):
                raise JourneyFailure("response-json-invalid") from None
        if op == "text":
            try: return a[0]["body"].decode("utf-8")
            except UnicodeError: raise JourneyFailure("response-text-invalid") from None
        if op == "not": return not self.boolean(a[0])
        if op == "sort": return sorted(a[0])
        if op == "sum":
            require(all(type(x) is int for x in a[0]), "integer-expression-required")
            return sum(a[0])
        if op == "unique": return len(a[0]) == len(set(a[0]))
        if op == "concat": return "".join(str(v) for v in a)
        if op == "append":
            require(isinstance(a[0], list) and len(a[0]) < 500, "expression-collection-invalid")
            return a[0] + [a[1]]
        if op == "location_id":
            path = urlsplit(a[0]).path
            require(path.startswith(a[1]) and re.fullmatch(r"[0-9]{1,20}", path[len(a[1]):]) is not None, "response-location-invalid")
            return int(path[len(a[1]):])
        if op == "message_id": return "ly-" + hashlib.sha256(f"{a[0]}:{a[1]}".encode()).hexdigest()[:48]
        if op == "is_int": return type(a[0]) is int
        if op == "is_object": return isinstance(a[0], dict)
        if op == "is_list": return isinstance(a[0], list)
        if op == "is_sha256": return isinstance(a[0], str) and re.fullmatch(r"[0-9a-f]{64}", a[0]) is not None
        if op == "digits": return type(a[1]) is int and 1 <= a[1] <= 20 and isinstance(a[0], str) and len(a[0]) == a[1] and a[0].isascii() and a[0].isdigit()
        if op == "lookup": return a[0].get(a[1], a[2])
        if op == "merge": return {**a[0], **a[1]}
        if op == "replace_at":
            result = list(a[0]); result[a[1]] = a[2]; return result
        if op == "sort_by": return sorted(a[0], key=lambda row: tuple(row[k] for k in a[1]))
        if op == "safe_text":
            return isinstance(a[0], str) and 0 < len(a[0].strip()) <= 4000 and re.search(
                r"(?i)(BEGIN (RSA )?PRIVATE KEY|authorization\s*:\s*bearer|(?:password|token|secret|api[_ -]?key)\s*[:=]\s*\S+)", a[0]) is None
        raise JourneyFailure("unsupported-expression")

    @staticmethod
    def boolean(value):
        require(type(value) is bool, "boolean-expression-required")
        return value

    def call(self, name, args=None):
        if name not in self.raw["macros"]: raise PackError("unknown macro")
        macro = self.raw["macros"][name]
        if set(args or {}) != set(macro["params"]): raise PackError("wrong macro arguments")
        env = dict(args or {})
        self.steps(macro["steps"], env)
        return self.value(macro["return"], env)

    def steps(self, steps, env):
        for step in steps:
            self._spend()
            op = step["op"]
            val = lambda x: self.value(x, env)
            result = None
            if op == "set":
                (self.state if step.get("state") else env)[step["name"]] = val(step["value"])
            elif op == "assert": require(self.boolean(val(step["test"])), step["code"])
            elif op == "request":
                path = step["path"]
                for k, v in val(step.get("params", {})).items():
                    require(type(v) in (str, int) and str(v) not in {"", ".", ".."} and len(str(v)) <= 200,
                            "path-parameter-invalid")
                    # Slash, percent and backslash cannot escape a path segment.
                    require(re.fullmatch(r"[A-Za-z0-9_-]+", str(v)) is not None, "path-parameter-invalid")
                    path = path.replace("{" + k + "}", quote(str(v), safe=""))
                query = val(step.get("query", {}))
                require(all(type(v) in (str, int) and len(str(v)) <= 4000 for v in query.values()), "query-value-invalid")
                if query: path += "?" + urlencode(query)
                headers = val(step.get("headers", {}))
                require(all(isinstance(v, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,200}", v) for v in headers.values()), "header-value-invalid")
                body = val(step.get("body"))
                require(len(canonical(body)) <= MAX_BYTES, "request-body-too-large")
                try: result = self.lane.request(step["service"], step["method"], path, step.get("role"), body, headers)
                except JourneyFailure as exc:
                    if str(exc) != step.get("allow_error"): raise
                    result = {"status": None, "body": b"", "headers": {}, "error": str(exc)}
            elif op == "control":
                args = [step["service"]] if step["action"] in {"stop", "start", "restart", "crash_stop"} else []
                if step["action"] == "queue": args = [step["service"], val(step["message"])]
                result = self.lane.control(step["action"], *args)
            elif op == "call": result = self.call(step["macro"], val(step["args"]))
            elif op == "if": self.steps(step["then"] if self.boolean(val(step["test"])) else step["else"], env)
            elif op == "each":
                items = val(step["over"])
                require(isinstance(items, list) and len(items) <= step["max_items"], "loop-bound-exceeded")
                for item in items:
                    env[step["as"]] = item
                    self.steps(step["steps"], env)
                env.pop(step["as"], None)
            elif op == "poll":
                deadline = self.clock() + self.timeout
                for attempt in range(step["attempts"]):
                    self.steps(step["steps"], env)
                    if self.boolean(val(step["until"])): break
                    require(attempt + 1 < step["attempts"] and self.clock() < deadline, step["code"])
                    self.pause(min(1, max(0, deadline - self.clock())))
            elif op == "parallel":
                with concurrent.futures.ThreadPoolExecutor(max_workers=len(step["calls"])) as pool:
                    futures = [pool.submit(self.call, s["macro"], val(s["args"])) for s in step["calls"]]
                    result = [f.result() for f in futures]
            elif op == "ensure":
                try: self.steps(step["steps"], env)
                finally:
                    self._cleanup_depth += 1
                    try: self.steps(step["finally"], env)
                    finally: self._cleanup_depth -= 1
            if "save" in step: env[step["save"]] = result

    def journey(self, identifier):
        for j in self.raw["journeys"]:
            if j["id"] == identifier: return self.call(j["macro"], self.value(j["args"], {}))
        raise PackError("unknown journey")


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="Validate and plan service/API journeys without accessing a runtime")
    parser.add_argument("action", choices=["validate", "plan"])
    parser.add_argument("pack", type=Path)
    args = parser.parse_args(argv)
    try:
        pack = load(args.pack)
        print(json.dumps(plan(pack) if args.action == "plan" else {"pack_id": pack.pack_id, "status": "valid", "sha256": pack.sha256}, indent=2))
        return 0
    except (PackError, OSError) as exc:
        print(f"Pack refused: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
