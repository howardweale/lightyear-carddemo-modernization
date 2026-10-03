"""One operator-owned task, durable budgets and signed replayable evidence."""

import base64
import json
import os
import secrets
import threading
import uuid
from pathlib import Path
from lightyear_control_tower.decisions import canonical, digest, verify_envelope, ZERO
from lightyear_control_tower.status_export import atomic_new, StatusWriter, read_exports
from lightyear_mainframe.zos_evidence import Signer, initialize_key, now, read_json
from lightyear_mainframe import zos_evidence
from lightyear_mainframe.zos_bridge import replay as replay_intcalc
from lightyear_toolkit.workspace import ARTIFACT_LIMIT, sha
from .evaluation import evaluate, summarize
from .sandbox import require_isolation, require_trusted_installation

METHODS = {
    "get_task": set(),
    "get_budget": set(),
    "submit_candidate": {"request_id", "artifact"},
    "get_verdict": {"attempt_id"},
    "get_receipt": {"attempt_id"},
    "propose_normalization": {"attempt_id", "dataset", "field"},
}


def inventory(folder):
    result = {}
    for path in sorted(Path(folder).rglob("*")):
        if path.is_symlink():
            raise ValueError("evaluation-link-refused")
        if path.is_file():
            result[path.relative_to(folder).as_posix()] = sha(path.read_bytes())
    return result


def implementation():
    source = Path(__file__).resolve().parents[1]
    return {
        str(p.relative_to(source)): sha(p.read_bytes())
        for package in (
            "lightyear_judge",
            "lightyear_toolkit",
            "lightyear_mainframe",
            "lightyear_control_tower",
        )
        for p in sorted((source / package).glob("*.py"))
    }


def initialize(root, config):
    root = Path(root).absolute()
    root.mkdir(mode=0o700)
    require_isolation(root, config["agent_uid"])
    require_trusted_installation(config["agent_uid"])
    require_isolation(Path(config["evaluation"]), config["agent_uid"])
    if (
        not 1 <= config.get("submissions", 5) <= 100
        or not 5 <= config.get("build_minutes", 25) <= 500
    ):
        raise ValueError("operator-budget-invalid")
    if not Path(config["evaluation"]).resolve().is_relative_to(root.parent.resolve()):
        raise ValueError("evaluation-must-be-in-private-parent")
    config = {
        **config,
        "schema": "lightyear-verify-task/1",
        "submissions": config.get("submissions", 5),
        "build_minutes": config.get("build_minutes", 25),
        "evaluation_inventory": inventory(config["evaluation"]),
        "implementation": implementation(),
    }
    initialize_key(root / "authority.pem")
    signer = Signer(root / "authority.pem")
    atomic_new(root / "task.json", signer.sign(config))
    with (root / "token").open("x") as f:
        f.write(secrets.token_urlsafe(32))
    return root / "authority.public.pem"


def journal(root, key):
    previous, events = ZERO, []
    for i, path in enumerate(sorted((root / "journal").glob("*.json")), 1):
        event = read_json(path)
        if (
            path.name != f"{i:06}.json"
            or not verify_envelope(event, key)
            or event["sequence"] != i
            or event["previous_sha256"] != previous
        ):
            raise ValueError("journal-replay-failed")
        previous = event["content_sha256"]
        events.append(event)
    return events


