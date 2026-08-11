from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .ledger import RunLedger


class FactoryRunStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        if not self.root.is_dir():
            return []
        summaries = []
        for path in self.root.rglob("summary.json"):
            try:
                summary = json.loads(path.read_text(encoding="utf-8"))
                summary["run_key"] = self._run_key(path.parent)
                summaries.append(summary)
            except (OSError, json.JSONDecodeError):
                continue
        summaries.sort(key=lambda item: (item.get("updated_at", ""), item.get("run_id", "")), reverse=True)
        return summaries[: max(1, min(limit, 200))]

    def run(self, selector: str, include_private: bool = False) -> dict[str, Any]:
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{2,80}", selector):
            raise KeyError(selector)
        receipts = [
            item for item in self.root.rglob("receipt.json")
            if self.root in item.resolve().parents
        ] if self.root.is_dir() else []
        keyed = [item for item in receipts if self._run_key(item.parent) == selector]
        matches = keyed or [item for item in receipts if item.parent.name == selector]
        if len(matches) != 1:
            raise KeyError(selector)
        receipt_path = matches[0]
        run_dir = receipt_path.parent
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        events = RunLedger(run_dir / "events.jsonl").events
        if not include_private:
            receipt = dict(receipt)
            receipt["artifacts"] = [
                item for item in receipt.get("artifacts", [])
                if item.get("visibility") != "verifier_private"
            ]
            events = [self._public_event(item) for item in events]
        return {
            "run_key": self._run_key(run_dir),
            "receipt": receipt,
            "events": events,
        }

    def _run_key(self, run_dir: Path) -> str:
        relative = run_dir.resolve().relative_to(self.root).as_posix()
        digest = hashlib.sha256(relative.encode("utf-8")).hexdigest()[:24]
        return f"factory-{digest}"

    @staticmethod
    def _public_event(event: dict[str, Any]) -> dict[str, Any]:
        public = dict(event)
        payload = dict(public.get("payload", {}))
        if payload.get("visibility") == "verifier_private":
            payload = {
                "artifact_type": payload.get("artifact_type"),
                "content_sha256": payload.get("content_sha256"),
                "role": payload.get("role"),
                "visibility": "verifier_private",
                "redacted": True,
                **({"attempt": payload["attempt"]} if "attempt" in payload else {}),
                **({"status": payload["status"]} if "status" in payload else {}),
            }
        public["payload"] = payload
        return public
