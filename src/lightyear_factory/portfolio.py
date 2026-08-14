from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from lightyear_knowledge_graph.model import graph_hash, load_graph

from .contracts import ContractError, WorkOrder, canonical_hash, safe_relative_path, write_json


PORTFOLIO_SCHEMA_VERSION = "1.0"
RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ContractError("Portfolio timestamps must include a timezone")
    return parsed.astimezone(timezone.utc)


def _validate_key(key: bytes) -> bytes:
    if len(key) < 32:
        raise ContractError("Portfolio approval keys must contain at least 32 bytes")
    return key


def _paths_overlap(left: str, right: str) -> bool:
    left_parts = PurePosixPath(left).parts
    right_parts = PurePosixPath(right).parts
    shorter = min(len(left_parts), len(right_parts))
    return left_parts[:shorter] == right_parts[:shorter]


@dataclass(frozen=True)
class PortfolioManifest:
    portfolio_id: str
    title: str
    work_order_paths: tuple[str, ...]
    max_parallel: int
    approval_risks: tuple[str, ...]
    graph_trace_depth: int
    metadata: dict[str, Any]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PortfolioManifest":
        if payload.get("schema_version") != PORTFOLIO_SCHEMA_VERSION:
            raise ContractError("Unsupported portfolio manifest schema")
        portfolio_id = str(payload.get("id", "")).strip()
        title = str(payload.get("title", "")).strip()
        paths = payload.get("work_orders", [])
        if not portfolio_id or not title or not isinstance(paths, list) or len(paths) < 2:
            raise ContractError("Portfolio id, title, and at least two work orders are required")
        normalized = tuple(safe_relative_path(str(item)) for item in paths)
        if len(set(normalized)) != len(normalized):
            raise ContractError("Portfolio work-order paths must be unique")
        policy = payload.get("policy", {})
        max_parallel = int(policy.get("max_parallel", 2))
        if not 1 <= max_parallel <= 16:
            raise ContractError("Portfolio max_parallel must be between 1 and 16")
        approval_risks = tuple(policy.get("human_approval_required_for", ["high", "critical"]))
        if not approval_risks or any(item not in RISK_ORDER for item in approval_risks):
            raise ContractError("Portfolio approval risks are invalid")
        trace_depth = int(policy.get("graph_trace_depth", 2))
        if not 0 <= trace_depth <= 5:
            raise ContractError("Portfolio graph_trace_depth must be between 0 and 5")
        metadata = payload.get("metadata", {})
        if not isinstance(metadata, dict):
            raise ContractError("Portfolio metadata must be an object")
        return cls(
            portfolio_id, title, normalized, max_parallel, approval_risks, trace_depth, metadata
        )

    @classmethod
    def load(cls, path: Path) -> "PortfolioManifest":
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": PORTFOLIO_SCHEMA_VERSION,
            "id": self.portfolio_id,
            "title": self.title,
            "work_orders": list(self.work_order_paths),
            "policy": {
                "max_parallel": self.max_parallel,
                "human_approval_required_for": list(self.approval_risks),
                "graph_trace_depth": self.graph_trace_depth,
            },
            "metadata": self.metadata,
        }

    @property
    def content_sha256(self) -> str:
        return canonical_hash(self.to_dict())


def load_portfolio_orders(
    manifest: PortfolioManifest, project_root: Path
) -> dict[str, WorkOrder]:
    orders: dict[str, WorkOrder] = {}
    root = project_root.resolve()
    for relative in manifest.work_order_paths:
        path = (root / relative).resolve()
        if root not in path.parents or not path.is_file():
            raise ContractError(f"Portfolio work order is unavailable: {relative}")
        order = WorkOrder.load(path)
        if order.order_id in orders:
            raise ContractError(f"Duplicate portfolio work-order id: {order.order_id}")
        orders[order.order_id] = order
    return orders


def _graph_distances(graph: dict[str, Any], roots: set[str], maximum: int) -> dict[str, int]:
    adjacency: dict[str, set[str]] = {}
    for edge in graph.get("edges", []):
        adjacency.setdefault(edge["source"], set()).add(edge["target"])
        adjacency.setdefault(edge["target"], set()).add(edge["source"])
    distances = {root: 0 for root in roots}
    frontier = sorted(roots)
    while frontier:
        current = frontier.pop(0)
        if distances[current] >= maximum:
            continue
        for neighbor in sorted(adjacency.get(current, set())):
            distance = distances[current] + 1
            if neighbor not in distances or distance < distances[neighbor]:
                distances[neighbor] = distance
                frontier.append(neighbor)
    return distances