class Judge:
    def __init__(self, root, *, task):
        import fcntl

        self.root = Path(root).absolute()
        self.signer = Signer(self.root / "authority.pem")
        self.config = read_json(self.root / "task.json")
        if (
            not verify_envelope(self.config, self.signer.public)
            or self.config["task_id"] != task
        ):
            raise ValueError("task-binding-failed")
        if self.config["implementation"] != implementation():
            raise ValueError("judge-implementation-changed")
        require_isolation(self.root, self.config["agent_uid"])
        require_trusted_installation(self.config["agent_uid"])
        self.lockfile = (self.root / "service.lock").open("a+b")
        fcntl.flock(self.lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.lock = threading.RLock()
        self.events = journal(self.root, self.signer.public)
        self.token = (self.root / "token").read_text().strip()
        self.exports = Path(self.config["exports"])
        self.bindings = {"task": self.config["content_sha256"]}
        if self.exports.exists() and list(self.exports.iterdir()):
            last = read_exports(
                self.exports,
                self.signer.public,
                task,
                self.bindings,
                scope=task,
                profile="lightyear-verify",
            )
            self.writer = object.__new__(StatusWriter)
            self.writer.directory, self.writer.sign, self.writer.key = (
                self.exports,
                self.signer.sign,
                self.signer.public,
            )
            self.writer.scope, self.writer.profile, self.writer.validator = (
                task,
                "lightyear-verify",
                None,
            )
            self.writer.sequence, self.writer.previous = (
                last["sequence"],
                last["content_sha256"],
            )
        else:
            self.writer = StatusWriter(
                self.exports,
                self.signer.sign,
                self.signer.public,
                scope=task,
                profile="lightyear-verify",
            )
        # A crash after reservation consumes the attempt; never rerun it on reconnect.
        for attempt in self.accepted():
            if not (
                self.root / "receipts" / (attempt["attempt_id"] + ".json")
            ).exists():
                self.finish(attempt, "indeterminate", [], [], "interrupted")
            elif not any(
                e["kind"] == "finished" and e["attempt_id"] == attempt["attempt_id"]
                for e in self.events
            ):
                self.append(
                    "finished",
                    attempt_id=attempt["attempt_id"],
                    receipt_sha256=self.receipt(attempt["attempt_id"])[
                        "content_sha256"
                    ],
                )
        self.export()

    def close(self):
        self.lockfile.close()

    def append(self, kind, **body):
        event = self.signer.sign(
            dict(
                schema="lightyear-verify-event/1",
                sequence=len(self.events) + 1,
                previous_sha256=(
                    self.events[-1]["content_sha256"] if self.events else ZERO
                ),
                task=self.config["content_sha256"],
                at_utc=now(),
                kind=kind,
                **body,
            )
        )
        atomic_new(self.root / "journal" / f'{event["sequence"]:06}.json', event)
        self.events.append(event)
        return event

    def accepted(self):
        return [e for e in self.events if e["kind"] == "accepted"]

    def budget(self):
        used = len(self.accepted())
        return {
            "submissions_left": max(0, self.config["submissions"] - used),
            "build_minutes_left": max(0, self.config["build_minutes"] - used * 5),
        }

    def receipt(self, attempt_id):
        if attempt_id not in {e["attempt_id"] for e in self.accepted()}:
            raise ValueError("attempt-unavailable")
        result = read_json(self.root / "receipts" / (attempt_id + ".json"))
        if not verify_envelope(result, self.signer.public):
            raise ValueError("receipt-integrity-failed")
        return result

    def finish(self, attempt, verdict, diagnostics, evidence, status="completed"):
        evidence_path = (
            self.root / "private-evidence" / (attempt["attempt_id"] + ".json")
        )
        if evidence_path.exists():
            if status != "interrupted":
                raise ValueError("evidence-already-finalized")
            evidence = read_json(evidence_path)
        else:
            atomic_new(evidence_path, evidence)
        receipt = self.signer.sign(
            dict(
                schema="lightyear-verify-receipt/1",
                task_sha256=self.config["content_sha256"],
                attempt_id=attempt["attempt_id"],
                attempt_number=attempt["attempt_number"],
                submission_limit=self.config["submissions"],
                artifact_sha256=attempt["artifact_sha256"],
                verdict=verdict,
                diagnostics=diagnostics,
                status=status,
                evidence_sha256=digest(evidence),
                budget=self.budget(),
                normalization="verified-tower-decisions-only",
                review="operator review; not independent",
                evaluation="held-out",
                sandbox="linux-bubblewrap",
            )
        )
        atomic_new(self.root / "receipts" / (attempt["attempt_id"] + ".json"), receipt)
        self.append(
            "finished",
            attempt_id=attempt["attempt_id"],
            receipt_sha256=receipt["content_sha256"],
        )
        return receipt

    def export(self, active=None):
        receipts = [
            self.receipt(e["attempt_id"])
            for e in self.accepted()
            if (self.root / "receipts" / (e["attempt_id"] + ".json")).exists()
        ]
        used = len(self.accepted())
        seen, repeated = set(), False
        for r in receipts:
            h = digest(r["diagnostics"])
            repeated |= bool(r["diagnostics"] and h in seen)
            seen.add(h)
        exhausted = (
            self.budget()["submissions_left"] == 0
            or self.budget()["build_minutes_left"] < 5
        )
        stopped = any(r["status"] != "completed" for r in receipts)
        self.writer.emit(
            dict(
                campaign_id=self.config["task_id"],
                at_utc=now(),
                bindings=self.bindings,
                state=(
                    "running"
                    if active
                    else "stopped" if stopped else "completed" if exhausted else "ready"
                ),
                active_trial={"id": active, "phase": "evaluation"} if active else None,
                fixture=self.config.get("fixture", False),
                limits={
                    "submissions": self.config["submissions"],
                    "build_minutes": self.config["build_minutes"],
                },
                used={"submissions": used, "build_minutes": used * 5},
                details={
                    "submissions": used,
                    "refusals": sum(e["kind"] == "refused" for e in self.events),
                    "verdicts": [
                        {
                            "id": r["attempt_id"],
                            "verdict": r["verdict"],
                            "receipt_sha256": r["content_sha256"],
                        }
                        for r in receipts
                    ],
                    "budget_exhausted": exhausted,
                    "repeated_diagnostics": repeated,
                },
            )
        )

    def invoke(self, method, args):
        with self.lock:
            try:
                if (
                    method not in METHODS
                    or not isinstance(args, dict)
                    or set(args) != METHODS[method]
                ):
                    raise ValueError("request-invalid")
                # Hash untrusted query arguments, never journal echoed values or artifact bodies.
                self.append("query", method=method, arguments_sha256=digest(args))
                if method == "get_task":
                    result = {
                        "work_order": "Implement CardDemo CBACT04C INTCALC in Java; submit a runnable JAR.",
                        "task_id": self.config["task_id"],
                        "public": self.config["public_task"],
                        "budget": self.budget(),
                        "rules": "Exact existing INTCALC comparator; normalization only by verified human Tower decisions.",
                    }
                elif method == "get_budget":
                    result = self.budget()
                elif method == "get_receipt":
                    result = {"receipt": self.receipt(args["attempt_id"])}
                elif method == "get_verdict":
                    r = self.receipt(args["attempt_id"])
                    result = {
                        "verdict": r["verdict"],
                        "diagnostics": r["diagnostics"],
                        "budget": self.budget(),
                        "receipt_sha256": r["content_sha256"],
                    }
                elif method == "propose_normalization":
                    result = self.propose(**args)
                else:
                    result = self.submit(**args)
                return {"ok": True, **result}
            except Exception:
                self.append(
                    "refused", method=method if method in METHODS else "unknown"
                )
                self.export()
                return {
                    "ok": False,
                    "error": "request-refused",
                    "budget": self.budget(),
                }

    def submit(self, request_id, artifact):
        if str(uuid.UUID(request_id)) != request_id:
            raise ValueError("request-id-invalid")
        if not isinstance(artifact, str) or len(artifact) > (
            ARTIFACT_LIMIT * 4 // 3 + 8
        ):
            raise ValueError("artifact-too-large")
        raw = base64.b64decode(artifact, validate=True)
        if not raw.startswith(b"PK") or len(raw) > ARTIFACT_LIMIT:
            raise ValueError("jar-required")
        hashed = sha(raw)
        previous = [e for e in self.accepted() if e["request_id"] == request_id]
        if previous:
            if previous[0]["artifact_sha256"] != hashed:
                raise ValueError("idempotency-conflict")
            return {"attempt_id": previous[0]["attempt_id"]}
        if (
            self.budget()["submissions_left"] < 1
            or self.budget()["build_minutes_left"] < 5
        ):
            raise ValueError("budget-exhausted")
        if any(
            self.receipt(e["attempt_id"])["status"] != "completed"
            for e in self.accepted()
        ):
            raise ValueError("operator-review-required")
        if inventory(self.config["evaluation"]) != self.config["evaluation_inventory"]:
            raise ValueError("evaluation-changed")
        attempt_id = "attempt-" + uuid.uuid4().hex
        path = self.root / "artifacts" / (attempt_id + ".jar")
        path.parent.mkdir(exist_ok=True)
        with path.open("xb") as f:
            f.write(raw)
        attempt = self.append(
            "accepted",
            attempt_id=attempt_id,
            attempt_number=len(self.accepted()) + 1,
            request_id=request_id,
            artifact_sha256=hashed,
        )
        self.export(active=attempt_id)
        try:
            outcome, ds, runs = evaluate(
                self.root,
                self.config["evaluation"],
                path,
                self.signer,
                review_root=self.config["tower_workspace"],
            )
            self.finish(attempt, outcome, ds, runs)
        except Exception:
            self.finish(attempt, "indeterminate", [], [], "equipment-failure")
        self.export()
        return {"attempt_id": attempt_id}

    def propose(self, attempt_id, dataset, field):
        from lightyear_mainframe.zos_bindings import load_bindings, dataset_binding
        from lightyear_control_tower.status_export import atomic_new

        receipt = self.receipt(attempt_id)
        if not any(
            d["dataset"] == dataset and d["field"] == field
            for d in receipt["diagnostics"]
        ):
            raise ValueError("proposal-unbound")
        step, dd = dataset.split("/")
        if (
            field
            not in dataset_binding(load_bindings(), "INTCALC", step, dd)[
                "timestamp_fields"
            ]
        ):
            raise ValueError("normalization-not-allowed")
        rule = {
            "schema": "verify-normalization-draft/1",
            "dataset": dataset,
            "field": field,
            "receipt_sha256": receipt["content_sha256"],
            "applied": False,
        }
        rule_hash = digest(rule)
        mirror = "evidence/verify/" + rule_hash + ".json"
        tower = Path(self.config["tower_workspace"])
        if not (tower / mirror).exists():
            atomic_new(tower / mirror, rule)
        body = {
            "schema": "tower-request/1",
            "scope": self.config["task_id"],
            "id": "normalization-" + rule_hash,
            "kind": "verify-normalization",
            "bound": {"rule": rule_hash},
            "evidence": {"rule": mirror},
            "summary": "Timestamp difference: draft for human review; no rule is applied.",
            "proposed_by": "lightyear-verify",
            "authored_by": ["lightyear-verify"],
            "workload": "workload:carddemo-intcalc",
        }
        target = (
            tower
            / "work/control-tower/requests"
            / self.config["task_id"]
            / (body["id"] + ".json")
        )
        if not target.exists():
            atomic_new(target, body)
        return {"request_id": body["id"], "status": "draft", "applied": False}


def replay(root, key, expected_head):
    root = Path(root)
    config = read_json(root / "task.json")
    if not verify_envelope(config, key):
        raise ValueError("task-signature-failed")
    if config["implementation"] != implementation():
        raise ValueError("judge-implementation-changed")
    events = journal(root, key)
    if not events or events[-1]["content_sha256"] != expected_head:
        raise ValueError("journal-head-mismatch")
    zos_evidence.ARRIVALS = root / "arrivals"
    count, attempts, ids, requests = 0, 0, set(), set()
    for event in events:
        if event["task"] != config["content_sha256"]:
            raise ValueError("journal-task-mismatch")
        if event["kind"] != "accepted":
            continue
        attempts += 1
        if (
            event["attempt_number"] != attempts
            or event["attempt_id"] in ids
            or event["request_id"] in requests
            or attempts > config["submissions"]
            or attempts * 5 > config["build_minutes"]
        ):
            raise ValueError("attempt-budget-or-identity-invalid")
        ids.add(event["attempt_id"])
        requests.add(event["request_id"])
        receipt = read_json(root / "receipts" / (event["attempt_id"] + ".json"))
        runs = read_json(root / "private-evidence" / (event["attempt_id"] + ".json"))
        if (
            not verify_envelope(receipt, key)
            or receipt["evidence_sha256"] != digest(runs)
            or receipt["artifact_sha256"] != event["artifact_sha256"]
        ):
            raise ValueError("receipt-replay-failed")
        finished = [
            e
            for e in events
            if e["kind"] == "finished" and e["attempt_id"] == event["attempt_id"]
        ]
        if (
            len(finished) != 1
            or finished[0]["receipt_sha256"] != receipt["content_sha256"]
            or receipt["task_sha256"] != config["content_sha256"]
            or receipt["attempt_id"] != event["attempt_id"]
            or receipt["attempt_number"] != attempts
        ):
            raise ValueError("receipt-journal-binding-failed")
        if (
            sha((root / "artifacts" / (event["attempt_id"] + ".jar")).read_bytes())
            != receipt["artifact_sha256"]
        ):
            raise ValueError("artifact-changed")
        for run in runs:
            if not Path(run["path"]).resolve().is_relative_to(root.resolve()):
                raise ValueError("replay-path-refused")
            replay_intcalc(run["path"], key)
            if (
                read_json(Path(run["path"]) / "candidate/execution.json")["jar_sha256"]
                != event["artifact_sha256"]
            ):
                raise ValueError("native-artifact-binding-failed")
            count += 1
        if receipt["status"] == "completed":
            if not runs or summarize(runs) != (
                receipt["verdict"],
                receipt["diagnostics"],
            ):
                raise ValueError("closed-result-replay-failed")
        elif (
            receipt["status"] not in {"interrupted", "equipment-failure"}
            or receipt["verdict"] != "indeterminate"
            or receipt["diagnostics"]
        ):
            raise ValueError("incomplete-result-invalid")
    return {
        "status": "verified",
        "attempts": sum(e["kind"] == "accepted" for e in events),
        "native_verdicts_replayed": count,
        "journal_head_sha256": expected_head,
        "model_calls": 0,
    }
