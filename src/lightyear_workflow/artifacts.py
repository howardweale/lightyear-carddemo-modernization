"""Engine writes snapshots; readers verify and project them without writing evidence."""
from __future__ import annotations

from datetime import datetime, timezone
import gzip
import json
import os
from pathlib import Path
import tempfile

from lightyear_data.contracts import content_hash, seal
from .planner import POLICY_PATH, build_plan, markdown_report
from .policy import load_policy

SNAPSHOT_PATH = Path("control-tower/action-plan.snapshot.json.gz")
LIVE_PATH = Path("work/workflow/action-plan.snapshot.json.gz")


def _atomic_write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def emit(root: Path, output: Path, report: Path | None = None) -> dict:
    plan = build_plan(root, load_policy(root / POLICY_PATH))
    snapshot = seal({"artifact_type": "lightyear-action-plan-snapshot", "schema_version": "1.0",
                     "emitted_at": datetime.now(timezone.utc).isoformat(), "plan": plan})
    _atomic_write(output, gzip.compress(json.dumps(snapshot, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(), mtime=0))
    if report is not None:
        _atomic_write(report, markdown_report(plan).encode())
    return snapshot


def read_snapshot(root: Path, path: Path | None = None, *, now: datetime | None = None) -> dict:
    """Never generate a missing plan in the Tower. Changed evidence invalidates it."""
    path = path or (root / LIVE_PATH if (root / LIVE_PATH).exists() else root / SNAPSHOT_PATH)
    if not path.is_file():
        return {"status": "unavailable", "reason": "The headless engine has not published an action plan.", "engine_status": "no-executor-in-step-1", "plan": None}
    try:
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            snapshot = json.load(stream)
        if snapshot.get("artifact_type") != "lightyear-action-plan-snapshot" or snapshot.get("schema_version") != "1.0" or snapshot.get("content_sha256") != content_hash(snapshot):
            raise ValueError("Snapshot identity or content hash is invalid")
        expected = build_plan(root, load_policy(root / POLICY_PATH))
        if snapshot["plan"] != expected:
            raise ValueError("Action plan differs from current admitted evidence, implementation or policy")
        emitted_at = datetime.fromisoformat(snapshot["emitted_at"])
        if emitted_at.tzinfo is None:
            raise ValueError("Snapshot time must include its timezone")
        age = ((now or datetime.now(timezone.utc)) - emitted_at).total_seconds()
        if age < -60:
            raise ValueError("Snapshot timestamp is in the future")
        return {"status": "stale" if age >= 86400 else "snapshot", "emitted_at": snapshot["emitted_at"],
                "age_seconds": max(0, int(age)), "engine_status": "no-executor-in-step-1",
                "reason": "Planning snapshot; engine liveness and convergence are not measured.", "plan": expected}
    except (OSError, EOFError, ValueError, KeyError, TypeError) as exc:
        return {"status": "invalid", "reason": str(exc), "engine_status": "no-executor-in-step-1", "plan": None}


def project_snapshot(snapshot: dict, *, kind: str | None = None, action_class: str | None = None,
                     entity_id: str | None = None, offset: int = 0, limit: int = 50) -> dict:
    """Bounded read projection, no decision or execution API."""
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("Action page must have offset >= 0 and limit from 1 to 100")
    plan = snapshot.get("plan")
    result = {k: v for k, v in snapshot.items() if k != "plan"}
    if plan is None:
        return {**result, "summary": None, "items": [], "total": 0}
    actions = [a for r in plan["results"] for a in r["actions"]
               if (not entity_id or r["entity_id"] == entity_id) and (not kind or a["kind"] == kind)
               and (not action_class or a["class"] == action_class)]
    return {**result, "summary": plan["summary"], "bindings": plan["bindings"],
            "plan_sha256": plan["content_sha256"], "execution": plan["execution"],
            "convergence": plan["convergence"], "items": actions[offset:offset + limit],
            "total": len(actions), "offset": offset, "limit": limit}
