"""Run history: one small row per run, kept forever; journals pruned on policy.

`RunStore` is a single run — a hash-chained journal capped at 256 events, which
is roughly 123 actions. That cap is a design constraint, not a limitation: it
keeps `append()` cheap, since every write re-verifies the chain. An estate is
therefore a *set* of runs, one per workload, and this module is the layer across
them that did not exist.

Two artefacts with opposite lifecycles:

    journals   large, needed rarely, must replay byte-identically
    index      one bounded row per run, needed constantly, kept forever

Three properties hold:

1. Every index row is derivable from its journal. Nothing is recorded here that
   cannot be recomputed while the journal survives.
2. Retention is a customer policy. The default is thirteen months — one annual
   audit cycle plus a month — because the product promises replay next quarter
   and a promise with an unstated condition is not one.
3. A pruned journal leaves its hash behind. A missing run is a known gap with a
   date, never a silent absence.
"""

from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import json
import re
from pathlib import Path
import sqlite3

from lightyear_data.contracts import content_hash

DEFAULT_RETENTION_DAYS = 396          # 13 months
SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  run_id           TEXT PRIMARY KEY,
  estate           TEXT NOT NULL,
  workload         TEXT NOT NULL,
  started_at       TEXT NOT NULL,
  ended_at         TEXT,
  terminal         TEXT,
  actions_completed INTEGER NOT NULL DEFAULT 0,
  awaiting_human   INTEGER NOT NULL DEFAULT 0,
  blocked_access   INTEGER NOT NULL DEFAULT 0,
  blocked_internal INTEGER NOT NULL DEFAULT 0,
  rounds           INTEGER NOT NULL DEFAULT 0,
  model_calls      INTEGER NOT NULL DEFAULT 0,
  journal_sha256   TEXT NOT NULL,
  journal_path     TEXT NOT NULL,
  journal_bytes    INTEGER NOT NULL DEFAULT 0,
  journal_pruned_at TEXT
);
CREATE INDEX IF NOT EXISTS runs_by_time ON runs (estate, started_at);
PRAGMA user_version=1;
"""


@dataclass(frozen=True)
class Retention:
    """What the customer has decided. Not a product default in disguise."""
    journal_days: int = DEFAULT_RETENTION_DAYS
    index_forever: bool = True

    def __post_init__(self):
        if type(self.journal_days) is not int or self.journal_days < 1 or self.index_forever is not True:
            raise ValueError("Retention requires positive journal days and a permanent index")

    def cutoff(self, now: datetime | None = None) -> datetime:
        return (now or datetime.now(timezone.utc)) - timedelta(days=self.journal_days)


class RunIndex:
    """One row per run, across runs. Journals stay where they are."""

    def __init__(self, path: Path, *, read_only: bool = False):
        source = Path(path).absolute()
        if source.is_symlink():
            raise ValueError("Symbolic index path is not allowed")
        self.path = source.resolve()
        self.read_only = read_only
        if not read_only:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._db()) as db:
            if not read_only:
                with db:
                    db.executescript(SCHEMA)
            if db.execute("PRAGMA user_version").fetchone()[0] != 1:
                raise ValueError("Unsupported run index schema")
            columns = {r[1] for r in db.execute("PRAGMA table_info(runs)")}
            required = {"run_id", "estate", "workload", "started_at", "ended_at", "terminal",
                        "actions_completed", "awaiting_human", "blocked_access", "blocked_internal",
                        "rounds", "model_calls", "journal_sha256", "journal_path", "journal_bytes",
                        "journal_pruned_at"}
            if columns != required:
                raise ValueError("Invalid run index schema")

    def _db(self) -> sqlite3.Connection:
        if self.read_only:
            db = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)
            db.execute("PRAGMA query_only=ON")
        else:
            db = sqlite3.connect(self.path)
            db.execute("PRAGMA synchronous=FULL")
        db.row_factory = sqlite3.Row
        return db

    def _writer(self):
        if self.read_only:
            raise ValueError("Read-only run index cannot write")

    def record(self, run_id: str, estate: str, workload: str,
               events: list[dict], journal_path: Path) -> dict:
        """Record a finished journal without changing an existing run identity."""
        self._writer()
        _run_id(run_id)
        row = summarise(run_id, estate, workload, events)
        source = Path(journal_path).absolute()
        if source.is_symlink() or source.name != f"{run_id}.json.gz":
            raise ValueError("Journal must be a regular run-id.json.gz file")
        path = source.resolve(strict=True)
        raw = path.read_bytes()
        with gzip.open(path, "rb") as journal:
            decoded = journal.read(16 * 1024 * 1024 + 1)
        if len(decoded) > 16 * 1024 * 1024:
            raise ValueError("Journal exceeds the bounded size")
        stored = json.loads(decoded)
        if (stored.get("events") if isinstance(stored, dict) else stored) != events:
            raise ValueError("Journal does not match the supplied events")
        row.update(journal_sha256=hashlib.sha256(raw).hexdigest(), journal_path=str(path),
                   journal_bytes=len(raw))
        cols = ", ".join(row)
        marks = ", ".join("?" for _ in row)
        with closing(self._db()) as db, db:
            existing = db.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if existing:
                if any(existing[k] != v for k, v in row.items()):
                    raise ValueError("Run identity already records a different journal")
                return dict(existing)
            db.execute(f"INSERT INTO runs ({cols}) VALUES ({marks})", tuple(row.values()))
        return row

    def prune(self, journals: Path, policy: Retention,
              now: datetime | None = None, dry_run: bool = False) -> dict:
        """Prune only bound, unchanged journals inside the supplied directory.

        Uses completion time for retention. Missing/moved/changed files remain
        explicit errors, never successful deletion measurements. No scheduler.
        """
        self._writer()
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise ValueError("Retention time must include a timezone")
        current = current.astimezone(timezone.utc)
        cutoff = policy.cutoff(current).isoformat()
        root = Path(journals).resolve(strict=True)
        removed, freed = [], 0
        with closing(self._db()) as db, db:
            stale = db.execute(
                "SELECT * FROM runs WHERE ended_at < ? AND journal_pruned_at IS NULL",
                (cutoff,)).fetchall()
            targets = []
            # Validate the complete batch before deleting any file.
            for row in stale:
                _run_id(row["run_id"])
                candidate = root / f"{row['run_id']}.json.gz"
                if candidate.is_symlink():
                    raise ValueError("Symbolic journal cannot be pruned")
                target = candidate.resolve(strict=True)
                if not target.is_relative_to(root) or target != Path(row["journal_path"]):
                    raise ValueError("Journal is outside its recorded retention directory")
                raw = target.read_bytes()
                if len(raw) != row["journal_bytes"] or hashlib.sha256(raw).hexdigest() != row["journal_sha256"]:
                    raise ValueError("Journal changed since it was recorded")
                targets.append((row, target))
            for row, target in targets:
                if not dry_run:
                    target.unlink()
                    db.execute("UPDATE runs SET journal_pruned_at=? WHERE run_id=?",
                               (current.isoformat(), row["run_id"]))
                removed.append(row["run_id"])
                freed += row["journal_bytes"]
        return {"pruned": len(removed), "freed_bytes": freed,
                "cutoff": cutoff, "run_ids": removed[:20], "dry_run": dry_run}

    # ── reading ──────────────────────────────────────────────────────────
    def convergence(self, estate: str, weeks: int = 12) -> list[dict]:
        """Weekly action activity, not resolved findings. Reads rows, never journals."""
        if type(weeks) is not int or not 1 <= weeks <= 52:
            raise ValueError("Weeks must be between 1 and 52")
        with closing(self._db()) as db:
            rows = db.execute(
                "SELECT strftime('%Y-W%W', started_at) AS week, "
                "  SUM(actions_completed) AS actions_completed, SUM(awaiting_human) AS awaiting_human, "
                "  SUM(blocked_access) AS blocked_access, "
                "  SUM(blocked_internal) AS blocked_internal, COUNT(*) AS runs "
                "FROM runs WHERE estate=? GROUP BY week ORDER BY week DESC LIMIT ?",
                (estate, weeks)).fetchall()
        return [dict(r) for r in reversed(rows)]

    def storage(self) -> dict:
        """What this is costing, for the tower to show before anyone asks."""
        with closing(self._db()) as db:
            row = db.execute(
                "SELECT COUNT(*) AS runs, "
                "  SUM(CASE WHEN journal_pruned_at IS NULL THEN journal_bytes ELSE 0 END) AS live_bytes, "
                "  SUM(CASE WHEN journal_pruned_at IS NOT NULL THEN 1 ELSE 0 END) AS pruned, "
                "  MIN(started_at) AS oldest, MAX(started_at) AS newest "
                "FROM runs").fetchone()
        return {"runs": row["runs"] or 0,
                "journal_bytes": row["live_bytes"] or 0,
                "pruned_runs": row["pruned"] or 0,
                "oldest_run": row["oldest"], "newest_run": row["newest"],
                "index_bytes": self.path.stat().st_size if self.path.exists() else 0}


# ── derivation ───────────────────────────────────────────────────────────
def summarise(run_id: str, estate: str, workload: str, events: list[dict]) -> dict:
    """Action-event counts, computed from the journal. No semantic verdicts are inferred.

    Emitted at halt. Because it is derivable, a lost or suspect index can be
    rebuilt from any journal that still exists.
    """
    _run_id(run_id)
    if not estate or not workload or not 2 <= len(events) <= 256:
        raise ValueError("A bounded finished journal and estate/workload are required")
    if events[0].get("type") != "started" or events[-1].get("type") != "halted":
        raise ValueError("Only a finished journal may be indexed")
    previous = None
    last_time = None
    for i, event in enumerate(events, 1):
        if event.get("sequence") != i or event.get("previous_sha256") != previous or event.get("content_sha256") != content_hash(event):
            raise ValueError("Journal integrity check failed")
        when = datetime.fromisoformat(event["at"])
        if when.tzinfo is None or (last_time is not None and when < last_time):
            raise ValueError("Invalid journal timestamp")
        if i < len(events) and event.get("type") == "halted":
            raise ValueError("Events after halt")
        previous, last_time = event["content_sha256"], when
    actions_completed = awaiting = blocked_access = blocked_internal = rounds = calls = 0
    terminal = started = ended = None
    for event in events:
        kind = event.get("type")
        payload = event.get("payload", {})
        if kind == "started":
            started = event.get("at")
        elif kind == "round":
            rounds += 1
        elif kind == "result":
            actions_completed += 1
            calls += int(payload.get("boundary", {}).get("model_calls", 0) or 0)
        elif kind == "blocked":
            reason = str(payload.get("reason", "")).lower()
            if "decision" in reason or "authority" in reason:
                awaiting += 1
            elif "authoris" in reason or "authoriz" in reason or "credential" in reason:
                blocked_access += 1
            else:
                blocked_internal += 1
        elif kind == "halted":
            terminal = payload.get("reason")
            ended = event.get("at")
    return {"run_id": run_id, "estate": estate, "workload": workload,
            "started_at": datetime.fromisoformat(started).astimezone(timezone.utc).isoformat(),
            "ended_at": datetime.fromisoformat(ended).astimezone(timezone.utc).isoformat(), "terminal": terminal,
            "actions_completed": actions_completed, "awaiting_human": awaiting,
            "blocked_access": blocked_access, "blocked_internal": blocked_internal,
            "rounds": rounds, "model_calls": calls}


def _run_id(value: str):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", value):
        raise ValueError("Invalid run id")
