from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import Counter
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


class PortfolioStore:
    """Read-only portfolio control-tower projection; it exposes no dispatch authority."""

    def __init__(self, plan_path: Path, runs_root: Path) -> None:
        self.plan_path = plan_path.resolve()
        self.runs_root = runs_root.resolve()

    def summary(self) -> dict[str, Any]:
        if not self.plan_path.is_file():
            return {
                "status": "not_configured",
                "orders": [],
                "conflicts": [],
                "waves": [],
                "approval": {"required": False, "authority": "human"},
                "runs": [],
                "read_only": True,
            }
        plan = json.loads(self.plan_path.read_text(encoding="utf-8"))
        if plan.get("content_sha256") != canonical_hash(plan, {"content_sha256"}):
            raise ValueError("Portfolio plan snapshot hash is invalid")
        runs = []
        if self.runs_root.is_dir():
            for path in self.runs_root.rglob("receipt.json"):
                try:
                    receipt = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if receipt.get("receipt_type") != "lightyear-modernization-portfolio-run":
                    continue
                runs.append({
                    "portfolio_id": receipt.get("portfolio_id"),
                    "status": receipt.get("status"),
                    "waves_completed": receipt.get("waves_completed", 0),
                    "cells": len(receipt.get("cells", [])),
                    "receipt_sha256": receipt.get("content_sha256"),
                })
        runs.sort(key=lambda item: item.get("receipt_sha256") or "", reverse=True)
        return {**plan, "runs": runs[:20], "read_only": True}


class DurableStore:
    """Strictly read-only projection of an existing durable SQLite database."""

    def __init__(self, path: Path) -> None:
        self.path = path.resolve()

    def summary(self, event_limit: int = 100) -> dict[str, Any]:
        if not self.path.is_file():
            return {
                "schema_version": "1.0",
                "snapshot_type": "lightyear-durable-control-plane",
                "status": "not_configured",
                "statistics": {"runs": 0, "work_items": 0, "states": {}, "events": 0},
                "runs": [],
                "items": [],
                "events": [],
                "read_only": True,
            }
        connection = sqlite3.connect(
            f"file:{self.path.as_posix()}?mode=ro", uri=True, timeout=5
        )
        connection.row_factory = sqlite3.Row
        try:
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
            event_rows = connection.execute(
                "SELECT * FROM durable_events ORDER BY sequence DESC LIMIT ?", (event_limit,)
            ).fetchall()
            events = [
                {
                    "sequence": row["sequence"],
                    "occurred_at": row["occurred_at"],
                    "run_id": row["run_id"],
                    "item_id": row["item_id"],
                    "kind": row["kind"],
                    "payload": json.loads(row["payload_json"]),
                    "previous_sha256": row["previous_sha256"],
                    "event_sha256": row["event_sha256"],
                }
                for row in reversed(event_rows)
            ]
            approvals = connection.execute(
                "SELECT COUNT(*) FROM approval_consumptions"
            ).fetchone()[0]
            artifacts = connection.execute("SELECT COUNT(*) FROM artifact_index").fetchone()[0]
        finally:
            connection.close()
        result = {
            "schema_version": "1.0",
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
        result["content_sha256"] = canonical_hash(result)
        return result


class EvaluationStore:
    """Read-only projection of privacy-safe evaluation receipts."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def list_evaluations(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = []
        for path in self._receipts():
            try:
                receipt = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            quality = receipt.get("quality_gate", {})
            metrics = quality.get("metrics", {})
            rows.append({
                "evaluation_key": self._key(path, receipt),
                "evaluation_id": receipt.get("evaluation_id"),
                "evaluation_class": receipt.get("evaluation_class"),
                "status": receipt.get("status"),
                "quality_status": quality.get("status", "unreported"),
                "cases": receipt.get("cases", 0),
                "repair_rate": metrics.get("repair_rate", receipt.get("repair_rate", 0.0)),
                "correct_no_change_rate": metrics.get(
                    "correct_no_change_rate", receipt.get("correct_no_change_rate", 0.0)
                ),
                "false_acceptances": metrics.get(
                    "false_acceptances", receipt.get("false_acceptances", 0)
                ),
                "average_input_tokens": metrics.get("average_input_tokens", 0.0),
                "estimated_cost_usd": receipt.get("totals", {}).get(
                    "estimated_cost_usd", 0.0
                ),
                "receipt_sha256": receipt.get("content_sha256"),
            })
        rows.sort(
            key=lambda item: (
                item["quality_status"] == "qualified",
                item["status"] == "passed",
                item["evaluation_id"] or "",
            ),
            reverse=True,
        )
        return rows[: max(1, min(limit, 200))]

    def evaluation(self, selector: str) -> dict[str, Any]:
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9:._-]{2,100}", selector):
            raise KeyError(selector)
        matches = []
        for path in self._receipts():
            receipt = json.loads(path.read_text(encoding="utf-8"))
            if selector in {
                self._key(path, receipt), receipt.get("evaluation_id"),
                receipt.get("content_sha256"),
            }:
                matches.append(receipt)
        if len(matches) != 1:
            raise KeyError(selector)
        return matches[0]

    def _receipts(self) -> list[Path]:
        if not self.root.is_dir():
            return []
        return [
            path for path in self.root.rglob("evaluation.receipt.json")
            if self.root in path.resolve().parents
        ]

    @staticmethod
    def _key(path: Path, receipt: dict[str, Any]) -> str:
        identity = f"{path.resolve()}:{receipt.get('content_sha256', '')}"
        return f"evaluation-{hashlib.sha256(identity.encode()).hexdigest()[:24]}"
