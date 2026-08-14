from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .contracts import canonical_hash
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
        receipt_path = self._receipt_path(selector)
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

    def transcript(self, selector: str, include_private: bool = False) -> dict[str, Any]:
        """Render a controller-mediated, audience-safe view of role exchanges."""
        receipt_path = self._receipt_path(selector)
        run_dir = receipt_path.parent
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        messages = []
        for reference in receipt.get("artifacts", []):
            visibility = reference.get("visibility")
            if visibility == "verifier_private" and not include_private:
                messages.append(
                    {
                        "sequence": len(messages) + 1,
                        "actor": reference.get("role"),
                        "artifact_type": reference.get("artifact_type"),
                        "visibility": visibility,
                        "content_sha256": reference.get("content_sha256"),
                        "content": {"redacted": True},
                    }
                )
                continue
            artifact_path = (run_dir / str(reference.get("path", ""))).resolve()
            if run_dir.resolve() not in artifact_path.parents or not artifact_path.is_file():
                continue
            envelope = json.loads(artifact_path.read_text(encoding="utf-8"))
            content = envelope.get("content", {})
            if reference.get("artifact_type") == "implementer-context":
                content = {
                    "context_type": content.get("context_type"),
                    "approved_roots": content.get("approved_roots", []),
                    "statistics": content.get("statistics", {}),
                    "content_sha256": content.get("content_sha256"),
                }
            elif reference.get("artifact_type") == "model-call-evidence":
                content = {
                    key: content.get(key)
                    for key in (
                        "provider", "model", "role", "input_tokens", "output_tokens",
                        "input_tokens_preflight", "estimated_cost_usd", "request_manifest",
                        "request_sha256", "response_sha256", "content_sha256",
                    )
                    if key in content
                }
            messages.append(
                {
                    "sequence": envelope.get("sequence", len(messages) + 1),
                    "actor": envelope.get("role"),
                    "artifact_type": envelope.get("artifact_type"),
                    "visibility": envelope.get("visibility"),
                    "content_sha256": envelope.get("content_sha256"),
                    "content": content,
                }
            )
        payload = {
            "schema_version": "1.0",
            "transcript_type": "lightyear-controller-mediated-agent-exchange",
            "run_id": receipt.get("run_id"),
            "run_key": self._run_key(run_dir),
            "audience": "verifier" if include_private else "implementer",
            "direct_agent_chat": False,
            "messages": messages,
        }
        payload["content_sha256"] = canonical_hash(payload)
        return payload

    def _receipt_path(self, selector: str) -> Path:
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
        return matches[0]

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
