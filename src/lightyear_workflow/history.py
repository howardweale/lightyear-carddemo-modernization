"""Archive replay-admitted terminal runs; never execute from a read projection."""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import sqlite3
from pathlib import Path
import tempfile

from .convergence import INDEX_RELATIVE
from .run_index import RunIndex, summarise

HISTORY_PATH = Path("work/workflow/history/journals")


def record_finished(root: Path, events: list[dict], journals: Path) -> dict:
    # Semantic admission is mandatory even for callers outside execute(). A sealed
    # but invented result must not acquire a permanent history row.
    from .execution import _output_scope, replay
    state = replay(root, events)
    if state["halt_reason"] is None:
        raise ValueError("Only replay-admitted terminal runs can enter history")
    _output_scope(root, journals)
    index_path = root / INDEX_RELATIVE
    if any(p.is_symlink() for p in (index_path, *index_path.parents)):
        raise ValueError("Symbolic history index path")
    run_id = "cloudbank-" + events[0]["content_sha256"]
    metadata = {"run_id": run_id, "estate": "cloudbank", "workload": state["plan"]["scope"]}
    archive = {**metadata, "events": events}
    raw = gzip.compress(json.dumps(archive, sort_keys=True, separators=(",", ":")).encode(), mtime=0)
    path = journals.resolve() / (run_id + ".json.gz")
    index = RunIndex(index_path)
    existing = index.lookup(run_id)
    expected = {**summarise(**metadata, events=events), "journal_path": str(path),
                "journal_sha256": hashlib.sha256(raw).hexdigest(), "journal_bytes": len(raw)}
    if existing:
        if any(existing[k] != v for k, v in expected.items()):
            raise ValueError("Run identity already records a different history archive")
        if existing["journal_pruned_at"]:
            # A repeat invocation must never undo the customer's retention choice.
            return existing
    journals.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError("Symbolic history journal path")
    if not path.exists():
        # Publish only complete bytes, without replacing an existing archive. A
        # crash between this publish and record() is repaired by the next run.
        fd, temporary = tempfile.mkstemp(prefix=".history-", dir=journals)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, path)
            except FileExistsError:
                pass
        finally:
            Path(temporary).unlink(missing_ok=True)
    if path.is_symlink() or path.read_bytes() != raw:
        raise ValueError("History archive differs from the admitted terminal run")
    return index.record(**metadata, events=events, journal_path=path)


ESTATES = {"cloudbank": "CloudBank", "carddemo": "CardDemo", "oracle": "Oracle", "idempiere": "iDempiere"}


def estate_name(estate: str) -> str:
    if estate not in ESTATES:
        raise ValueError("Unknown workflow estate")
    return ESTATES[estate]


def _read_index(root: Path) -> RunIndex:
    path = root / INDEX_RELATIVE
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("Symbolic history index")
    return RunIndex(path, read_only=True)


def read_runs(root: Path, estate: str = "cloudbank") -> dict:
    name = estate_name(estate)
    result = {"estate": estate, "estate_name": name, "read_only": True, "limit": 100}
    try:
        rows = _read_index(root).runs(estate) if (root / INDEX_RELATIVE).exists() else []
        return {**result, "runs": [{k: v for k, v in row.items() if k != "journal_path"} for row in rows],
                "reason": None if rows else "no-runs-recorded"}
    except (OSError, ValueError, sqlite3.Error):
        return {**result, "runs": [], "reason": "invalid-run-index"}


def read_selected(root: Path, estate: str = "cloudbank", run_id: str | None = None) -> dict:
    """Resolve IDs through the index; verify bounded archive bytes and replay."""
    from .execution import read_execution, project_events
    from .policy import _unique_object
    context = {"estate_id": estate, "estate_name": estate_name(estate), "run_id": run_id or "current", "read_only": True}
    empty = {**context, "status": "unavailable", "items": []}
    if estate != "cloudbank":
        return {**empty, "reason": "No run adapter is recorded for this estate."}
    if not run_id or run_id == "current":
        return {**read_execution(root), **context}
    try:
        row = _read_index(root).lookup(run_id)
        if not row or row["estate"] != estate:
            return {**empty, "reason": "This run is not recorded for the selected estate."}
        if row["journal_pruned_at"]:
            return {**empty, "reason": "Journal pruned by retention policy. Indexed history remains available."}
        path = Path(row["journal_path"])
        if any(p.is_symlink() for p in (path, *path.parents)) or not path.resolve().is_relative_to((root / "work").resolve()):
            raise ValueError("Journal archive is outside the permitted workspace")
        if path.stat().st_size != row["journal_bytes"] or not 0 < row["journal_bytes"] <= 16 * 1024 * 1024:
            raise ValueError("Journal archive size is invalid")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != row["journal_sha256"]:
            raise ValueError("Journal archive hash is invalid")
        with gzip.open(path, "rb") as stream:
            decoded = stream.read(16 * 1024 * 1024 + 1)
        if len(decoded) > 16 * 1024 * 1024:
            raise ValueError("Journal exceeds bounded size")
        archive = json.loads(decoded, object_pairs_hook=_unique_object)
        if any(archive[k] != row[k] for k in ("run_id", "estate", "workload")):
            raise ValueError("Journal context differs from its index")
        events = archive["events"]
        if run_id != "cloudbank-" + events[0]["content_sha256"]:
            raise ValueError("Journal identity mismatch")
        result = project_events(root, events, "engine-journal")
        expected = summarise(run_id, estate, row["workload"], events)
        if any(expected[k] != row[k] for k in expected):
            raise ValueError("Journal summary differs from its index")
        return {**result, **context}
    except (ValueError, OSError, KeyError, IndexError, TypeError, sqlite3.Error):
        return {**context, "status": "invalid", "reason": "Selected journal could not be verified.", "items": []}
