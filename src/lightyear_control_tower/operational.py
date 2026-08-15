from __future__ import annotations

import hashlib
import json
import queue
import sqlite3
import threading
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable


SCHEMA_VERSION = "1.0"
SOURCE_ORDER = ("factory", "portfolio", "recovery", "quality", "memory", "runtime", "audit")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_hash(payload: dict[str, Any], excluded: set[str] | None = None) -> str:
    omitted = excluded or set()
    body = {key: value for key, value in payload.items() if key not in omitted}
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class OperationalSource:
    name: str
    paths: tuple[Path, ...]
    trust_class: str
    expected_interval_seconds: int
    provider: Callable[[], dict[str, Any]]


class OperationalEventStore:
    """Append-only SQLite event ledger with an in-process subscription fan-out."""

    def __init__(self, path: Path, now: Callable[[], datetime] = _utc_now) -> None:
        self.path = path.resolve()
        self.now = now
        self._lock = threading.RLock()
        self._subscribers: set[queue.Queue[dict[str, Any]]] = set()
        self.initialize()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS operational_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    event_type TEXT NOT NULL,
                    source TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    trust_class TEXT NOT NULL,
                    correlation_id TEXT,
                    occurred_at TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    previous_sha256 TEXT,
                    content_sha256 TEXT NOT NULL UNIQUE
                );
                CREATE INDEX IF NOT EXISTS idx_operational_source_sequence
                    ON operational_events(source, sequence);
                CREATE TABLE IF NOT EXISTS source_observations (
                    source TEXT PRIMARY KEY,
                    fingerprint TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    changed_at TEXT NOT NULL,
                    trust_class TEXT NOT NULL,
                    expected_interval_seconds INTEGER NOT NULL,
                    path_count INTEGER NOT NULL
                );
                """
            )

    def append(
        self,
        event_type: str,
        source: str,
        subject: str,
        payload: dict[str, Any],
        *,
        severity: str = "info",
        trust_class: str = "local-observation",
        correlation_id: str | None = None,
        occurred_at: datetime | None = None,
    ) -> dict[str, Any]:
        if severity not in {"info", "warning", "critical"}:
            raise ValueError("Operational event severity is invalid")
        observed = self.now()
        occurred = occurred_at or observed
        with self._lock, closing(sqlite3.connect(self.path)) as connection, connection:
            previous = connection.execute(
                "SELECT content_sha256 FROM operational_events ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            previous_sha = previous[0] if previous else None
            sequence = connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 FROM operational_events"
            ).fetchone()[0]
            envelope: dict[str, Any] = {
                "schema_version": SCHEMA_VERSION,
                "event_type": event_type,
                "source": source,
                "subject": subject,
                "severity": severity,
                "trust_class": trust_class,
                "correlation_id": correlation_id,
                "occurred_at": _stamp(occurred),
                "observed_at": _stamp(observed),
                "payload": payload,
                "previous_sha256": previous_sha,
            }
            envelope["content_sha256"] = _canonical_hash(envelope)
            envelope["event_id"] = f"op-{envelope['content_sha256'][:24]}"
            connection.execute(
                """
                INSERT INTO operational_events(
                    sequence, event_id, event_type, source, subject, severity,
                    trust_class, correlation_id, occurred_at, observed_at,
                    payload_json, previous_sha256, content_sha256
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sequence, envelope["event_id"], event_type, source, subject, severity,
                    trust_class, correlation_id, envelope["occurred_at"],
                    envelope["observed_at"], json.dumps(payload, sort_keys=True),
                    previous_sha, envelope["content_sha256"],
                ),
            )
            envelope["sequence"] = sequence
        for subscriber in tuple(self._subscribers):
            try:
                subscriber.put_nowait(envelope)
            except queue.Full:
                pass
        return envelope

    def record_observation(
        self,
        source: OperationalSource,
        fingerprint: str,
        path_count: int,
    ) -> tuple[bool, str | None]:
        observed = _stamp(self.now())
        with self._lock, closing(sqlite3.connect(self.path)) as connection, connection:
            existing = connection.execute(
                "SELECT fingerprint, changed_at FROM source_observations WHERE source=?",
                (source.name,),
            ).fetchone()
            changed = existing is None or existing[0] != fingerprint
            changed_at = observed if changed else existing[1]
            connection.execute(
                """
                INSERT INTO source_observations VALUES(?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source) DO UPDATE SET
                    fingerprint=excluded.fingerprint,
                    observed_at=excluded.observed_at,
                    changed_at=excluded.changed_at,
                    trust_class=excluded.trust_class,
                    expected_interval_seconds=excluded.expected_interval_seconds,
                    path_count=excluded.path_count
                """,
                (
                    source.name, fingerprint, observed, changed_at, source.trust_class,
                    source.expected_interval_seconds, path_count,
                ),
            )
        return changed, existing[0] if existing else None

    def observations(self) -> dict[str, dict[str, Any]]:
        with closing(sqlite3.connect(self.path)) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute("SELECT * FROM source_observations").fetchall()
        return {row["source"]: dict(row) for row in rows}

    def events(self, after: int = 0, limit: int = 200) -> list[dict[str, Any]]:
        with closing(sqlite3.connect(self.path)) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """
                SELECT * FROM operational_events WHERE sequence > ?
                ORDER BY sequence DESC LIMIT ?
                """,
                (max(0, after), max(1, min(limit, 1000))),
            ).fetchall()
        return [self._event(dict(row)) for row in reversed(rows)]

    def subscribe(self, after: int = 0) -> queue.Queue[dict[str, Any]]:
        channel: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=256)
        for event in self.events(after=after, limit=256):
            channel.put_nowait(event)
        with self._lock:
            self._subscribers.add(channel)
        return channel

    def unsubscribe(self, channel: queue.Queue[dict[str, Any]]) -> None:
        with self._lock:
            self._subscribers.discard(channel)

    def validate(self) -> dict[str, Any]:
        errors: list[str] = []
        previous: str | None = None
        for event in self.events(limit=1000):
            expected = _canonical_hash(event, {"sequence", "event_id", "content_sha256"})
            if event["previous_sha256"] != previous:
                errors.append(f"event:{event['sequence']}:previous-hash")
            if event["content_sha256"] != expected:
                errors.append(f"event:{event['sequence']}:content-hash")
            if event["event_id"] != f"op-{event['content_sha256'][:24]}":
                errors.append(f"event:{event['sequence']}:identity")
            previous = event["content_sha256"]
        return {"status": "passed" if not errors else "failed", "errors": errors}

    @staticmethod
    def _event(row: dict[str, Any]) -> dict[str, Any]:
        row["payload"] = json.loads(row.pop("payload_json"))
        row["schema_version"] = SCHEMA_VERSION
        return row


