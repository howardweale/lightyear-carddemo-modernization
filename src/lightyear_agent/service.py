"""Transport-independent v1 workflow. No approval, SQL, cloud or shell interface."""
from __future__ import annotations

from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import uuid

from lightyear_data.contracts import content_hash, seal
from lightyear_workflow.cloudbank import build_execution_plan
from lightyear_workflow.execution import execute, project_events
from lightyear_workflow.ledger_gate import current_approval
from lightyear_workflow.policy import _unique_object
from lightyear_workflow.run_store import RunStore, utcnow

WORKFLOW = "cloudbank-retained-v1"
VERSION = "1.0"
OPERATIONS = ("capabilities", "plan", "start", "status", "events", "verify", "export", "resume")
SOURCE = Path(__file__).resolve().parents[1]


class WorkflowError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def safe_path(path: Path) -> Path:
    path = path.absolute()
    if any(p.is_symlink() or getattr(p, "is_junction", lambda: False)() for p in (path, *path.parents)):
        raise WorkflowError("unsafe-path", "Symbolic links and junctions are outside this workflow's scope.")
    return path.resolve()


def read_json(path, limit=2 * 1024 * 1024):
    path = safe_path(path)
    if path.stat().st_size > limit:
        raise WorkflowError("invalid-evidence", "JSON exceeds the permitted size.")
    return json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=_unique_object)


def initialize(path: Path, evidence_root: Path, project_id: str) -> dict:
    path = safe_path(path)
    value = {"schema_version": VERSION, "project_id": project_id, "workflow": WORKFLOW,
             "evidence_root": str(safe_path(evidence_root))}
    validate_manifest(value, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, indent=2) + "\n")
    return {"schema_version": VERSION, "ok": True, "status": "configured", "project": str(path)}


