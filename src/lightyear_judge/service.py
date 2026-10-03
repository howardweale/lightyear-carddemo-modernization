"""One operator-owned task, durable budgets and signed replayable evidence."""

import base64
import json
import os
import secrets
import threading
import uuid
import time
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from lightyear_control_tower.decisions import canonical, digest, verify_envelope, ZERO
from lightyear_control_tower.status_export import atomic_new, StatusWriter, read_exports
from lightyear_mainframe.zos_evidence import Signer, initialize_key, now, read_json
from lightyear_mainframe import zos_evidence
from lightyear_mainframe.zos_bridge import replay as replay_intcalc
from lightyear_toolkit.workspace import ARTIFACT_LIMIT, sha
from .evaluation import summarize
from .policy import disclosure, project, fingerprint
from .ledger import Ledger
from .review import verify_review, request_review
from .sandbox import require_isolation, require_trusted_installation

METHODS = {
    "get_task": set(),
    "get_budget": set(),
    "submit_candidate": {"request_id", "artifact"},
    "get_verdict": {"attempt_id"},
    "get_receipt": {"attempt_id"},
    "propose_normalization": {"attempt_id", "dataset", "field"},
}


def public_body(receipt):
    return {
        k: receipt[k]
        for k in (
            "schema",
            "task_sha256",
            "attempt_id",
            "attempt_number",
            "submission_limit",
            "artifact_sha256",
            "verdict",
            "diagnostics",
            "status",
            "budget",
            "review",
            "disclosure_mode",
        )
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
    return fingerprint()


def initialize(root, config):
    root = Path(root).absolute()
    root.mkdir(mode=0o700)
    require_isolation(root, config["agent_uid"])
    require_trusted_installation(config["agent_uid"])
    require_isolation(Path(config["evaluation"]), config["agent_uid"])
    if "build_minutes" in config:
        raise ValueError("use-attempt-slots-not-build-minutes")
    if (
        type(config.get("submissions", 5)) is not int
        or not 1 <= config.get("submissions", 5) <= 100
        or type(config.get("attempt_slots", 5)) is not int
        or not 1 <= config.get("attempt_slots", 5) <= 100
    ):
        raise ValueError("operator-budget-invalid")
    if not Path(config["evaluation"]).resolve().is_relative_to(root.parent.resolve()):
        raise ValueError("evaluation-must-be-in-private-parent")
    config = {
        **config,
        "schema": "lightyear-verify-task/1",
        "submissions": config.get("submissions", 5),
        "attempt_slots": config.get("attempt_slots", 5),
        "disclosure_mode": disclosure(config),
        "evaluation_inventory": inventory(config["evaluation"]),
        "implementation": implementation(),
    }
    config["evaluation_inventory_sha256"] = digest(config["evaluation_inventory"])
    ledger = Ledger(
        config["evaluation_inventory_sha256"],
        min(config["submissions"], config["attempt_slots"]),
        tower_key=config.get("tower_public_key", ""),
    )
    config["inventory_ledger_public_key"] = ledger.signer.public.decode()
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
        self.ledger = Ledger(
            self.config["evaluation_inventory_sha256"], self.config["attempt_slots"]
        )
        if (
            self.ledger.signer.public.decode()
            != self.config["inventory_ledger_public_key"]
        ):
            raise ValueError("inventory-authority-changed")
        self.pool = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="verify-finalizer"
        )
        self.active = None
        self.ingress_counts = {}
        self.ingress_tick = time.monotonic()
        self.ingress_used = 0
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
                self.write_public_receipt(self.receipt(attempt["attempt_id"]))
                self.append(
                    "finished",
                    attempt_id=attempt["attempt_id"],
                    receipt_sha256=self.receipt(attempt["attempt_id"])[
                        "content_sha256"
                    ],
                )
        for attempt in self.accepted():
            receipt = self.receipt(attempt["attempt_id"])
            self.write_public_receipt(receipt)
            if receipt["status"] != "completed":
                request_review(
                    self.root,
                    Path(self.config["tower_workspace"]),
                    task,
                    attempt["attempt_id"],
                )
        self.consume_decisions()
        self.export()

    def close(self):
        self.pool.shutdown(wait=True)
        with self.lock:
            self.flush_ingress(force=True)
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
        limit, cumulative = self.ledger.budget()
        remaining = max(
            0,
            min(
                self.config["submissions"] - used,
                self.config["attempt_slots"] - used,
                limit - cumulative,
            ),
        )
        return {
            "submissions_left": remaining,
            "attempt_slots_left": remaining,
            "inventory_attempts_used": cumulative,
            "inventory_attempt_limit": limit,
        }

    def flush_ingress(self, force=False):
        if force or time.monotonic() - self.ingress_tick >= 60:
            if self.ingress_counts:
                self.append("ingress-summary", counts=self.ingress_counts)
            self.ingress_counts = {}
            self.ingress_used = 0
            self.ingress_tick = time.monotonic()

    def ingress(self, kind):
        with self.lock:
            self.flush_ingress()
            # Fixed cardinality, saturating counters, at most one summary/minute.
            if kind not in {"unauthorized", "invalid", "query", "throttled"}:
                kind = "invalid"
            self.ingress_counts[kind] = min(
                2**31 - 1, self.ingress_counts.get(kind, 0) + 1
            )
            self.ingress_used = min(2**31 - 1, self.ingress_used + 1)
            return self.ingress_used <= 120

    def public_receipt(self, attempt_id):
        private = self.receipt(attempt_id)
        value = read_json(self.root / "public-receipts" / (attempt_id + ".json"))
        if not verify_envelope(value, self.signer.public) or {
            k: v for k, v in value.items() if k not in {"signature", "content_sha256"}
        } != public_body(private):
            raise ValueError("public-receipt-invalid")
        return value

    def receipt(self, attempt_id):
        if attempt_id not in {e["attempt_id"] for e in self.accepted()}:
            raise ValueError("attempt-unavailable")
        result = read_json(self.root / "receipts" / (attempt_id + ".json"))
        if not verify_envelope(result, self.signer.public):
            raise ValueError("receipt-integrity-failed")
        return result

    def finish(self, attempt, verdict, diagnostics, evidence, status="completed"):
        diagnostics = project(diagnostics, self.config["disclosure_mode"])
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
                disclosure_mode=self.config["disclosure_mode"],
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
        self.write_public_receipt(receipt)
        self.append(
            "finished",
            attempt_id=attempt["attempt_id"],
            receipt_sha256=receipt["content_sha256"],
        )
        if status != "completed":
            request_review(
                self.root,
                Path(self.config["tower_workspace"]),
                self.config["task_id"],
                attempt["attempt_id"],
            )
        return receipt

    def write_public_receipt(self, receipt):
        public = self.signer.sign(public_body(receipt))
        path = self.root / "public-receipts" / (receipt["attempt_id"] + ".json")
        if path.exists():
            if read_json(path) != public:
                raise ValueError("public-receipt-binding-failed")
        else:
            atomic_new(path, public)

    def consume_decisions(self):
        applied = {
            e["receipt_sha256"] for e in self.events if e["kind"] == "operator-decision"
        }
        for path in sorted((self.root / "operator-decisions").glob("*.json")):
            bundle = read_json(path)
            if not verify_envelope(bundle, self.signer.public):
                raise ValueError("operator-import-invalid")
            decision = verify_review(self.root, self.config, bundle)
            if bundle["receipt_sha256"] not in applied:
                self.append(
                    "operator-decision",
                    receipt_sha256=bundle["receipt_sha256"],
                    outcome=decision["outcome"],
                    bundle=bundle,
                )
                applied.add(bundle["receipt_sha256"])

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
            or self.budget()["attempt_slots_left"] < 1
        )
        resolved = {
            e["receipt_sha256"] for e in self.events if e["kind"] == "operator-decision"
        }
        stopped = any(
            r["status"] != "completed" and r["content_sha256"] not in resolved
            for r in receipts
        )
        self.writer.emit(
            dict(
                campaign_id=self.config["task_id"],
                at_utc=now(),
                bindings=self.bindings,
                state=(
                    "running"
                    if active
                    else "paused" if stopped else "completed" if exhausted else "ready"
                ),
                active_trial={"id": active, "phase": "evaluation"} if active else None,
                fixture=self.config.get("fixture", False),
                limits={
                    "submissions": self.config["submissions"],
                    "attempt_slots": self.config["attempt_slots"],
                },
                used={"submissions": used, "attempt_slots": used},
                details={
                    "submissions": used,
                    "refusals": sum(
                        e.get("counts", {}).get("invalid", 0)
                        + e.get("counts", {}).get("unauthorized", 0)
                        for e in self.events
                        if e["kind"] == "ingress-summary"
                    )
                    + self.ingress_counts.get("invalid", 0)
                    + self.ingress_counts.get("unauthorized", 0),
                    "verdicts": [
                        {
                            "id": r["attempt_id"],
                            "verdict": r["verdict"],
                            "receipt_sha256": self.public_receipt(r["attempt_id"])[
                                "content_sha256"
                            ],
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
                if method == "get_task":
                    result = {
                        "work_order": "Implement CardDemo CBACT04C INTCALC in Java; submit a runnable JAR.",
                        "task_id": self.config["task_id"],
                        "disclosure_mode": self.config["disclosure_mode"],
                        "public": self.config["public_task"],
                        "budget": self.budget(),
                        "rules": "Exact existing INTCALC comparator; normalization only by verified human Tower decisions.",
                    }
                elif method == "get_budget":
                    result = self.budget()
                elif method == "get_receipt":
                    result = {"receipt": self.public_receipt(args["attempt_id"])}
                elif method == "get_verdict":
                    if args["attempt_id"] == self.active:
                        return {
                            "ok": True,
                            "verdict": "pending",
                            "attempt_id": self.active,
                        }
                    r = self.public_receipt(args["attempt_id"])
                    result = {
                        "verdict": r["verdict"],
                        "diagnostics": r["diagnostics"],
                        "budget": self.budget(),
                        "receipt_sha256": self.public_receipt(r["attempt_id"])[
                            "content_sha256"
                        ],
                    }
                elif method == "propose_normalization":
                    result = self.propose(**args)
                else:
                    result = self.submit(**args)
                return {"ok": True, **result}
            except Exception:
                self.ingress("invalid")
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
            or self.budget()["attempt_slots_left"] < 1
        ):
            raise ValueError("budget-exhausted")
        self.consume_decisions()
        if self.active or self.unresolved():
            raise ValueError("operator-review-required")
        if self.config["implementation"] != implementation():
            raise ValueError("judge-implementation-changed")
        if inventory(self.config["evaluation"]) != self.config["evaluation_inventory"]:
            raise ValueError("evaluation-changed")
        attempt_id = "attempt-" + uuid.uuid4().hex
        path = self.root / "artifacts" / (attempt_id + ".jar")
        path.parent.mkdir(exist_ok=True)
        with path.open("xb") as f:
            f.write(raw)
        reservation = self.ledger.reserve(self.config["content_sha256"], attempt_id)
        attempt = self.append(
            "accepted",
            inventory_reservation=reservation,
            attempt_id=attempt_id,
            attempt_number=len(self.accepted()) + 1,
            request_id=request_id,
            artifact_sha256=hashed,
        )
        self.active = attempt_id
        self.export(active=attempt_id)
        self.pool.submit(self.execute, attempt)
        return {"attempt_id": attempt_id, "verdict": "pending"}

    def execute(self, attempt):
        attempt_id = attempt["attempt_id"]
        try:
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "lightyear_judge.worker",
                    str(self.root),
                    attempt_id,
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
                timeout=360,
            )
            result = read_json(self.root / "worker-results" / (attempt_id + ".json"))
            if (
                not verify_envelope(result, self.signer.public)
                or result["task"] != self.config["content_sha256"]
                or result["attempt_id"] != attempt_id
            ):
                raise ValueError("worker-result-invalid")
            with self.lock:
                self.finish(
                    attempt, result["verdict"], result["diagnostics"], result["runs"]
                )
        except Exception:
            with self.lock:
                if not (self.root / "receipts" / (attempt_id + ".json")).exists():
                    self.finish(attempt, "indeterminate", [], [], "equipment-failure")
        finally:
            with self.lock:
                self.active = None
                self.export()

    def unresolved(self):
        resolved = {
            e["receipt_sha256"] for e in self.events if e["kind"] == "operator-decision"
        }
        pending = []
        for e in self.accepted():
            receipt = self.receipt(e["attempt_id"])
            self.public_receipt(e["attempt_id"])
            finished = [
                f
                for f in self.events
                if f["kind"] == "finished" and f["attempt_id"] == e["attempt_id"]
            ]
            if (
                len(finished) != 1
                or finished[0]["receipt_sha256"] != receipt["content_sha256"]
            ):
                raise ValueError("attempt-finalization-incomplete")
            if (
                receipt["status"] != "completed"
                and receipt["content_sha256"] not in resolved
            ):
                pending.append(receipt)
        return pending

    def propose(self, attempt_id, dataset, field):
        from lightyear_mainframe.zos_bindings import load_bindings, dataset_binding
        from lightyear_control_tower.status_export import atomic_new

        receipt = self.receipt(attempt_id)
        if not any(
            d["dataset"] == dataset and d.get("field") == field
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
        if event["kind"] == "operator-decision":
            decision = verify_review(root, config, event["bundle"])
            if (
                decision["outcome"] != event["outcome"]
                or event["receipt_sha256"] != event["bundle"]["receipt_sha256"]
            ):
                raise ValueError("operator-decision-replay-failed")
        if event["kind"] != "accepted":
            continue
        reservation = event["inventory_reservation"]
        if (
            not verify_envelope(
                reservation, config["inventory_ledger_public_key"].encode()
            )
            or reservation["inventory_sha256"] != config["evaluation_inventory_sha256"]
            or reservation["task_sha256"] != config["content_sha256"]
            or reservation["attempt_id"] != event["attempt_id"]
        ):
            raise ValueError("inventory-reservation-invalid")
        attempts += 1
        if (
            event["attempt_number"] != attempts
            or event["attempt_id"] in ids
            or event["request_id"] in requests
            or attempts > config["submissions"]
            or attempts > config["attempt_slots"]
        ):
            raise ValueError("attempt-budget-or-identity-invalid")
        ids.add(event["attempt_id"])
        requests.add(event["request_id"])
        receipt = read_json(root / "receipts" / (event["attempt_id"] + ".json"))
        runs = read_json(root / "private-evidence" / (event["attempt_id"] + ".json"))
        public = read_json(root / "public-receipts" / (event["attempt_id"] + ".json"))
        if not verify_envelope(public, key) or {
            k: v for k, v in public.items() if k not in {"signature", "content_sha256"}
        } != public_body(receipt):
            raise ValueError("public-receipt-replay-failed")
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
            outcome, ds = summarize(runs)
            if not runs or (outcome, project(ds, config["disclosure_mode"])) != (
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