def _conflicts(
    orders: dict[str, WorkOrder], graph: dict[str, Any], trace_depth: int
) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    node_ids = {item["id"] for item in graph.get("nodes", [])}
    for order in orders.values():
        missing = sorted(set(order.graph_node_ids) - node_ids)
        if missing:
            raise ContractError(
                f"Work order {order.order_id} references unknown graph nodes: {', '.join(missing)}"
            )
    ids = sorted(orders)
    for index, left_id in enumerate(ids):
        left = orders[left_id]
        for right_id in ids[index + 1 :]:
            right = orders[right_id]
            overlaps = sorted({
                left_path
                for left_path in left.allowed_paths
                for right_path in right.allowed_paths
                if _paths_overlap(left_path, right_path)
            })
            shared_nodes = sorted(set(left.graph_node_ids) & set(right.graph_node_ids))
            dependencies = set(left.metadata.get("depends_on", [])) | set(
                right.metadata.get("depends_on", [])
            )
            if overlaps:
                kind, severity, evidence = "path_overlap", "critical", overlaps
            elif shared_nodes:
                kind, severity, evidence = "graph_scope_overlap", "high", shared_nodes
            elif left_id in dependencies or right_id in dependencies:
                kind, severity, evidence = "declared_dependency", "medium", sorted(dependencies)
            elif trace_depth:
                distances = _graph_distances(graph, set(left.graph_node_ids), trace_depth)
                connected = sorted(
                    node for node in right.graph_node_ids if node in distances
                )
                if not connected:
                    continue
                kind, severity = "graph_dependency", "medium"
                evidence = [f"{node}:distance={distances[node]}" for node in connected]
            else:
                continue
            conflict = {
                "id": "conflict:" + hashlib.sha256(
                    json.dumps([left_id, right_id, kind], separators=(",", ":")).encode()
                ).hexdigest()[:20],
                "orders": [left_id, right_id],
                "kind": kind,
                "severity": severity,
                "evidence": evidence,
                "resolution": "serialize",
            }
            conflicts.append(conflict)
    return conflicts


def _order_risk(order: WorkOrder) -> str:
    declared = str(order.metadata.get("risk", "low")).lower()
    if declared not in RISK_ORDER:
        raise ContractError(f"Work order {order.order_id} has invalid metadata.risk")
    return declared


def plan_portfolio(
    manifest: PortfolioManifest,
    project_root: Path,
    graph_path: Path,
) -> tuple[dict[str, Any], dict[str, WorkOrder]]:
    orders = load_portfolio_orders(manifest, project_root)
    graph = load_graph(graph_path)
    if graph_hash(graph) != graph.get("content_sha256"):
        raise ContractError("Portfolio knowledge graph content hash is invalid")
    conflicts = _conflicts(orders, graph, manifest.graph_trace_depth)
    conflict_pairs = {tuple(item["orders"]) for item in conflicts}
    dependencies = {
        order_id: set(str(item) for item in order.metadata.get("depends_on", []))
        for order_id, order in orders.items()
    }
    for order_id, required in dependencies.items():
        unknown = required - set(orders)
        if unknown:
            raise ContractError(
                f"Work order {order_id} depends on unknown orders: {', '.join(sorted(unknown))}"
            )
    remaining = set(orders)
    completed: set[str] = set()
    waves: list[dict[str, Any]] = []
    while remaining:
        ready = sorted(item for item in remaining if dependencies[item] <= completed)
        if not ready:
            raise ContractError("Portfolio work-order dependencies contain a cycle")
        selected: list[str] = []
        for order_id in ready:
            if len(selected) >= manifest.max_parallel:
                break
            if any(tuple(sorted((order_id, other))) in conflict_pairs for other in selected):
                continue
            selected.append(order_id)
        if not selected:
            selected = [ready[0]]
        waves.append({
            "wave": len(waves) + 1,
            "work_order_ids": selected,
            "parallelism": len(selected),
        })
        completed.update(selected)
        remaining.difference_update(selected)
    order_rows = []
    required_orders: list[str] = []
    for order_id in sorted(orders):
        order = orders[order_id]
        risk = _order_risk(order)
        if risk in manifest.approval_risks:
            required_orders.append(order_id)
        order_rows.append({
            "id": order_id,
            "title": order.title,
            "risk": risk,
            "work_order_sha256": order.content_sha256,
            "allowed_paths": list(order.allowed_paths),
            "graph_node_ids": list(order.graph_node_ids),
            "depends_on": sorted(dependencies[order_id]),
        })
    required_conflicts = sorted(
        item["id"] for item in conflicts if item["severity"] in manifest.approval_risks
    )
    approval_required = bool(required_orders or required_conflicts)
    plan = {
        "schema_version": PORTFOLIO_SCHEMA_VERSION,
        "plan_type": "lightyear-modernization-portfolio-plan",
        "portfolio_id": manifest.portfolio_id,
        "title": manifest.title,
        "manifest_sha256": manifest.content_sha256,
        "graph_content_sha256": graph["content_sha256"],
        "max_parallel": manifest.max_parallel,
        "orders": order_rows,
        "conflicts": sorted(conflicts, key=lambda item: item["id"]),
        "waves": waves,
        "approval": {
            "required": approval_required,
            "required_order_ids": required_orders,
            "required_conflict_ids": required_conflicts,
            "authority": "human",
        },
        "status": "approval_required" if approval_required else "ready",
        "limitations": [
            "Portfolio scheduling proves bounded factory coordination, not z/OS equivalence.",
            "Only deterministic controllers and human approvers may authorize portfolio dispatch.",
        ],
    }
    plan["content_sha256"] = canonical_hash(plan)
    return plan, orders


