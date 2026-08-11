from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any


WORK_ORDER_SCHEMA_VERSION = "1.0"
RUN_RECEIPT_SCHEMA_VERSION = "1.0"
ARTIFACT_SCHEMA_VERSION = "1.0"
ALLOWED_AUDIENCES = {"implementer", "verifier"}


class ContractError(ValueError):
    """A versioned factory contract is invalid or unsafe."""


def canonical_hash(payload: dict[str, Any], excluded: set[str] | None = None) -> str:
    content = {
        key: value for key, value in payload.items() if key not in (excluded or set())
    }
    encoded = json.dumps(content, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def safe_relative_path(value: str) -> str:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise ContractError(f"Unsafe project-relative path: {value!r}")
    return path.as_posix()


@dataclass(frozen=True)
class GateContract:
    gate_id: str
    command: tuple[str, ...]
    timeout_seconds: int
    expose_output_to_builder: bool = False

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "GateContract":
        gate_id = str(payload.get("id", "")).strip()
        command = payload.get("command")
        if not gate_id or not isinstance(command, list) or not command:
            raise ContractError("Every gate requires an id and non-empty command array")
        if not all(isinstance(item, str) and item for item in command):
            raise ContractError(f"Gate {gate_id} command contains an invalid argument")
        if any("\x00" in item for item in command):
            raise ContractError(f"Gate {gate_id} command contains a null byte")
        timeout = int(payload.get("timeout_seconds", 300))
        if not 1 <= timeout <= 3600:
            raise ContractError(f"Gate {gate_id} timeout must be between 1 and 3600 seconds")
        return cls(
            gate_id=gate_id,
            command=tuple(command),
            timeout_seconds=timeout,
            expose_output_to_builder=bool(payload.get("expose_output_to_builder", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.gate_id,
            "command": list(self.command),
            "timeout_seconds": self.timeout_seconds,
            "expose_output_to_builder": self.expose_output_to_builder,
        }


@dataclass(frozen=True)
class WorkOrder:
    order_id: str
    title: str
    goal: str
    non_goals: tuple[str, ...]
    allowed_paths: tuple[str, ...]
    graph_node_ids: tuple[str, ...]
    gates: tuple[GateContract, ...]
    audience: str
    max_attempts: int
    max_files_changed: int
    max_patch_bytes: int
    max_changed_lines: int
    max_context_bytes: int
    max_file_bytes: int
    max_model_calls: int
    max_model_input_bytes: int
    max_model_output_bytes: int
    max_model_tokens: int
    max_model_cost_usd: float
    max_elapsed_seconds: int
    baseline_first: bool
    allow_network: bool
    metadata: dict[str, Any]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "WorkOrder":
        if payload.get("schema_version") != WORK_ORDER_SCHEMA_VERSION:
            raise ContractError(
                f"Unsupported work-order schema: {payload.get('schema_version')}"
            )
        order_id = str(payload.get("id", "")).strip()
        title = str(payload.get("title", "")).strip()
        goal = str(payload.get("goal", "")).strip()
        if not order_id or not title or not goal:
            raise ContractError("Work order id, title, and goal are required")
        scope = payload.get("scope", {})
        policy = payload.get("policy", {})
        acceptance = payload.get("acceptance", {})
        allowed_paths = tuple(
            safe_relative_path(str(item)) for item in scope.get("allowed_paths", [])
        )
        if not allowed_paths:
            raise ContractError("At least one allowed project path is required")
        graph_node_ids = tuple(str(item) for item in scope.get("graph_node_ids", []))
        gates = tuple(GateContract.from_dict(item) for item in acceptance.get("gates", []))
        if not gates:
            raise ContractError("At least one deterministic acceptance gate is required")
        if len({gate.gate_id for gate in gates}) != len(gates):
            raise ContractError("Acceptance gate ids must be unique")
        audience = str(policy.get("audience", "implementer"))
        if audience not in ALLOWED_AUDIENCES:
            raise ContractError("policy.audience must be implementer or verifier")
        if audience != "implementer":
            raise ContractError("Builder-facing work orders must use the implementer audience")
        max_attempts = int(acceptance.get("max_attempts", 3))
        max_files_changed = int(policy.get("max_files_changed", 12))
        max_patch_bytes = int(policy.get("max_patch_bytes", 250_000))
        max_changed_lines = int(policy.get("max_changed_lines", 2_000))
        max_context_bytes = int(policy.get("max_context_bytes", 160_000))
        max_file_bytes = int(policy.get("max_file_bytes", 250_000))
        max_model_calls = int(policy.get("max_model_calls", 12))
        max_model_input_bytes = int(policy.get("max_model_input_bytes", 2_000_000))
        max_model_output_bytes = int(policy.get("max_model_output_bytes", 500_000))
        max_model_tokens = int(policy.get("max_model_tokens", 250_000))
        max_model_cost_usd = float(policy.get("max_model_cost_usd", 25.0))
        max_elapsed_seconds = int(policy.get("max_elapsed_seconds", 1_800))
        if not 1 <= max_attempts <= 10:
            raise ContractError("max_attempts must be between 1 and 10")
        if not 1 <= max_files_changed <= 100:
            raise ContractError("max_files_changed must be between 1 and 100")
        if not 1 <= max_patch_bytes <= 5_000_000:
            raise ContractError("max_patch_bytes must be between 1 and 5,000,000")
        if not 1 <= max_changed_lines <= 100_000:
            raise ContractError("max_changed_lines must be between 1 and 100,000")
        if not 1_000 <= max_context_bytes <= 5_000_000:
            raise ContractError("max_context_bytes must be between 1,000 and 5,000,000")
        if not 1_000 <= max_file_bytes <= 5_000_000:
            raise ContractError("max_file_bytes must be between 1,000 and 5,000,000")
        if not 1 <= max_model_calls <= 100:
            raise ContractError("max_model_calls must be between 1 and 100")
        if not 1_000 <= max_model_input_bytes <= 100_000_000:
            raise ContractError("max_model_input_bytes must be between 1,000 and 100,000,000")
        if not 1_000 <= max_model_output_bytes <= 10_000_000:
            raise ContractError("max_model_output_bytes must be between 1,000 and 10,000,000")
        if not 1_000 <= max_model_tokens <= 10_000_000:
            raise ContractError("max_model_tokens must be between 1,000 and 10,000,000")
        if not 0 <= max_model_cost_usd <= 10_000:
            raise ContractError("max_model_cost_usd must be between 0 and 10,000")
        if not 30 <= max_elapsed_seconds <= 86_400:
            raise ContractError("max_elapsed_seconds must be between 30 and 86,400")
        non_goals = payload.get("non_goals", [])
        if not isinstance(non_goals, list) or not all(isinstance(item, str) for item in non_goals):
            raise ContractError("non_goals must be an array of strings")
        metadata = payload.get("metadata", {})
        if not isinstance(metadata, dict):
            raise ContractError("metadata must be an object")
        return cls(
            order_id=order_id,
            title=title,
            goal=goal,
            non_goals=tuple(non_goals),
            allowed_paths=allowed_paths,
            graph_node_ids=graph_node_ids,
            gates=gates,
            audience=audience,
            max_attempts=max_attempts,
            max_files_changed=max_files_changed,
            max_patch_bytes=max_patch_bytes,
            max_changed_lines=max_changed_lines,
            max_context_bytes=max_context_bytes,
            max_file_bytes=max_file_bytes,
            max_model_calls=max_model_calls,
            max_model_input_bytes=max_model_input_bytes,
            max_model_output_bytes=max_model_output_bytes,
            max_model_tokens=max_model_tokens,
            max_model_cost_usd=max_model_cost_usd,
            max_elapsed_seconds=max_elapsed_seconds,
            baseline_first=bool(acceptance.get("baseline_first", True)),
            allow_network=bool(policy.get("allow_network", False)),
            metadata=metadata,
        )

    @classmethod
    def load(cls, path: Path) -> "WorkOrder":
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": WORK_ORDER_SCHEMA_VERSION,
            "id": self.order_id,
            "title": self.title,
            "goal": self.goal,
            "non_goals": list(self.non_goals),
            "scope": {
                "allowed_paths": list(self.allowed_paths),
                "graph_node_ids": list(self.graph_node_ids),
            },
            "acceptance": {
                "baseline_first": self.baseline_first,
                "max_attempts": self.max_attempts,
                "gates": [gate.to_dict() for gate in self.gates],
            },
            "policy": {
                "audience": self.audience,
                "allow_network": self.allow_network,
                "max_files_changed": self.max_files_changed,
                "max_patch_bytes": self.max_patch_bytes,
                "max_changed_lines": self.max_changed_lines,
                "max_context_bytes": self.max_context_bytes,
                "max_file_bytes": self.max_file_bytes,
                "max_model_calls": self.max_model_calls,
                "max_model_input_bytes": self.max_model_input_bytes,
                "max_model_output_bytes": self.max_model_output_bytes,
                "max_model_tokens": self.max_model_tokens,
                "max_model_cost_usd": self.max_model_cost_usd,
                "max_elapsed_seconds": self.max_elapsed_seconds,
            },
            "metadata": self.metadata,
        }

    @property
    def content_sha256(self) -> str:
        return canonical_hash(self.to_dict())


def write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
