"""Authenticated human decisions and a signed, append-only local audit journal.

The service countersigns authenticated operator intent. It does not claim a browser
click is cryptographic proof of a human, nor replace customer SSO or WORM retention.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import subprocess
import sys
import threading
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from carddemo_oracle.compare import validate_normalization_ledger

WORKLOAD = "workload:carddemo-intcalc"
ZERO = "0" * 64


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def text_field(value: Any, label: str, maximum: int = 2000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{label} is required (maximum {maximum} characters)")
    return value.strip()


class DecisionConflict(ValueError):
    pass


class DecisionUnauthorized(ValueError):
    pass


def initialize_authority(path: Path, operator_id: str, operator_name: str) -> Path:
    """Provision a local individual credential; deliberately cannot approve anything."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    operator_id = text_field(operator_id, "Operator ID", 200)
    operator_name = text_field(operator_name, "Operator name", 200)
    if path.exists():
        raise ValueError("Authority already exists; refusing to replace its trust key")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    private = Ed25519PrivateKey.generate()
    private_path = path.with_suffix(".key.pem")
    public_path = path.with_suffix(".public.pem")
    credential_path = path.with_suffix(".credential.txt")
    token = secrets.token_urlsafe(48)
    public = private.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    files = {
        private_path: private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()),
        public_path: public,
        credential_path: token.encode() + b"\n",
        path: canonical({"schema_version": "1.0", "private_key": private_path.name,
                         "public_key": public_path.name, "operators": [{"id": operator_id,
                         "name": operator_name, "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
                         "roles": ["normalization-approver", "proof-runner"]}]}) + b"\n",
    }
    for target in files:
        if target.exists():
            raise ValueError(f"Refusing to overwrite existing authority file: {target.name}")
    for target, data in files.items():
        with os.fdopen(os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as stream:
            stream.write(data)
    return credential_path


def verify_envelope(envelope: dict, public_key: bytes) -> bool:
    from cryptography.hazmat.primitives import serialization
    from cryptography.exceptions import InvalidSignature
    try:
        signature = envelope["signature"]
        if signature["algorithm"] != "Ed25519" or signature["key_id"] != hashlib.sha256(public_key).hexdigest():
            return False
        body = {key: value for key, value in envelope.items() if key not in {"signature", "content_sha256"}}
        if digest(body) != envelope["content_sha256"]:
            return False
        serialization.load_pem_public_key(public_key).verify(base64.b64decode(signature["value"], validate=True), canonical(body))
        return True
    except (KeyError, TypeError, ValueError, InvalidSignature):
        return False


class DecisionService:
    def __init__(self, root: Path, authority: Path, database: Path | None = None, graph_identity=None, recover_runs: bool = True):
        from cryptography.hazmat.primitives import serialization
        self.root = root.resolve()
        self.authority_path = authority.resolve()
        config = json.loads(self.authority_path.read_text())
        if config.get("schema_version") != "1.0":
            raise ValueError("Unsupported decision authority configuration")
        key_path = self.authority_path.parent / config["private_key"]
        self.public_key = (self.authority_path.parent / config["public_key"]).read_bytes()
        self.key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
        self.key_id = hashlib.sha256(self.public_key).hexdigest()
        self.operators = config["operators"]
        ids = [operator["id"] for operator in self.operators]
        if not ids or len(ids) != len(set(ids)):
            raise ValueError("Operator identities must be nonempty and unique")
        self.database = database or self.root / "work/control-tower/decisions.sqlite3"
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self.graph_identity = graph_identity or (lambda: "")
        self.sessions: dict[str, dict] = {}
        self.lock = threading.RLock()
        self.workers: list[threading.Thread] = []
        self.closing = False
        self._writer_lock = None
        if recover_runs:
            self._acquire_writer_lock()
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS events (sequence INTEGER PRIMARY KEY, envelope TEXT NOT NULL)")
        if not verify_envelope(self.sign({"probe": "authority-key-pair"}), self.public_key):
            raise ValueError("Decision signing key does not match the trusted public key")
        # An interrupted process is never silently retried or reported as a pass.
        with self.transaction() as db:
            for run in self.runs(self.events(db)):
                if recover_runs and run["status"] == "running":
                    self.append(db, "proof_finished", {**run, "status": "interrupted", "reason": "server-restarted"}, self.system_actor())

    def _acquire_writer_lock(self):
        stream = open(self.database.with_suffix(".lock"), "a+b")
        stream.seek(0)
        if stream.read(1) == b"":
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            stream.close()
            raise ValueError("Another decision service owns this journal") from exc
        self._writer_lock = stream

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=15)
        try:
            db.execute("PRAGMA synchronous=FULL")
            with db:
                yield db
        finally:
            db.close()

    @contextmanager
    def transaction(self):
        with self.lock, self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            events = self.events(db)
            previous = ZERO
            for sequence, event in enumerate(events, 1):
                if event.get("sequence") != sequence or event.get("previous_sha256") != previous or not verify_envelope(event, self.public_key):
                    raise ValueError("Decision journal integrity check failed; commands are blocked")
                previous = event["content_sha256"]
            yield db

    @staticmethod
    def system_actor():
        return {"id": "control-tower-proof-worker", "name": "Automated proof worker", "kind": "service"}

    def sign(self, body: dict) -> dict:
        return {**body, "content_sha256": digest(body), "signature": {"algorithm": "Ed25519", "key_id": self.key_id,
                "value": base64.b64encode(self.key.sign(canonical(body))).decode()}}

    def events(self, db) -> list[dict]:
        return [json.loads(row[0]) for row in db.execute("SELECT envelope FROM events ORDER BY sequence")]

    def append(self, db, kind: str, payload: dict, actor: dict, session_id: str | None = None) -> dict:
        row = db.execute("SELECT sequence, envelope FROM events ORDER BY sequence DESC LIMIT 1").fetchone()
        sequence = row[0] + 1 if row else 1
        previous = json.loads(row[1])["content_sha256"] if row else ZERO
        event = self.sign({"schema_version": "1.0", "record_type": "control-tower-decision-event", "sequence": sequence,
                           "previous_sha256": previous, "occurred_at": utcnow().isoformat(), "kind": kind,
                           "actor": actor, "session_id": session_id, "payload": payload})
        db.execute("INSERT INTO events VALUES (?, ?)", (sequence, canonical(event).decode()))
        return event

    def login(self, credential: str) -> dict:
        supplied = hashlib.sha256(text_field(credential, "Operator credential", 300).encode()).hexdigest()
        operator = next((item for item in self.operators if hmac.compare_digest(supplied, item["token_sha256"])), None)
        if operator is None:
            raise DecisionUnauthorized("The operator credential is not valid")
        token = secrets.token_urlsafe(32)
        session = {"id": str(uuid.uuid4()), "actor": {"id": operator["id"], "name": operator["name"], "kind": "operator"},
                   "roles": operator["roles"], "expires_at": (utcnow() + timedelta(hours=1)).isoformat()}
        with self.transaction() as db:
            self.append(db, "session_started", {"expires_at": session["expires_at"], "authentication": "individual-local-credential"}, session["actor"], session["id"])
            self.sessions[token] = session
        return {**session, "token": token}

    def authenticate(self, token: str, role: str | None = None) -> dict:
        with self.lock:
            session = self.sessions.get(token)
            if not session or utcnow() >= datetime.fromisoformat(session["expires_at"]):
                raise DecisionUnauthorized("Start a new operator session")
            if role and role not in session["roles"]:
                raise DecisionUnauthorized("Your operator role does not permit this action")
            return session

    def logout(self, token: str) -> dict:
        with self.transaction() as db:
            session = self.authenticate(token)
            self.append(db, "session_ended", {}, session["actor"], session["id"])
            del self.sessions[token]
        return {"status": "ended"}

    def ledger(self) -> tuple[dict, str]:
        path = self.root / "spec/comparison-normalizations.json"
        validation = validate_normalization_ledger(path)
        if validation["status"] != "passed":
            raise ValueError("Normalization ledger is invalid: " + ", ".join(validation["errors"]))
        ledger = json.loads(path.read_text())
        return ledger, digest(ledger)

    def items(self, events: list[dict]) -> list[dict]:
        ledger, ledger_hash = self.ledger()
        result = []
        for rule in ledger["rules"]:
            latest = next((event for event in reversed(events) if event["kind"] == "normalization_decided" and event["payload"]["entry_id"] == rule["id"]), None)
            status = "pending"
            if latest:
                decision = latest["payload"]
                if decision["entry_sha256"] != digest(rule) or decision["ledger_sha256"] != ledger_hash:
                    status = "changed"
                elif decision["outcome"] == "rejected":
                    status = "rejected"
                elif date.fromisoformat(decision["review_after"]) <= utcnow().date():
                    status = "expired"
                else:
                    status = "approved"
            result.append({"id": rule["id"], "workload_id": WORKLOAD, "workload_name": "CardDemo · Interest calculation",
                           "kind": "normalization", "rule": rule, "entry_sha256": digest(rule), "ledger_sha256": ledger_hash,
                           "status": status, "latest_decision": latest})
        return result

    def queue(self, token: str) -> dict:
        session = self.authenticate(token)
        with self.transaction() as db:
            events = self.events(db)
            return {"items": self.items(events), "runs": self.runs(events), "session": session,
                    "events": events[-100:], "supported_decisions": ["normalization"],
                    "proof_workloads": [WORKLOAD]}

    def review(self, token: str, entry_id: str) -> dict:
        session = self.authenticate(token)
        with self.transaction() as db:
            item = next((item for item in self.items(self.events(db)) if item["id"] == entry_id), None)
            if item is None:
                raise KeyError(entry_id)
            self.append(db, "normalization_viewed", {"entry_id": entry_id, "entry_sha256": item["entry_sha256"],
                        "ledger_sha256": item["ledger_sha256"], "workload_id": WORKLOAD}, session["actor"], session["id"])
            return item

    def decide(self, token: str, payload: dict) -> dict:
        session = self.authenticate(token, "normalization-approver")
        reason = text_field(payload.get("reason"), "Reason")
        owner = text_field(payload.get("owner"), "Named owner", 200)
        outcome = payload.get("outcome")
        if outcome not in {"approved", "rejected"}:
            raise ValueError("Choose approved or rejected")
        if outcome == "approved":
            review_after = date.fromisoformat(text_field(payload.get("review_after"), "Review date", 10))
            if not utcnow().date() < review_after <= utcnow().date() + timedelta(days=366):
                raise ValueError("Review date must be in the next 366 days")
        request_id = str(uuid.UUID(text_field(payload.get("request_id"), "Request ID", 36)))
        with self.transaction() as db:
            session = self.authenticate(token, "normalization-approver")
            events = self.events(db)
            for event in events:
                if event["kind"] == "normalization_decided" and event["payload"]["request_id"] == request_id:
                    if event["actor"] != session["actor"] or event["payload"]["request_sha256"] != digest(payload):
                        raise DecisionConflict("Request ID was already used for a different decision")
                    return event
            item = next((item for item in self.items(events) if item["id"] == payload.get("entry_id")), None)
            if not item:
                raise KeyError(payload.get("entry_id"))
            if payload.get("entry_sha256") != item["entry_sha256"] or payload.get("ledger_sha256") != item["ledger_sha256"] or payload.get("previous_decision_sha256") != (item["latest_decision"] or {}).get("content_sha256"):
                raise DecisionConflict("This entry or its decision changed. Refresh and review it again")
            if not any(event["kind"] == "normalization_viewed" and event["session_id"] == session["id"] and event["payload"].get("entry_id") == item["id"] and event["payload"].get("ledger_sha256") == item["ledger_sha256"] for event in events):
                raise DecisionConflict("Review the current normalization in this session before deciding")
            if outcome == "approved" and review_after > date.fromisoformat(item["rule"]["review_after"]):
                raise ValueError("Review date cannot extend the governed ledger review date")
            return self.append(db, "normalization_decided", {"entry_id": item["id"], "entry_sha256": item["entry_sha256"],
                        "ledger_sha256": item["ledger_sha256"], "workload_id": WORKLOAD, "outcome": outcome, "reason": reason,
                        "owner": owner, "review_after": review_after.isoformat() if outcome == "approved" else None,
                        "request_id": request_id, "request_sha256": digest(payload),
                        "previous_decision_sha256": payload.get("previous_decision_sha256"), "channel": "control-tower",
                        "authentication": "individual-local-credential"}, session["actor"], session["id"])

    @staticmethod
    def runs(events: list[dict]) -> list[dict]:
        runs = {}
        for event in events:
            if event["kind"] in {"proof_started", "proof_finished"}:
                runs[event["payload"]["run_id"]] = {**event["payload"], "record_sha256": event["content_sha256"]}
        return list(reversed(list(runs.values())))

    def source_manifest(self) -> dict:
        paths = [self.root / "factory/benchmarks/intcalc_candidate.py", self.root / "spec/comparison-normalizations.json"]
        for package in ("lightyear_factory", "lightyear_common", "carddemo_oracle"):
            paths.extend(sorted((self.root / "src" / package).glob("*.py")))
        return {path.relative_to(self.root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(paths)}

    def dispatch(self, token: str, payload: dict) -> dict:
        session = self.authenticate(token, "proof-runner")
        if payload.get("workload_id") != WORKLOAD:
            raise ValueError("No approved proof runner is configured for this workload")
        request_id = str(uuid.UUID(text_field(payload.get("request_id"), "Request ID", 36)))
        with self.transaction() as db:
            session = self.authenticate(token, "proof-runner")
            if self.closing:
                raise DecisionConflict("Server is stopping; no new proof run was started")
            events = self.events(db)
            for event in events:
                if event["kind"] == "proof_started" and event["payload"]["request_id"] == request_id:
                    if event["actor"] != session["actor"]:
                        raise DecisionConflict("Request ID belongs to a different operator")
                    return next(run for run in self.runs(events) if run["run_id"] == event["payload"]["run_id"])
            if any(run["status"] == "running" for run in self.runs(events)):
                raise DecisionConflict("A proof run is already active; open it to follow progress")
            _, ledger_hash = self.ledger()
            manifest = self.source_manifest()
            run_id = "ct-" + uuid.uuid4().hex
            run = {"run_id": run_id, "request_id": request_id, "workload_id": WORKLOAD, "status": "running",
                   "started_at": utcnow().isoformat(), "ledger_sha256": ledger_hash,
                   "source_sha256": digest(manifest), "graph_sha256": self.graph_identity(),
                   "evidence_class": "local-reference-proof", "customer_evidence": False, "production_ready": False}
            target = self.root / "work/control-tower/proof-runs" / run_id
            for relative, expected in manifest.items():
                destination = target / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                data = (self.root / relative).read_bytes()
                if hashlib.sha256(data).hexdigest() != expected:
                    raise DecisionConflict("Proof inputs changed while staging; retry against stable inputs")
                destination.write_bytes(data)
            self.append(db, "proof_started", run, session["actor"], session["id"])
        worker = threading.Thread(target=self.execute_proof, args=(run, target, session), daemon=True)
        self.workers.append(worker)
        worker.start()
        return run

    def execute_proof(self, run: dict, target: Path, session: dict):
        try:
            env = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP") if key in os.environ}
            env.update({"PYTHONPATH": str(target / "src"), "LIGHTYEAR_FACTORY_WORKSPACE": str(target), "PYTHONDONTWRITEBYTECODE": "1"})
            result = subprocess.run([sys.executable, "-m", "lightyear_factory.private_benchmark"], cwd=target,
                                    env=env, capture_output=True, timeout=60, check=False)
            validation = validate_normalization_ledger(target / "spec/comparison-normalizations.json")
            passed = result.returncode == 0 and validation["status"] == "passed"
            finished = {**run, "status": "passed" if passed else "failed", "exit_code": result.returncode,
                        "checks": {"intcalc_policy": result.returncode == 0, "normalization_contract": validation["status"] == "passed"},
                        "output_sha256": hashlib.sha256(result.stdout + result.stderr).hexdigest()}
        except Exception as exc:
            finished = {**run, "status": "failed", "reason": type(exc).__name__}
        finished["finished_at"] = utcnow().isoformat()
        with self.transaction() as db:
            receipt = self.append(db, "proof_finished", finished, self.system_actor(), session["id"])
        (target / "proof.receipt.json").write_bytes(canonical(receipt) + b"\n")

    def gate(self, run_id: str) -> dict:
        """Always checks authoritative current state; no trust in a caller-supplied pass."""
        with self.transaction() as db:
            events = self.events(db)
            run = next((run for run in self.runs(events) if run["run_id"] == run_id), None)
            if run is None:
                raise KeyError(run_id)
            items = self.items(events)
            _, ledger_hash = self.ledger()
            reasons = []
            if run["status"] != "passed":
                reasons.append("proof-not-passed")
            if run["ledger_sha256"] != ledger_hash or run["source_sha256"] != digest(self.source_manifest()) or run["graph_sha256"] != self.graph_identity():
                reasons.append("proof-inputs-changed")
            for item in items:
                if item["status"] != "approved":
                    reasons.append(f"normalization-{item['status']}:{item['id']}")
            body = {"schema_version": "1.0", "receipt_type": "ms68-control-tower-human-decision-gate",
                    "workload_id": WORKLOAD, "run_id": run_id, "status": "blocked" if reasons else "passed",
                    "reason_codes": reasons, "issued_at": utcnow().isoformat(),
                    "valid_until": min((item["latest_decision"]["payload"]["review_after"] for item in items if item["status"] == "approved"), default=None),
                    "proof_record_sha256": run["record_sha256"], "ledger_sha256": ledger_hash,
                    "source_sha256": run["source_sha256"], "graph_sha256": run["graph_sha256"],
                    "approval_records": [item["latest_decision"] for item in items if item["status"] == "approved"],
                    "journal_head_sha256": events[-1]["content_sha256"] if events else ZERO,
                    "operator_workflow_complete": not reasons,
                    "human_promotion_authorized": False, "ms68_complete": False, "production_ready": False,
                    "scope": "normalization approval and local reference proof only"}
            return self.sign(body)

    def export_session(self, token: str) -> dict:
        session = self.authenticate(token)
        with self.transaction() as db:
            events = self.events(db)
            # Include the full chain so a verifier can verify continuity, plus a session index.
            return self.sign({"schema_version": "1.0", "record_type": "control-tower-session-export",
                              "session": session, "exported_at": utcnow().isoformat(), "events": events,
                              "session_sequences": [e["sequence"] for e in events if e["session_id"] == session["id"]],
                              "journal_head_sha256": events[-1]["content_sha256"] if events else ZERO})

    def close(self):
        self.closing = True
        for worker in self.workers:
            worker.join(timeout=65)
        if self._writer_lock:
            if os.name == "nt":
                import msvcrt
                self._writer_lock.seek(0)
                msvcrt.locking(self._writer_lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._writer_lock.fileno(), fcntl.LOCK_UN)
            self._writer_lock.close()
            self._writer_lock = None
