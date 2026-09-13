"""Single engine writer; transactional events and a verifiable receipt chain."""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3

from lightyear_data.contracts import content_hash, seal


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunStore:
    def __init__(self, directory: Path, *, read_only=False):
        self.directory = directory.resolve()
        self.path = self.directory / "events.sqlite3"
        self.read_only = read_only
        self.lock = None
        if not read_only:
            self.directory.mkdir(parents=True, exist_ok=True)
            if self.path.is_symlink() or (self.directory / "writer.lock").is_symlink():
                raise ValueError("Symbolic journal or writer lock is not allowed")
            try:
                self.lock = open(self.directory / "writer.lock", "a+b")
                # Windows byte-range locks also prohibit reading the locked byte.
                # Inspect file size without touching another writer's lock range.
                if os.fstat(self.lock.fileno()).st_size == 0:
                    self.lock.write(b"0")
                    self.lock.flush()
                self.lock.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(self.lock.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                self.close()
                raise ValueError("Another headless engine owns this run") from exc
            with closing(self.connect()) as db, db:
                db.execute("CREATE TABLE IF NOT EXISTS events (sequence INTEGER PRIMARY KEY, envelope TEXT NOT NULL)")

    def close(self):
        if self.lock:
            self.lock.close()
            self.lock = None

    def connect(self):
        if self.read_only:
            return sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)
        db = sqlite3.connect(self.path)
        db.execute("PRAGMA synchronous=FULL")
        return db

    def events(self) -> list[dict]:
        if self.read_only and not self.path.exists():
            return []
        with closing(self.connect()) as db:
            records = [json.loads(row[0]) for row in db.execute("SELECT envelope FROM events ORDER BY sequence LIMIT 257")]
        if len(records) > 256:
            raise ValueError("Execution journal exceeds bounded event count")
        previous = None
        for i, event in enumerate(records, 1):
            if event.get("sequence") != i or event.get("previous_sha256") != previous or event.get("content_sha256") != content_hash(event):
                raise ValueError("Execution journal integrity check failed")
            previous = event["content_sha256"]
        return records

    def append(self, kind: str, payload: dict) -> dict:
        if self.read_only:
            raise ValueError("Read-only execution projection cannot append events")
        events = self.events()
        event = seal({"sequence": len(events) + 1, "previous_sha256": events[-1]["content_sha256"] if events else None,
                      "at": utcnow(), "type": kind, "payload": payload})
        with closing(self.connect()) as db, db:
            db.execute("INSERT INTO events VALUES (?, ?)", (event["sequence"], json.dumps(event, sort_keys=True)))
        return event