class OperationalControlTower:
    """Observes authoritative read models and publishes change/freshness evidence."""

    def __init__(
        self,
        store: OperationalEventStore,
        sources: Iterable[OperationalSource],
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        self.store = store
        self.sources = {source.name: source for source in sources}
        self.now = now
        self._scan_lock = threading.Lock()
        self._active_alert_ids = self._replay_active_alerts()

    def _replay_active_alerts(self) -> set[str]:
        active: set[str] = set()
        for event in self.store.events(limit=1000):
            alert_id = event.get("payload", {}).get("alert_id")
            if not alert_id:
                continue
            if event["event_type"] == "control.alert.opened":
                active.add(alert_id)
            elif event["event_type"] == "control.alert.resolved":
                active.discard(alert_id)
        return active

    def scan(self) -> dict[str, Any]:
        with self._scan_lock:
            changed_sources = []
            for source in self.sources.values():
                fingerprint, path_count = self._fingerprint(source.paths)
                changed, previous = self.store.record_observation(
                    source, fingerprint, path_count
                )
                if changed:
                    changed_sources.append(source.name)
                    self.store.append(
                        f"{source.name}.projection.changed",
                        source.name,
                        f"control-tower:{source.name}",
                        {
                            "fingerprint": fingerprint,
                            "previous_fingerprint": previous,
                            "path_count": path_count,
                            "refresh_hint": source.name,
                        },
                        trust_class=source.trust_class,
                    )
            alerts = self._alerts()
            current_ids = {alert["alert_id"] for alert in alerts}
            for alert in alerts:
                if alert["alert_id"] not in self._active_alert_ids:
                    self.store.append(
                        "control.alert.opened",
                        alert["source"],
                        alert["subject"],
                        alert,
                        severity=alert["severity"],
                        trust_class=alert["trust_class"],
                    )
            for resolved in sorted(self._active_alert_ids - current_ids):
                self.store.append(
                    "control.alert.resolved",
                    "control-tower",
                    resolved,
                    {"alert_id": resolved},
                    trust_class="derived-control-plane",
                )
            self._active_alert_ids = current_ids
            return {"changed_sources": changed_sources, "alerts": alerts}

    def status(self) -> dict[str, Any]:
        observations = self.store.observations()
        now = self.now()
        sources = []
        for name in SOURCE_ORDER:
            source = self.sources.get(name)
            if source is None:
                continue
            observation = observations.get(name)
            if observation is None:
                sources.append({
                    "source": name,
                    "freshness": "unavailable",
                    "age_seconds": None,
                    "trust_class": source.trust_class,
                    "last_observed_at": None,
                    "last_changed_at": None,
                    "expected_interval_seconds": source.expected_interval_seconds,
                })
                continue
            if observation["path_count"] == 0:
                sources.append({
                    "source": name,
                    "freshness": "unavailable",
                    "age_seconds": None,
                    "trust_class": source.trust_class,
                    "last_observed_at": observation["observed_at"],
                    "last_changed_at": observation["changed_at"],
                    "expected_interval_seconds": source.expected_interval_seconds,
                    "fingerprint": observation["fingerprint"],
                })
                continue
            freshness_time = (
                observation["changed_at"] if name == "runtime" else observation["observed_at"]
            )
            observed = datetime.fromisoformat(freshness_time.replace("Z", "+00:00"))
            age = max(0, int((now - observed).total_seconds()))
            expected = source.expected_interval_seconds
            freshness = "live" if age <= expected * 2 else "delayed" if age <= expected * 6 else "stale"
            sources.append({
                "source": name,
                "freshness": freshness,
                "age_seconds": age,
                "trust_class": source.trust_class,
                "last_observed_at": observation["observed_at"],
                "last_changed_at": observation["changed_at"],
                "expected_interval_seconds": expected,
                "fingerprint": observation["fingerprint"],
            })
        events = self.store.events(limit=1)
        alerts = self._alerts()
        return {
            "schema_version": SCHEMA_VERSION,
            "plane_type": "lightyear-live-evidence-control-plane",
            "status": "critical" if any(item["severity"] == "critical" for item in alerts)
            else "warning" if alerts else "healthy",
            "connection": "live",
            "read_only": True,
            "command_plane": "disabled",
            "latest_sequence": events[-1]["sequence"] if events else 0,
            "sources": sources,
            "alerts": alerts,
        }

    def _alerts(self) -> list[dict[str, Any]]:
        alerts: list[dict[str, Any]] = []
        recovery = self.sources.get("recovery")
        if recovery:
            try:
                summary = recovery.provider()
                now = self.now()
                for item in summary.get("items", []):
                    if item.get("state") == "dead_letter":
                        alerts.append(self._alert(
                            "recovery", "critical", f"dead-letter:{item['item_id']}",
                            item["item_id"], "Work item requires human recovery."))
                    expiry = item.get("lease_expires_at")
                    if item.get("state") in {"leased", "running"} and expiry:
                        parsed = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
                        if parsed < now:
                            alerts.append(self._alert(
                                "recovery", "critical", f"expired-lease:{item['item_id']}",
                                item["item_id"], "Worker lease expired without recovery."))
            except (OSError, ValueError, KeyError, sqlite3.DatabaseError):
                alerts.append(self._alert(
                    "recovery", "warning", "projection-unavailable", "control-tower:recovery",
                    "Recovery projection could not be read."))
        runtime_status = next(
            (item for item in self.status_without_alerts() if item["source"] == "runtime"), None
        )
        if runtime_status and runtime_status["freshness"] == "stale":
            alerts.append(self._alert(
                "runtime", "warning", "runtime-stale", "control-tower:runtime",
                "Runtime evidence is stale relative to its observation policy."))
        audit = self.sources.get("audit")
        if audit:
            try:
                posture = audit.provider().get("trust_posture", {})
                if posture.get("promotion_status") == "blocked":
                    alerts.append(self._alert(
                        "audit", "warning", "promotion-blocked", "release:latest",
                        "The latest release promotion decision is blocked."))
            except (OSError, ValueError, KeyError):
                pass
        return sorted(alerts, key=lambda item: (item["severity"], item["alert_id"]))

    def status_without_alerts(self) -> list[dict[str, Any]]:
        observations = self.store.observations()
        now = self.now()
        rows = []
        for name, source in self.sources.items():
            observation = observations.get(name)
            if not observation or observation["path_count"] == 0:
                rows.append({"source": name, "freshness": "unavailable"})
                continue
            freshness_time = (
                observation["changed_at"] if name == "runtime" else observation["observed_at"]
            )
            observed = datetime.fromisoformat(freshness_time.replace("Z", "+00:00"))
            age = max(0, int((now - observed).total_seconds()))
            freshness = "live" if age <= source.expected_interval_seconds * 2 else (
                "delayed" if age <= source.expected_interval_seconds * 6 else "stale"
            )
            rows.append({"source": name, "freshness": freshness})
        return rows

    @staticmethod
    def _alert(
        source: str, severity: str, code: str, subject: str, message: str
    ) -> dict[str, Any]:
        alert_id = f"alert:{source}:{code}"
        return {
            "alert_id": alert_id,
            "source": source,
            "subject": subject,
            "severity": severity,
            "message": message,
            "trust_class": "derived-control-plane",
        }

    @staticmethod
    def _fingerprint(paths: tuple[Path, ...]) -> tuple[str, int]:
        entries: list[str] = []
        for configured in paths:
            path = configured.resolve()
            if path.is_file():
                stat = path.stat()
                entries.append(f"{path}:{stat.st_size}:{stat.st_mtime_ns}")
            elif path.is_dir():
                for child in sorted(item for item in path.rglob("*") if item.is_file()):
                    if any(part in {"target", "__pycache__", ".git"} for part in child.parts):
                        continue
                    stat = child.stat()
                    entries.append(f"{child}:{stat.st_size}:{stat.st_mtime_ns}")
        body = "\n".join(entries).encode("utf-8")
        return hashlib.sha256(body).hexdigest(), len(entries)


class OperationalMonitor:
    def __init__(self, tower: OperationalControlTower, interval_seconds: float = 2.0) -> None:
        self.tower = tower
        self.interval_seconds = max(0.25, interval_seconds)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self.tower.scan()
        self._thread = threading.Thread(target=self._run, name="lightyear-live-plane", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=max(1.0, self.interval_seconds * 2))

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            try:
                self.tower.scan()
            except Exception:
                # The HTTP status endpoint remains available even if one observation fails.
                continue
