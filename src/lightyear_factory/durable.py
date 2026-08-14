from __future__ import annotations

import hashlib
import json
import re
import secrets
import sqlite3
import tempfile
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from .contracts import ContractError, WorkOrder, canonical_hash


DURABLE_SCHEMA_VERSION = "1.0"
ACTIVE_STATES = {"queued", "leased", "running"}
TERMINAL_STATES = {"passed", "blocked", "dead_letter"}


def _utc(value: datetime | None = None) -> datetime:
    result = value or datetime.now(timezone.utc)
    if result.tzinfo is None:
        raise ContractError("Durable queue timestamps must include a timezone")
    return result.astimezone(timezone.utc)


def _stamp(value: datetime | None = None) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ContractError("Durable queue timestamp is missing a timezone")
    return parsed.astimezone(timezone.utc)


def _safe_id(value: str, label: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9:._-]{2,120}", value):
        raise ContractError(f"Invalid {label}")
    return value


class DurableQueue:
    """SQLite reference control plane with transactional leases and hash-chained events."""

    def __init__(self, path: Path) -> None:
        self.path = path.resolve()

    def initialize(self) -> dict[str, Any]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._read_connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS control_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS portfolio_runs (
                    run_id TEXT PRIMARY KEY,
                    portfolio_id TEXT NOT NULL,
                    plan_sha256 TEXT NOT NULL,
                    admission_sha256 TEXT,
                    state TEXT NOT NULL,
                    submitted_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS approval_consumptions (
                    approval_sha256 TEXT PRIMARY KEY,
                    plan_sha256 TEXT NOT NULL,
                    run_id TEXT NOT NULL UNIQUE,
                    consumed_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES portfolio_runs(run_id)
                );
                CREATE TABLE IF NOT EXISTS work_items (
                    item_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    work_order_id TEXT NOT NULL,
                    work_order_sha256 TEXT NOT NULL,
                    wave INTEGER NOT NULL CHECK(wave > 0),
                    ordinal INTEGER NOT NULL CHECK(ordinal > 0),
                    state TEXT NOT NULL,
                    attempt INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL CHECK(max_attempts > 0),
                    available_at TEXT NOT NULL,
                    lease_owner TEXT,
                    lease_token_sha256 TEXT,
                    lease_expires_at TEXT,
                    heartbeat_at TEXT,
                    receipt_sha256 TEXT,
                    error_code TEXT,
                    updated_at TEXT NOT NULL,
                    UNIQUE(run_id, work_order_id),
                    FOREIGN KEY(run_id) REFERENCES portfolio_runs(run_id)
                );
                CREATE INDEX IF NOT EXISTS idx_work_ready
                    ON work_items(state, available_at, run_id, wave, ordinal);
                CREATE TABLE IF NOT EXISTS artifact_index (
                    artifact_sha256 TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    artifact_type TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES portfolio_runs(run_id),
                    FOREIGN KEY(item_id) REFERENCES work_items(item_id)
                );
                CREATE TABLE IF NOT EXISTS durable_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    occurred_at TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    item_id TEXT,
                    kind TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    previous_sha256 TEXT,
                    event_sha256 TEXT NOT NULL UNIQUE
                );
                """
            )
            existing = connection.execute(
                "SELECT value FROM control_meta WHERE key='schema_version'"
            ).fetchone()
            if existing and existing[0] != DURABLE_SCHEMA_VERSION:
                raise ContractError("Unsupported durable control-plane schema")
            connection.execute(
                "INSERT OR IGNORE INTO control_meta(key, value) VALUES('schema_version', ?)",
                (DURABLE_SCHEMA_VERSION,),
            )
        return {
            "schema_version": DURABLE_SCHEMA_VERSION,
            "status": "passed",
            "database": str(self.path),
        }

    def submit(
        self,
        plan: dict[str, Any],
        run_id: str,
        admission: dict[str, Any] | None = None,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        self.initialize()
        run_id = _safe_id(run_id, "durable portfolio run id")
        if plan.get("content_sha256") != canonical_hash(plan, {"content_sha256"}):
            raise ContractError("Durable submission plan hash is invalid")
        if plan.get("plan_type") != "lightyear-modernization-portfolio-plan":
            raise ContractError("Durable submission requires a portfolio plan")
        approval_required = bool(plan.get("approval", {}).get("required"))
        if approval_required:
            if not admission or admission.get("status") != "passed":
                raise ContractError("Durable submission requires human-approved admission")
            if admission.get("receipt_type") != "lightyear-portfolio-admission":
                raise ContractError("Durable admission receipt type is invalid")
            if admission.get("plan_sha256") != plan["content_sha256"]:
                raise ContractError("Durable admission targets a different portfolio plan")
            if admission.get("approver_kind") != "human":
                raise ContractError("Durable admission must originate from a human approver")
            if not re.fullmatch(r"[0-9a-f]{64}", str(admission.get("signature_sha256", ""))):
                raise ContractError("Durable admission is missing verified signature evidence")
            if admission.get("content_sha256") != canonical_hash(
                admission, {"content_sha256"}
            ):
                raise ContractError("Durable admission receipt hash is invalid")
        admitted_sha = admission.get("content_sha256") if admission else None
        submitted = _stamp(now)
        order_by_id = {row["id"]: row for row in plan.get("orders", [])}
        scheduled_ids = [
            order_id
            for wave in plan.get("waves", [])
            for order_id in wave.get("work_order_ids", [])
        ]
        expected_ids = set(scheduled_ids)
        if (
            expected_ids != set(order_by_id)
            or not expected_ids
            or len(scheduled_ids) != len(expected_ids)
        ):
            raise ContractError("Portfolio waves do not cover every work order exactly")
        with self._transaction() as connection:
            existing = connection.execute(
                "SELECT plan_sha256, admission_sha256 FROM portfolio_runs WHERE run_id=?",
                (run_id,),
            ).fetchone()
            if existing:
                if existing[0] != plan["content_sha256"] or existing[1] != admitted_sha:
                    raise ContractError("Durable run id already targets different inputs")
                result = self._run_summary(connection, run_id)
                result["idempotent"] = True
                return result
            connection.execute(
                "INSERT INTO portfolio_runs VALUES(?, ?, ?, ?, 'queued', ?, ?)",
                (
                    run_id,
                    plan["portfolio_id"],
                    plan["content_sha256"],
                    admitted_sha,
                    submitted,
                    submitted,
                ),
            )
            if admission:
                try:
                    connection.execute(
                        "INSERT INTO approval_consumptions VALUES(?, ?, ?, ?)",
                        (admitted_sha, plan["content_sha256"], run_id, submitted),
                    )
                except sqlite3.IntegrityError as exc:
                    raise ContractError("Human portfolio approval has already been consumed") from exc
            for wave in plan["waves"]:
                for ordinal, order_id in enumerate(wave["work_order_ids"], start=1):
                    row = order_by_id[order_id]
                    item_id = f"{run_id}:w{wave['wave']}:{ordinal}"
                    connection.execute(
                        """
                        INSERT INTO work_items(
                            item_id, run_id, work_order_id, work_order_sha256, wave,
                            ordinal, state, max_attempts, available_at, updated_at
                        ) VALUES(?, ?, ?, ?, ?, ?, 'queued', ?, ?, ?)
                        """,
                        (
                            item_id,
                            run_id,
                            order_id,
                            row["work_order_sha256"],
                            int(wave["wave"]),
                            ordinal,
                            int(row.get("max_attempts", 3)),
                            submitted,
                            submitted,
                        ),
                    )
            self._append_event(
                connection,
                run_id,
                None,
                "portfolio_submitted",
                {
                    "portfolio_id": plan["portfolio_id"],
                    "plan_sha256": plan["content_sha256"],
                    "admission_sha256": admitted_sha,
                    "work_items": len(order_by_id),
                },
                submitted,
            )
            result = self._run_summary(connection, run_id)
            result["idempotent"] = False
            return result

    def lease_next(
        self,
        worker_id: str,
        *,
        now: datetime | None = None,
        lease_seconds: int = 60,
    ) -> dict[str, Any] | None:
        self.initialize()
        worker_id = _safe_id(worker_id, "worker id")
        if not 5 <= lease_seconds <= 3600:
            raise ContractError("Lease duration must be between 5 and 3600 seconds")
        current = _utc(now)
        current_stamp = _stamp(current)
        expiry = _stamp(current + timedelta(seconds=lease_seconds))
        with self._transaction() as connection:
            self._recover_expired(connection, current)
            row = connection.execute(
                """
                SELECT item_id, run_id, work_order_id, work_order_sha256, wave,
                       ordinal, attempt, max_attempts
                FROM work_items AS candidate
                WHERE state='queued' AND available_at <= ?
                  AND NOT EXISTS (
                    SELECT 1 FROM work_items AS predecessor
                    WHERE predecessor.run_id=candidate.run_id
                      AND predecessor.wave < candidate.wave
                      AND predecessor.state != 'passed'
                  )
                ORDER BY run_id, wave, ordinal
                LIMIT 1
                """,
                (current_stamp,),
            ).fetchone()
            if row is None:
                return None
            token = secrets.token_urlsafe(32)
            token_sha = hashlib.sha256(token.encode("utf-8")).hexdigest()
            updated = connection.execute(
                """
                UPDATE work_items
                SET state='leased', attempt=attempt+1, lease_owner=?,
                    lease_token_sha256=?, lease_expires_at=?, heartbeat_at=?, updated_at=?
                WHERE item_id=? AND state='queued'
                """,
                (worker_id, token_sha, expiry, current_stamp, current_stamp, row["item_id"]),
            )
            if updated.rowcount != 1:
                return None
            connection.execute(
                "UPDATE portfolio_runs SET state='running', updated_at=? WHERE run_id=?",
                (current_stamp, row["run_id"]),
            )
            self._append_event(
                connection,
                row["run_id"],
                row["item_id"],
                "work_item_leased",
                {
                    "worker_id": worker_id,
                    "attempt": int(row["attempt"]) + 1,
                    "lease_expires_at": expiry,
                    "lease_token_sha256": token_sha,
                },
                current_stamp,
            )
            return {
                "schema_version": DURABLE_SCHEMA_VERSION,
                "lease_type": "lightyear-durable-work-lease",
                "item_id": row["item_id"],
                "run_id": row["run_id"],
                "work_order_id": row["work_order_id"],
                "work_order_sha256": row["work_order_sha256"],
                "wave": row["wave"],
                "attempt": int(row["attempt"]) + 1,
                "max_attempts": row["max_attempts"],
                "worker_id": worker_id,
                "lease_token": token,
                "lease_expires_at": expiry,
            }

    def start(
        self,
        lease: dict[str, Any],
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        return self._lease_transition(lease, "leased", "running", "work_item_started", now)

    def heartbeat(
        self,
        lease: dict[str, Any],
        *,
        now: datetime | None = None,
        lease_seconds: int = 60,
    ) -> dict[str, Any]:
        if not 5 <= lease_seconds <= 3600:
            raise ContractError("Lease duration must be between 5 and 3600 seconds")
        current = _utc(now)
        expiry = current + timedelta(seconds=lease_seconds)
        with self._transaction() as connection:
            row = self._authorized_lease(connection, lease, {"leased", "running"}, current)
            connection.execute(
                "UPDATE work_items SET heartbeat_at=?, lease_expires_at=?, updated_at=? WHERE item_id=?",
                (_stamp(current), _stamp(expiry), _stamp(current), row["item_id"]),
            )
            self._append_event(
                connection,
                row["run_id"],
                row["item_id"],
                "work_item_heartbeat",
                {"lease_expires_at": _stamp(expiry)},
                _stamp(current),
            )
        return {"status": "passed", "item_id": row["item_id"], "lease_expires_at": _stamp(expiry)}

    def complete(
        self,
        lease: dict[str, Any],
        receipt: dict[str, Any],
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        current = _utc(now)
        if receipt.get("content_sha256") != canonical_hash(receipt, {"content_sha256"}):
            raise ContractError("Work-cell receipt hash is invalid")
        status = receipt.get("status")
        if status not in {"passed", "blocked"}:
            raise ContractError("Work-cell receipt must be passed or blocked")
        with self._transaction() as connection:
            row = self._authorized_lease(connection, lease, {"running"}, current)
            connection.execute(
                """
                UPDATE work_items
                SET state=?, receipt_sha256=?, error_code=?, lease_owner=NULL,
                    lease_token_sha256=NULL, lease_expires_at=NULL, heartbeat_at=NULL, updated_at=?
                WHERE item_id=?
                """,
                (
                    status,
                    receipt["content_sha256"],
                    None if status == "passed" else "acceptance_blocked",
                    _stamp(current),
                    row["item_id"],
                ),
            )
            connection.execute(
                "INSERT OR IGNORE INTO artifact_index VALUES(?, ?, ?, 'work-cell-receipt', ?)",
                (receipt["content_sha256"], row["run_id"], row["item_id"], _stamp(current)),
            )
            self._append_event(
                connection,
                row["run_id"],
                row["item_id"],
                "work_item_completed",
                {"status": status, "receipt_sha256": receipt["content_sha256"]},
                _stamp(current),
            )
            if status == "blocked":
                self._block_descendants(connection, row["run_id"], int(row["wave"]), current)
            self._refresh_run(connection, row["run_id"], current)
            return self._run_summary(connection, row["run_id"])

    def fail(
        self,
        lease: dict[str, Any],
        error_code: str,
        *,
        now: datetime | None = None,
        backoff_seconds: int = 5,
    ) -> dict[str, Any]:
        current = _utc(now)
        error_code = _safe_id(error_code, "worker error code")
        if not 0 <= backoff_seconds <= 3600:
            raise ContractError("Retry backoff must be between 0 and 3600 seconds")
        with self._transaction() as connection:
            row = self._authorized_lease(connection, lease, {"leased", "running"}, current)
            terminal = int(row["attempt"]) >= int(row["max_attempts"])
            state = "dead_letter" if terminal else "queued"
            available = _stamp(current + timedelta(seconds=backoff_seconds))
            connection.execute(
                """
                UPDATE work_items
                SET state=?, available_at=?, error_code=?, lease_owner=NULL,
                    lease_token_sha256=NULL, lease_expires_at=NULL, heartbeat_at=NULL, updated_at=?
                WHERE item_id=?
                """,
                (state, available, error_code, _stamp(current), row["item_id"]),
            )
            self._append_event(
                connection,
                row["run_id"],
                row["item_id"],
                "work_item_dead_lettered" if terminal else "work_item_retry_scheduled",
                {
                    "attempt": row["attempt"],
                    "error_code": error_code,
                    "available_at": available,
                },
                _stamp(current),
            )
            if terminal:
                self._block_descendants(connection, row["run_id"], int(row["wave"]), current)
            self._refresh_run(connection, row["run_id"], current)
            return self._run_summary(connection, row["run_id"])

    def recover_expired(self, *, now: datetime | None = None) -> dict[str, Any]:
        current = _utc(now)
        with self._transaction() as connection:
            recovered = self._recover_expired(connection, current)
            run_ids = sorted({item["run_id"] for item in recovered})
            for run_id in run_ids:
                self._refresh_run(connection, run_id, current)
        return {
            "schema_version": DURABLE_SCHEMA_VERSION,
            "status": "passed",
            "recovered": len(recovered),
            "items": recovered,
        }

    def snapshot(self, *, event_limit: int = 200) -> dict[str, Any]:
        self.initialize()
        with self._read_connection() as connection:
            runs = [dict(row) for row in connection.execute(
                "SELECT * FROM portfolio_runs ORDER BY submitted_at DESC, run_id"
            )]
            items = [dict(row) for row in connection.execute(
                """
                SELECT item_id, run_id, work_order_id, wave, ordinal, state, attempt,
                       max_attempts, available_at, lease_owner, lease_expires_at,
                       receipt_sha256, error_code, updated_at
                FROM work_items ORDER BY run_id, wave, ordinal
                """
            )]
            events = [self._event_dict(row) for row in connection.execute(
                "SELECT * FROM durable_events ORDER BY sequence DESC LIMIT ?", (event_limit,)
            )]
            events.reverse()
            approvals = connection.execute("SELECT COUNT(*) FROM approval_consumptions").fetchone()[0]
            artifacts = connection.execute("SELECT COUNT(*) FROM artifact_index").fetchone()[0]
        payload = {
            "schema_version": DURABLE_SCHEMA_VERSION,
            "snapshot_type": "lightyear-durable-control-plane",
            "status": "passed",
            "statistics": {
                "runs": len(runs),
                "work_items": len(items),
                "states": dict(sorted(Counter(item["state"] for item in items).items())),
                "consumed_approvals": approvals,
                "indexed_artifacts": artifacts,
                "events": len(events),
            },
            "runs": runs,
            "items": items,
            "events": events,
            "read_only": True,
        }
        payload["content_sha256"] = canonical_hash(payload)
        return payload

    def validate(self) -> dict[str, Any]:
        self.initialize()
        errors: list[str] = []
        with self._read_connection() as connection:
            previous = None
            for row in connection.execute("SELECT * FROM durable_events ORDER BY sequence"):
                event = self._event_dict(row)
                if event["previous_sha256"] != previous:
                    errors.append(f"event:{event['sequence']}:previous-hash")
                expected = canonical_hash(event, {"event_sha256", "sequence"})
                if expected != event["event_sha256"]:
                    errors.append(f"event:{event['sequence']}:content-hash")
                previous = event["event_sha256"]
            orphan = connection.execute(
                """
                SELECT COUNT(*) FROM work_items w
                LEFT JOIN portfolio_runs r ON r.run_id=w.run_id WHERE r.run_id IS NULL
                """
            ).fetchone()[0]
            if orphan:
                errors.append("orphan-work-items")
            duplicate_active = connection.execute(
                """
                SELECT COUNT(*) FROM (
                  SELECT run_id, work_order_id, COUNT(*) count FROM work_items
                  GROUP BY run_id, work_order_id HAVING count > 1
                )
                """
            ).fetchone()[0]
            if duplicate_active:
                errors.append("duplicate-work-items")
        result = {
            "schema_version": DURABLE_SCHEMA_VERSION,
            "status": "failed" if errors else "passed",
            "errors": errors,
        }
        result["content_sha256"] = canonical_hash(result)
        return result

    def _lease_transition(
        self,
        lease: dict[str, Any],
        expected: str,
        target: str,
        event_kind: str,
        now: datetime | None,
    ) -> dict[str, Any]:
        current = _utc(now)
        with self._transaction() as connection:
            row = self._authorized_lease(connection, lease, {expected}, current)
            connection.execute(
                "UPDATE work_items SET state=?, updated_at=? WHERE item_id=?",
                (target, _stamp(current), row["item_id"]),
            )
            self._append_event(
                connection,
                row["run_id"],
                row["item_id"],
                event_kind,
                {"worker_id": row["lease_owner"], "attempt": row["attempt"]},
                _stamp(current),
            )
        return {"status": "passed", "item_id": row["item_id"], "state": target}

    def _authorized_lease(
        self,
        connection: sqlite3.Connection,
        lease: dict[str, Any],
        states: set[str],
        now: datetime,
    ) -> sqlite3.Row:
        item_id = str(lease.get("item_id", ""))
        worker = str(lease.get("worker_id", ""))
        token = str(lease.get("lease_token", ""))
        token_sha = hashlib.sha256(token.encode("utf-8")).hexdigest()
        row = connection.execute("SELECT * FROM work_items WHERE item_id=?", (item_id,)).fetchone()
        if row is None or row["state"] not in states:
            raise ContractError("Work item is not in the required lease state")
        if row["lease_owner"] != worker or not secrets.compare_digest(
            str(row["lease_token_sha256"]), token_sha
        ):
            raise ContractError("Work-item lease authority is invalid")
        if not row["lease_expires_at"] or _parse(row["lease_expires_at"]) <= now:
            raise ContractError("Work-item lease has expired")
        return row

    def _recover_expired(
        self, connection: sqlite3.Connection, now: datetime
    ) -> list[dict[str, Any]]:
        rows = connection.execute(
            """
            SELECT * FROM work_items
            WHERE state IN ('leased', 'running') AND lease_expires_at <= ?
            ORDER BY run_id, wave, ordinal
            """,
            (_stamp(now),),
        ).fetchall()
        recovered = []
        for row in rows:
            terminal = int(row["attempt"]) >= int(row["max_attempts"])
            state = "dead_letter" if terminal else "queued"
            connection.execute(
                """
                UPDATE work_items SET state=?, available_at=?, error_code='lease_expired',
                    lease_owner=NULL, lease_token_sha256=NULL, lease_expires_at=NULL,
                    heartbeat_at=NULL, updated_at=? WHERE item_id=?
                """,
                (state, _stamp(now), _stamp(now), row["item_id"]),
            )
            self._append_event(
                connection,
                row["run_id"],
                row["item_id"],
                "work_item_dead_lettered" if terminal else "work_item_lease_recovered",
                {"attempt": row["attempt"], "prior_worker": row["lease_owner"]},
                _stamp(now),
            )
            if terminal:
                self._block_descendants(connection, row["run_id"], int(row["wave"]), now)
            recovered.append({"item_id": row["item_id"], "run_id": row["run_id"], "state": state})
        return recovered

    def _block_descendants(
        self,
        connection: sqlite3.Connection,
        run_id: str,
        wave: int,
        now: datetime,
    ) -> None:
        rows = connection.execute(
            """
            SELECT item_id FROM work_items
            WHERE run_id=? AND wave>? AND state='queued' ORDER BY wave, ordinal
            """,
            (run_id, wave),
        ).fetchall()
        for row in rows:
            connection.execute(
                "UPDATE work_items SET state='blocked', error_code='predecessor_failed', updated_at=? WHERE item_id=?",
                (_stamp(now), row["item_id"]),
            )
            self._append_event(
                connection,
                run_id,
                row["item_id"],
                "work_item_blocked_by_predecessor",
                {"failed_wave": wave},
                _stamp(now),
            )

    def _refresh_run(
        self, connection: sqlite3.Connection, run_id: str, now: datetime
    ) -> None:
        states = [row[0] for row in connection.execute(
            "SELECT state FROM work_items WHERE run_id=?", (run_id,)
        )]
        if states and all(state == "passed" for state in states):
            state = "passed"
        elif any(state in {"blocked", "dead_letter"} for state in states):
            state = "blocked"
        elif any(state in {"leased", "running"} for state in states):
            state = "running"
        else:
            state = "queued"
        connection.execute(
            "UPDATE portfolio_runs SET state=?, updated_at=? WHERE run_id=?",
            (state, _stamp(now), run_id),
        )

    def _run_summary(self, connection: sqlite3.Connection, run_id: str) -> dict[str, Any]:
        run = connection.execute("SELECT * FROM portfolio_runs WHERE run_id=?", (run_id,)).fetchone()
        if run is None:
            raise KeyError(run_id)
        items = [dict(row) for row in connection.execute(
            """
            SELECT item_id, work_order_id, wave, ordinal, state, attempt, max_attempts,
                   available_at, lease_owner, lease_expires_at, receipt_sha256, error_code
            FROM work_items WHERE run_id=? ORDER BY wave, ordinal
            """,
            (run_id,),
        )]
        payload = {
            "schema_version": DURABLE_SCHEMA_VERSION,
            "receipt_type": "lightyear-durable-portfolio-state",
            "run_id": run_id,
            "portfolio_id": run["portfolio_id"],
            "plan_sha256": run["plan_sha256"],
            "admission_sha256": run["admission_sha256"],
            "state": run["state"],
            "submitted_at": run["submitted_at"],
            "updated_at": run["updated_at"],
            "items": items,
        }
        payload["content_sha256"] = canonical_hash(payload)
        return payload

    def _append_event(
        self,
        connection: sqlite3.Connection,
        run_id: str,
        item_id: str | None,
        kind: str,
        payload: dict[str, Any],
        occurred_at: str,
    ) -> None:
        previous_row = connection.execute(
            "SELECT event_sha256 FROM durable_events ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        previous = previous_row[0] if previous_row else None
        event = {
            "occurred_at": occurred_at,
            "run_id": run_id,
            "item_id": item_id,
            "kind": kind,
            "payload": payload,
            "previous_sha256": previous,
        }
        identity = canonical_hash(event)
        connection.execute(
            """
            INSERT INTO durable_events(
                occurred_at, run_id, item_id, kind, payload_json, previous_sha256, event_sha256
            ) VALUES(?, ?, ?, ?, ?, ?, ?)
            """,
            (
                occurred_at,
                run_id,
                item_id,
                kind,
                json.dumps(payload, sort_keys=True, separators=(",", ":")),
                previous,
                identity,
            ),
        )

    @staticmethod
    def _event_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "sequence": row["sequence"],
            "occurred_at": row["occurred_at"],
            "run_id": row["run_id"],
            "item_id": row["item_id"],
            "kind": row["kind"],
            "payload": json.loads(row["payload_json"]),
            "previous_sha256": row["previous_sha256"],
            "event_sha256": row["event_sha256"],
        }

    def _connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA busy_timeout=10000")
        return connection

    class _ConnectionContext:
        def __init__(self, queue: "DurableQueue") -> None:
            self.connection = queue._connection()

        def __enter__(self) -> sqlite3.Connection:
            return self.connection

        def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
            self.connection.close()

    def _read_connection(self) -> "DurableQueue._ConnectionContext":
        return self._ConnectionContext(self)

    class _Transaction:
        def __init__(self, queue: "DurableQueue") -> None:
            self.connection = queue._connection()

        def __enter__(self) -> sqlite3.Connection:
            self.connection.execute("BEGIN IMMEDIATE")
            return self.connection

        def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
            try:
                self.connection.execute("ROLLBACK" if exc_type else "COMMIT")
            finally:
                self.connection.close()

    def _transaction(self) -> "DurableQueue._Transaction":
        return self._Transaction(self)


class DurableWorker:
    """One worker iteration; process lifetime is deliberately disposable."""

    def __init__(
        self,
        queue: DurableQueue,
        worker_id: str,
        orders: dict[str, WorkOrder],
        execute: Callable[[WorkOrder, str], dict[str, Any]],
    ) -> None:
        self.queue = queue
        self.worker_id = worker_id
        self.orders = orders
        self.execute = execute

    def run_once(self, *, now: datetime | None = None) -> dict[str, Any] | None:
        lease = self.queue.lease_next(self.worker_id, now=now)
        if lease is None:
            return None
        order = self.orders.get(lease["work_order_id"])
        if order is None or order.content_sha256 != lease["work_order_sha256"]:
            return self.queue.fail(lease, "work_order_identity_mismatch", now=now)
        self.queue.start(lease, now=now)
        try:
            receipt = self.execute(order, lease["item_id"])
        except Exception as exc:
            return self.queue.fail(
                lease, f"worker_{type(exc).__name__.lower()}", now=now
            )
        return self.queue.complete(lease, receipt, now=now)


def run_durable_conformance(
    project_root: Path, output: Path | None = None
) -> dict[str, Any]:
    """Prove deterministic recovery semantics without claiming production equivalence."""
    from .contracts import write_json
    from .portfolio import (
        PortfolioManifest,
        plan_portfolio,
        sign_portfolio_approval,
        verify_portfolio_approval,
    )

    root = project_root.resolve()
    epoch = datetime(2026, 8, 15, tzinfo=timezone.utc)
    plan, _ = plan_portfolio(
        PortfolioManifest.load(root / "factory/portfolio/carddemo-portfolio.json"),
        root,
        root / "knowledge/graph.snapshot.json.gz",
    )
    key = b"lightyear-durable-conformance-key-32-bytes"
    envelope = sign_portfolio_approval(
        plan,
        key,
        approver_id="conformance-human-fixture",
        key_id="durable-conformance",
        issued_at=epoch,
        ttl_seconds=600,
    )
    admission = verify_portfolio_approval(
        plan, envelope, {"durable-conformance": key}, now=epoch
    )
    with tempfile.TemporaryDirectory() as directory:
        queue = DurableQueue(Path(directory) / "control.sqlite3")
        queue.submit(plan, "conformance-run-001", admission, now=epoch)
        killed = queue.lease_next("worker-killed", now=epoch, lease_seconds=60)
        if killed is None:
            raise ContractError("Conformance queue did not produce the first lease")
        queue.start(killed, now=epoch)
        recovered = queue.recover_expired(now=epoch + timedelta(seconds=61))
        replacement = queue.lease_next(
            "worker-replacement", now=epoch + timedelta(seconds=61), lease_seconds=60
        )
        if replacement is None or replacement["item_id"] != killed["item_id"]:
            raise ContractError("Conformance recovery did not re-lease the killed work cell")
        queue.start(replacement, now=epoch + timedelta(seconds=61))

        def conformance_receipt(order_id: str) -> dict[str, Any]:
            item = {"status": "passed", "receipt_type": "durable-conformance-cell", "order": order_id}
            item["content_sha256"] = canonical_hash(item)
            return item

        queue.complete(
            replacement,
            conformance_receipt(replacement["work_order_id"]),
            now=epoch + timedelta(seconds=62),
        )
        while True:
            lease = queue.lease_next(
                "worker-steady", now=epoch + timedelta(seconds=63), lease_seconds=60
            )
            if lease is None:
                break
            queue.start(lease, now=epoch + timedelta(seconds=63))
            final = queue.complete(
                lease,
                conformance_receipt(lease["work_order_id"]),
                now=epoch + timedelta(seconds=64),
            )
        approval_replay_rejected = False
        try:
            queue.submit(plan, "conformance-run-002", admission, now=epoch)
        except ContractError as exc:
            approval_replay_rejected = "already been consumed" in str(exc)
        validation = queue.validate()
        snapshot = queue.snapshot()
    checks = {
        "atomic_recovery": recovered["recovered"] == 1,
        "same_item_released_after_crash": replacement["item_id"] == killed["item_id"],
        "attempt_incremented": replacement["attempt"] == 2,
        "portfolio_completed_once": final["state"] == "passed",
        "approval_replay_rejected": approval_replay_rejected,
        "event_chain_valid": validation["status"] == "passed",
        "receipts_content_addressed": snapshot["statistics"]["indexed_artifacts"] == len(plan["orders"]),
    }
    policy = json.loads((root / "factory/durable/policy.json").read_text(encoding="utf-8"))
    result = {
        "schema_version": "1.0",
        "receipt_type": "lightyear-durable-control-plane-conformance",
        "status": "passed" if all(checks.values()) else "failed",
        "evidence_class": "synthetic-crash-recovery-conformance",
        "reference_backend": "sqlite-wal",
        "plan_sha256": plan["content_sha256"],
        "policy_sha256": canonical_hash(policy),
        "checks": checks,
        "statistics": {
            "work_items": len(plan["orders"]),
            "recovered_leases": recovered["recovered"],
            "indexed_receipts": snapshot["statistics"]["indexed_artifacts"],
        },
        "limitations": [
            "This proves local control-plane mechanics, not distributed PostgreSQL behavior.",
            "Synthetic worker termination does not establish live z/OS equivalence.",
        ],
    }
    result["content_sha256"] = canonical_hash(result)
    if output is not None:
        write_json(result, output)
    return result