def sign_portfolio_approval(
    plan: dict[str, Any],
    signing_key: bytes,
    *,
    approver_id: str,
    key_id: str,
    issued_at: datetime | None = None,
    ttl_seconds: int = 900,
) -> dict[str, Any]:
    key = _validate_key(signing_key)
    if not approver_id.strip() or not key_id.strip():
        raise ContractError("Portfolio approver and key id are required")
    if not 60 <= ttl_seconds <= 86_400:
        raise ContractError("Portfolio approval TTL must be between 60 seconds and 24 hours")
    if plan.get("content_sha256") != canonical_hash(plan, {"content_sha256"}):
        raise ContractError("Portfolio plan content hash is invalid")
    issued = (issued_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    envelope = {
        "schema_version": PORTFOLIO_SCHEMA_VERSION,
        "envelope_type": "lightyear-human-portfolio-approval",
        "approver": {"id": approver_id.strip(), "kind": "human", "role": "approver"},
        "key_id": key_id.strip(),
        "issued_at": issued.isoformat().replace("+00:00", "Z"),
        "expires_at": (issued + timedelta(seconds=ttl_seconds)).isoformat().replace(
            "+00:00", "Z"
        ),
        "nonce": secrets.token_hex(16),
        "portfolio_id": plan.get("portfolio_id"),
        "plan_sha256": plan["content_sha256"],
        "approved_order_ids": list(plan.get("approval", {}).get("required_order_ids", [])),
        "acknowledged_conflict_ids": list(
            plan.get("approval", {}).get("required_conflict_ids", [])
        ),
        "signature": {"algorithm": "HMAC-SHA256", "value": None},
    }
    unsigned = json.loads(json.dumps(envelope))
    envelope["signature"]["value"] = hmac.new(
        key, canonical_hash(unsigned).encode("ascii"), hashlib.sha256
    ).hexdigest()
    envelope["content_sha256"] = canonical_hash(envelope)
    return envelope


def verify_portfolio_approval(
    plan: dict[str, Any],
    envelope: dict[str, Any],
    trusted_keys: dict[str, bytes],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    if envelope.get("schema_version") != PORTFOLIO_SCHEMA_VERSION:
        raise ContractError("Unsupported portfolio approval schema")
    if envelope.get("envelope_type") != "lightyear-human-portfolio-approval":
        raise ContractError("Invalid portfolio approval envelope type")
    approver = envelope.get("approver", {})
    if approver.get("kind") != "human" or approver.get("role") != "approver":
        raise ContractError("Portfolio approval must be issued by a human approver")
    if envelope.get("content_sha256") != canonical_hash(envelope, {"content_sha256"}):
        raise ContractError("Portfolio approval content hash is invalid")
    if plan.get("content_sha256") != canonical_hash(plan, {"content_sha256"}):
        raise ContractError("Portfolio plan content hash is invalid")
    if envelope.get("plan_sha256") != plan["content_sha256"]:
        raise ContractError("Portfolio approval targets a different plan")
    key_id = str(envelope.get("key_id", ""))
    if key_id not in trusted_keys:
        raise ContractError("Portfolio approval key id is not trusted")
    key = _validate_key(trusted_keys[key_id])
    supplied = str(envelope.get("signature", {}).get("value", ""))
    unsigned = json.loads(json.dumps(envelope))
    unsigned.pop("content_sha256", None)
    unsigned["signature"]["value"] = None
    expected = hmac.new(
        key, canonical_hash(unsigned).encode("ascii"), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(supplied, expected):
        raise ContractError("Portfolio approval signature is invalid")
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    issued = _timestamp(str(envelope.get("issued_at", "")))
    expires = _timestamp(str(envelope.get("expires_at", "")))
    if issued > current + timedelta(minutes=5) or current >= expires:
        raise ContractError("Portfolio approval is not currently valid")
    required_orders = set(plan.get("approval", {}).get("required_order_ids", []))
    required_conflicts = set(plan.get("approval", {}).get("required_conflict_ids", []))
    if not required_orders <= set(envelope.get("approved_order_ids", [])):
        raise ContractError("Portfolio approval omits high-risk work orders")
    if not required_conflicts <= set(envelope.get("acknowledged_conflict_ids", [])):
        raise ContractError("Portfolio approval omits high-risk conflicts")
    receipt = {
        "schema_version": PORTFOLIO_SCHEMA_VERSION,
        "receipt_type": "lightyear-portfolio-admission",
        "status": "passed",
        "portfolio_id": plan["portfolio_id"],
        "plan_sha256": plan["content_sha256"],
        "approver_id": approver.get("id"),
        "approver_kind": "human",
        "key_id": key_id,
        "issued_at": envelope["issued_at"],
        "expires_at": envelope["expires_at"],
        "approved_order_ids": sorted(required_orders),
        "acknowledged_conflict_ids": sorted(required_conflicts),
        "signature_sha256": hashlib.sha256(supplied.encode("ascii")).hexdigest(),
    }
    receipt["content_sha256"] = canonical_hash(receipt)
    return receipt


class PortfolioRunner:
    """Wave-barrier executor. It cannot approve plans or resolve conflicts."""

    def __init__(
        self,
        execute_cell: Callable[[WorkOrder, str], dict[str, Any]],
    ) -> None:
        self.execute_cell = execute_cell

    def run(
        self,
        plan: dict[str, Any],
        orders: dict[str, WorkOrder],
        output_root: Path,
        admission: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if plan.get("approval", {}).get("required"):
            if not admission or admission.get("status") != "passed":
                raise ContractError("Human-approved portfolio admission is required")
            if admission.get("plan_sha256") != plan.get("content_sha256"):
                raise ContractError("Portfolio admission targets a different plan")
        output_root.mkdir(parents=True, exist_ok=True)
        started = datetime.now(timezone.utc)
        cell_receipts: list[dict[str, Any]] = []
        blocked = False
        for wave in plan.get("waves", []):
            if blocked:
                break
            ids = list(wave["work_order_ids"])
            with ThreadPoolExecutor(max_workers=max(1, len(ids))) as executor:
                futures = {
                    executor.submit(
                        self.execute_cell,
                        orders[order_id],
                        f"portfolio-{plan['portfolio_id'].split(':')[-1]}-w{wave['wave']}-{index + 1}",
                    ): order_id
                    for index, order_id in enumerate(ids)
                }
                rows = []
                for future in as_completed(futures):
                    order_id = futures[future]
                    try:
                        receipt = future.result()
                        rows.append({
                            "work_order_id": order_id,
                            "status": receipt.get("status", "blocked"),
                            "run_id": receipt.get("run_id"),
                            "receipt_sha256": receipt.get("content_sha256"),
                        })
                    except Exception as exc:  # fail-closed controller boundary
                        rows.append({
                            "work_order_id": order_id,
                            "status": "blocked",
                            "error_type": type(exc).__name__,
                        })
                rows.sort(key=lambda item: item["work_order_id"])
                blocked = any(item["status"] != "passed" for item in rows)
                cell_receipts.extend({"wave": wave["wave"], **item} for item in rows)
        receipt = {
            "schema_version": PORTFOLIO_SCHEMA_VERSION,
            "receipt_type": "lightyear-modernization-portfolio-run",
            "portfolio_id": plan["portfolio_id"],
            "plan_sha256": plan["content_sha256"],
            "admission_sha256": admission.get("content_sha256") if admission else None,
            "started_at": started.isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "status": "blocked" if blocked or len(cell_receipts) != len(orders) else "passed",
            "waves_completed": len({item["wave"] for item in cell_receipts}),
            "cells": cell_receipts,
            "limitations": ["Cell acceptance does not substitute for live z/OS equivalence."],
        }
        receipt["content_sha256"] = canonical_hash(receipt)
        write_json(receipt, output_root / "receipt.json")
        return receipt
