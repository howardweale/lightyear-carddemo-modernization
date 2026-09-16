"""Archive replay-admitted terminal runs; never execute from a read projection."""
from __future__ import annotations

import gzip
import hashlib
import json
import os
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
