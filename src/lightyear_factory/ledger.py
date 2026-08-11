from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .contracts import canonical_hash


class RunLedger:
    """Append-only, hash-chained event history for one factory run."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.events = self._load()

    def _load(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        events = [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line]
        previous = None
        for sequence, event in enumerate(events, start=1):
            if event.get("sequence") != sequence or event.get("previous_sha256") != previous:
                raise ValueError("Factory run ledger sequence or hash chain is invalid")
            if event.get("event_sha256") != canonical_hash(event, {"event_sha256"}):
                raise ValueError("Factory run ledger event hash is invalid")
            previous = event["event_sha256"]
        return events

    def append(self, state: str, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        event = {
            "sequence": len(self.events) + 1,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "previous_sha256": self.events[-1]["event_sha256"] if self.events else None,
            "state": state,
            "kind": kind,
            "payload": payload,
        }
        event["event_sha256"] = canonical_hash(event)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
            handle.flush()
        self.events.append(event)
        return event

    @property
    def head_sha256(self) -> str | None:
        return self.events[-1]["event_sha256"] if self.events else None

    def verify(self) -> bool:
        RunLedger(self.path)
        return True