def validate_manifest(value, path):
    if (not isinstance(value, dict) or set(value) != {"schema_version", "project_id", "workflow", "evidence_root"}
            or value["schema_version"] != VERSION or value["workflow"] != WORKFLOW
            or not isinstance(value["project_id"], str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", value["project_id"])
            or not isinstance(value["evidence_root"], str) or not value["evidence_root"]):
        raise WorkflowError("configuration-required", "Use a v1 project manifest with the registered cloudbank-retained-v1 workflow.")
    root = safe_path(path.parent / value["evidence_root"])
    if not (root / "control-tower/execution-policy.json").is_file():
        raise WorkflowError("configuration-required", "Evidence root must contain the CloudBank evidence checkout and execution policy.")
    return root


class Workflow:
    def __init__(self, project: Path, *, dispatcher=None):
        self.project = safe_path(project)
        self.config = read_json(self.project, 16384)
        self.root = validate_manifest(self.config, self.project)
        self.identity = content_hash({"project": str(self.project), "config": self.config})
        self.directory = self.root / "work/agent-workflows" / self.identity
        self.dispatcher = dispatcher or self._dispatch

    def _guard(self):
        safe_path(self.directory)
        if read_json(self.project, 16384) != self.config:
            raise WorkflowError("configuration-changed", "Project configuration changed; restart the client and review a new plan.")

    def invoke(self, operation: str, **arguments) -> dict:
        base = {"schema_version": VERSION, "project_id": self.config["project_id"], "workflow": WORKFLOW}
        try:
            self._guard()
            if operation not in OPERATIONS:
                raise WorkflowError("unsupported-operation", "Operation is not available in this workflow.")
            return {**base, "ok": True, **getattr(self, operation)(**arguments)}
        except WorkflowError as exc:
            return {**base, "ok": False, "status": "error", "error": {"code": exc.code, "message": str(exc)}}
        except (ValueError, OSError, KeyError, TypeError, sqlite3.Error):
            # Do not return paths, worker stderr or credentials through an error.
            return {**base, "ok": False, "status": "error", "error": {
                "code": "invalid-evidence-or-configuration", "message": "Operation could not verify its configured inputs or journal."}}

    def capabilities(self):
        return {"status": "ready", "operations": list(OPERATIONS), "transport": ["json-cli", "stdio-mcp"],
                "evidence_class": "retained-evidence-verification", "fresh_database_execution": False,
                "cloud_execution": False, "creates_human_approval": False,
                "project_scope": "Configured CloudBank evidence checkout; arbitrary customer adapters are not yet supported.",
                "authorization": "Local operations obey the existing execution policy; ledger application also requires a separately signed human decision.",
                "plan_resource": "lightyear://plan/current"}

    def _plan(self):
        self._guard()
        engine = build_execution_plan(self.root)
        self._check_runtime(engine)
        return seal({"schema_version": VERSION, "workflow": WORKFLOW, "project_identity": self.identity,
                     "engine_plan": engine})

    def _check_runtime(self, engine):
        # The executing package must match the code actually bound by the plan,
        # including when an external project points at another evidence checkout.
        for relative, expected in engine["inputs"]["files"].items():
            if relative.startswith("src/"):
                path = safe_path(SOURCE / relative[4:])
                actual = hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
                if actual != expected:
                    raise WorkflowError("implementation-mismatch", "Install the implementation matching the configured evidence checkout.")

    def plan(self):
        value = self._plan()
        engine = value["engine_plan"]
        return {"status": "reviewable", "plan_sha256": value["content_sha256"],
                "scope": engine["scope"], "services": engine["services"], "limits": engine["policy"],
                "evidence_class": "retained-evidence-verification", "incremental_cloud_cost_usd": 0,
                "human_decision": current_approval(self.root), "plan_resource": "lightyear://plan/current"}

    def _db(self, *, write=False):
        self._guard()
        path = safe_path(self.directory / "runs.sqlite3")
        if write:
            self.directory.mkdir(parents=True, exist_ok=True)
            db = sqlite3.connect(path, timeout=15)
            db.execute("PRAGMA synchronous=FULL")
            db.execute("CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL, plan TEXT NOT NULL, dispatch_state TEXT NOT NULL, created_at TEXT NOT NULL)")
            db.commit()
        else:
            if not path.is_file():
                raise WorkflowError("run-not-found", "No run exists with this ID in this project.")
            db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
        db.row_factory = sqlite3.Row
        return db

    def _run_id(self, request_id):
        try:
            normalized = str(uuid.UUID(request_id))
        except (ValueError, TypeError, AttributeError):
            raise WorkflowError("invalid-request-id", "request_id must be a UUID; reuse it when retrying the same start request.") from None
        return normalized, "agent-" + uuid.uuid5(uuid.NAMESPACE_URL, self.identity + normalized).hex

    def _row(self, run_id):
        if not isinstance(run_id, str) or not re.fullmatch(r"agent-[a-f0-9]{32}", run_id):
            raise WorkflowError("invalid-run-id", "Use a run ID returned by start for this project.")
        with closing(self._db()) as db:
            row = db.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            raise WorkflowError("run-not-found", "No run exists with this ID in this project.")
        row = dict(row)
        row["plan"] = json.loads(row["plan"], object_pairs_hook=_unique_object)
        plan = row["plan"]
        if (self._run_id(row["request_id"])[1] != run_id or plan["project_identity"] != self.identity
                or plan["content_sha256"] != content_hash(plan)):
            raise WorkflowError("invalid-evidence", "Run metadata failed verification.")
        return row

    def _run_directory(self, run_id):
        return safe_path(self.directory / "runs" / run_id)

    def start(self, plan_sha256: str, request_id: str):
        request_id, run_id = self._run_id(request_id)
        # Retries return the same receipt even if the current inputs have drifted.
        with closing(self._db(write=True)) as db:
            old = db.execute("SELECT plan FROM runs WHERE request_id=?", (request_id,)).fetchone()
        if old:
            row = self._row(run_id)
            if row["plan"]["content_sha256"] != plan_sha256:
                raise WorkflowError("request-conflict", "This request ID already belongs to another plan.")
            return {"status": "accepted", "run_id": run_id, "new_dispatch": False}
        plan = self._plan()
        if plan_sha256 != plan["content_sha256"]:
            raise WorkflowError("plan-changed", "Review the current plan before starting; the supplied digest is stale.")
        with closing(self._db(write=True)) as db, db:
            created = db.execute("INSERT OR IGNORE INTO runs VALUES (?,?,?,?,?)",
                                 (run_id, request_id, json.dumps(plan, sort_keys=True), "dispatch-unconfirmed", utcnow())).rowcount == 1
        if self._row(run_id)["plan"]["content_sha256"] != plan_sha256:
            raise WorkflowError("request-conflict", "This request ID already belongs to another plan.")
        if created:
            try:
                self.dispatcher(run_id)
            except OSError:
                return {"status": "dispatch-unconfirmed", "run_id": run_id, "new_dispatch": True,
                        "next_action": "Inspect status; use resume to recover this same run."}
        return {"status": "accepted", "run_id": run_id, "new_dispatch": created}

    def _dispatch(self, run_id):
        keep = {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR", "LANG"}
        env = {k: v for k, v in os.environ.items() if k in keep}
        env.update(PYTHONPATH=str(SOURCE), PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
        options = {"start_new_session": True} if os.name != "nt" else {
            "creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP}
        subprocess.Popen([sys.executable, "-m", "lightyear_agent.worker", "--project", str(self.project), "--run-id", run_id],
                         cwd=self.root, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, close_fds=True, **options)

    def _verified(self, run_id):
        row = self._row(run_id)
        directory = self._run_directory(run_id) / "journal"
        safe_path(directory / "events.sqlite3")
        events = RunStore(directory, read_only=True).events()
        if not events:
            return row, [], None
        if events[0]["payload"] != row["plan"]["engine_plan"]:
            raise WorkflowError("invalid-evidence", "Journal does not match the reviewed plan.")
        self._check_runtime(row["plan"]["engine_plan"])
        return row, events, project_events(self.root, events, "engine-journal")

    def status(self, run_id: str):
        row, events, view = self._verified(run_id)
        result = {"run_id": run_id, "plan_sha256": row["plan"]["content_sha256"],
                  "dispatch_state": row["dispatch_state"], "evidence_class": "retained-evidence-verification",
                  "fresh_database_execution": False, "events_resource": f"lightyear://runs/{run_id}/events"}
        if view is None:
            return {**result, "status": row["dispatch_state"], "terminal": False}
        halt = view["halt_reason"]
        status = {"human-decision-required": "human-decision-required", "completed": "completed",
                  "divergent": "comparison-failed"}.get(halt, "execution-failed" if halt else "running-or-interrupted")
        if halt is None and row["dispatch_state"] == "execution-failed":
            status = "execution-failed"
        return {**result, "status": status, "terminal": halt is not None, "halt_reason": halt,
                "summary": view["summary"], "boundary": view["boundary"],
                "human_decision": view["current_ledger_approval"],
                "journal_head_sha256": view["journal_head_sha256"],
                "tower": {"estate": "cloudbank", "campaign_id": "retained",
                          "run_id": "cloudbank-" + events[0]["content_sha256"],
                          "available_in_history": halt is not None and row["dispatch_state"] == "finished"}}

    def events(self, run_id: str, after: int = 0, limit: int = 10):
        if type(after) is not int or after < 0 or type(limit) is not int or not 1 <= limit <= 25:
            raise WorkflowError("invalid-page", "after must be nonnegative; limit must be 1 through 25.")
        _, events, _ = self._verified(run_id)
        if after > len(events):
            raise WorkflowError("invalid-page", "Cursor is beyond the verified journal.")
        page = events[after:after + limit]
        return {"status": "verified", "run_id": run_id, "events": page, "next_cursor": after + len(page),
                "has_more": after + len(page) < len(events), "total_events": len(events)}

    def verify(self, run_id: str):
        value = self.status(run_id)
        if "journal_head_sha256" not in value:
            raise WorkflowError("evidence-unavailable", "No engine journal is available to verify yet.")
        return {**value, "verified": True, "verification_method": "hash-chain-and-semantic-replay",
                "independent_signature": False, "workflow_completed": value["status"] == "completed"}

    def evidence(self, run_id):
        row, events, view = self._verified(run_id)
        if view is None or view["halt_reason"] is None:
            raise WorkflowError("run-not-terminal", "Export requires a verified terminal journal, including a human-decision halt.")
        return seal({"schema_version": VERSION, "artifact_type": "lightyear-agent-evidence",
                     "evidence_class": "retained-evidence-verification", "independent_signature": False,
                     "project_id": self.config["project_id"], "run_id": run_id, "plan": row["plan"], "events": events,
                     "workflow_status": view["status"], "halt_reason": view["halt_reason"]})

    def export(self, run_id: str):
        value = self.evidence(run_id)
        raw = (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()
        path = safe_path(self._run_directory(run_id) / "evidence.json")
        # Exclusive publish: a repeat never replaces a differing evidence file.
        temporary = path.with_name(".export-" + uuid.uuid4().hex)
        try:
            with temporary.open("xb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, path)
            except FileExistsError:
                pass
        finally:
            temporary.unlink(missing_ok=True)
        if path.read_bytes() != raw:
            raise WorkflowError("export-conflict", "Existing export differs from the verified run; it was not overwritten.")
        return {"status": "exported", "run_id": run_id, "path": str(path), "sha256": hashlib.sha256(raw).hexdigest(),
                "resource_uri": f"lightyear://runs/{run_id}/evidence", "halt_reason": value["halt_reason"]}

    def resume(self, run_id: str):
        row, _, view = self._verified(run_id)
        if view and view["halt_reason"] is not None:
            if row["dispatch_state"] != "finished":
                self.dispatcher(run_id)
                return {"status": "resume-requested", "run_id": run_id,
                        "note": "Repair terminal archive publication only; no actions will repeat."}
            return {**self.status(run_id), "new_dispatch": False,
                    "next_action": "Terminal runs remain immutable. After a human decision, plan and start with a new request ID."}
        if self._plan() != row["plan"]:
            raise WorkflowError("plan-changed", "Inputs or policy changed; retain this run and review a new plan.")
        self.dispatcher(run_id)
        return {"status": "resume-requested", "run_id": run_id,
                "note": "A per-run process lock prevents concurrent workers; completed actions are not repeated."}

    def _set_dispatch(self, run_id, state):
        with closing(self._db(write=True)) as db, db:
            db.execute("UPDATE runs SET dispatch_state=? WHERE run_id=?", (state, run_id))

    def work(self, run_id):
        self._row(run_id)
        # Reuse the engine's cross-platform OS lease. A competing dispatcher
        # exits without changing the active worker's state or running actions.
        lease = RunStore(self._run_directory(run_id) / "lease")
        try:
            row, _, view = self._verified(run_id)
            if view and view["halt_reason"] is not None:
                # Repair a crash after the terminal event but before archive/index
                # publication. execute() replays and finishes without more actions.
                execute(self.root, self._run_directory(run_id) / "journal")
                self._set_dispatch(run_id, "finished")
                return
            if self._plan() != row["plan"]:
                raise WorkflowError("plan-changed", "Reviewed inputs changed before execution.")
            self._set_dispatch(run_id, "running-or-interrupted")
            execute(self.root, self._run_directory(run_id) / "journal")
            self._set_dispatch(run_id, "finished")
        except (ValueError, OSError, KeyError, TypeError, sqlite3.Error):
            self._set_dispatch(run_id, "execution-failed")
            raise
        finally:
            lease.close()
