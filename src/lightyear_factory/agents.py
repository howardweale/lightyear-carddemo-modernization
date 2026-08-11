from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

from .contracts import ContractError, WorkOrder, canonical_hash
from .providers import BoundedModelProvider, ModelProvider, OpenAIResponsesProvider


PLANNER_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "tasks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "objective": {"type": "string"},
                    "paths": {"type": "array", "items": {"type": "string"}},
                    "graph_node_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["id", "objective", "paths", "graph_node_ids"],
                "additionalProperties": False,
            },
        },
        "risks": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "tasks", "risks"],
    "additionalProperties": False,
}

BUILDER_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "edits": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "find": {"type": "string"},
                    "replace": {"type": "string"},
                    "rationale": {"type": "string"},
                },
                "required": ["path", "find", "replace", "rationale"],
                "additionalProperties": False,
            },
        },
        "blocked_reason": {"type": ["string", "null"]},
    },
    "required": ["summary", "edits", "blocked_reason"],
    "additionalProperties": False,
}

VERIFIER_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "failure_codes": {"type": "array", "items": {"type": "string"}},
        "builder_guidance": {"type": "string"},
        "risk": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": ["summary", "failure_codes", "builder_guidance", "risk"],
    "additionalProperties": False,
}


class AgentSet(Protocol):
    name: str

    def plan(self, order: WorkOrder, context: dict[str, Any]) -> dict[str, Any]: ...

    def build(
        self,
        order: WorkOrder,
        plan: dict[str, Any],
        failure: dict[str, Any],
        workspace_root: Path,
        attempt: int,
    ) -> dict[str, Any]: ...

    def analyze_failure(
        self, order: WorkOrder, verification: dict[str, Any], attempt: int
    ) -> dict[str, Any]: ...

    def drain_evidence(self) -> list[dict[str, Any]]: ...

    def intelligence_summary(self) -> dict[str, Any]: ...


@dataclass(frozen=True)
class RepairRule:
    path: str
    broken: str
    corrected: str
    rationale: str


DEFAULT_REPAIR_RULES = (
    RepairRule(
        "factory/benchmarks/intcalc_candidate.py",
        'ROUNDING = "half-up"',
        'ROUNDING = "down"',
        "Restore COBOL-compatible truncation toward zero.",
    ),
    RepairRule(
        "factory/benchmarks/intcalc_candidate.py",
        "MONTHS_PERCENT = 100",
        "MONTHS_PERCENT = 1200",
        "Restore annual percentage to monthly-rate conversion.",
    ),
    RepairRule(
        "factory/benchmarks/intcalc_candidate.py",
        'DEFAULT_GROUP = "STANDARD"',
        'DEFAULT_GROUP = "DEFAULT"',
        "Restore the default disclosure-group fallback.",
    ),
    RepairRule(
        "factory/benchmarks/intcalc_candidate.py",
        "SKIP_ZERO_RATE = False",
        "SKIP_ZERO_RATE = True",
        "Restore the zero-rate no-transaction rule.",
    ),
    RepairRule(
        "factory/benchmarks/intcalc_candidate.py",
        "PRESERVE_FINAL_ACCOUNT = False",
        "PRESERVE_FINAL_ACCOUNT = True",
        "Restore the source-faithful final-account boundary behavior.",
    ),
)


class LocalAgentSet:
    """Deterministic reference workers for the offline factory benchmark."""

    name = "local-reference"

    def __init__(self, repair_rules: tuple[RepairRule, ...] = DEFAULT_REPAIR_RULES) -> None:
        self.repair_rules = repair_rules

    def plan(self, order: WorkOrder, context: dict[str, Any]) -> dict[str, Any]:
        return {
            "summary": f"Bound {order.title} to {len(order.allowed_paths)} writable path(s).",
            "tasks": [
                {
                    "id": "repair-and-prove",
                    "objective": order.goal,
                    "paths": list(order.allowed_paths),
                    "graph_node_ids": list(order.graph_node_ids),
                }
            ],
            "risks": [
                "Local reference workers cover the mutation benchmark, not arbitrary modernization.",
                *context.get("limitations", []),
            ],
        }

    def build(
        self,
        order: WorkOrder,
        plan: dict[str, Any],
        failure: dict[str, Any],
        workspace_root: Path,
        attempt: int,
    ) -> dict[str, Any]:
        edits = []
        for rule in self.repair_rules:
            if rule.path not in order.allowed_paths:
                continue
            path = workspace_root / rule.path
            if path.is_file() and rule.broken in path.read_text(encoding="utf-8"):
                edits.append(
                    {
                        "path": rule.path,
                        "find": rule.broken,
                        "replace": rule.corrected,
                        "rationale": rule.rationale,
                    }
                )
        return {
            "summary": f"Reference builder proposed {len(edits)} bounded repair(s) on attempt {attempt}.",
            "edits": edits,
            "blocked_reason": None if edits else "No recognized safe repair is available.",
        }

    def analyze_failure(
        self, order: WorkOrder, verification: dict[str, Any], attempt: int
    ) -> dict[str, Any]:
        failed = [item["id"] for item in verification.get("gates", []) if item["status"] != "passed"]
        return {
            "summary": f"Deterministic gates rejected attempt {attempt}.",
            "failure_codes": [f"GATE_FAILED:{item}" for item in failed],
            "builder_guidance": "Inspect only the approved files and restore source-faithful behavior.",
            "risk": "medium",
        }

    def drain_evidence(self) -> list[dict[str, Any]]:
        return []

    def intelligence_summary(self) -> dict[str, Any]:
        payload = {
            "mode": "deterministic-reference",
            "provider": self.name,
            "model": None,
            "calls": 0,
            "input_bytes": 0,
            "output_bytes": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "estimated_cost_usd": 0.0,
            "cost_estimate_available": True,
            "limitations": [
                "Reference rules prove factory mechanics, not model generalization."
            ],
        }
        payload["content_sha256"] = canonical_hash(payload)
        return payload


class ModelAgentSet:
    """Graph-grounded roles backed by a budgeted, replaceable model provider."""

    name = "model-backed"

    def __init__(self, provider: ModelProvider) -> None:
        self.provider = provider
        self.bounded_provider: BoundedModelProvider | None = None
        self.order_sha256: str | None = None
        self.pending_evidence: list[dict[str, Any]] = []
        self.implementer_context: dict[str, Any] | None = None

    def plan(self, order: WorkOrder, context: dict[str, Any]) -> dict[str, Any]:
        self.implementer_context = context
        return self._call(
            order,
            "planner",
            "Use the supplied graph relationships, evidence excerpts, and approved files to "
            "decompose the work order. Cite graph node IDs in tasks. Do not propose paths outside "
            "allowed_paths and state uncertainty as risk.",
            {"work_order": order.to_dict(), "implementer_context": context},
            PLANNER_SCHEMA,
        )

    def build(
        self,
        order: WorkOrder,
        plan: dict[str, Any],
        failure: dict[str, Any],
        workspace_root: Path,
        attempt: int,
    ) -> dict[str, Any]:
        files = {}
        for relative in order.allowed_paths:
            path = workspace_root / relative
            if path.is_file():
                raw = path.read_bytes()
                files[relative] = {
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "content": raw[: order.max_file_bytes].decode("utf-8", errors="replace"),
                    "truncated": len(raw) > order.max_file_bytes,
                }
        return self._call(
            order,
            "builder",
            "Return exact bounded find/replace edits supported by the plan and public failure "
            "envelope. Never claim verification, request holdout data, or modify unapproved paths.",
            {
                "work_order": order.to_dict(),
                "plan": plan,
                "graph_context": {
                    key: value
                    for key, value in (self.implementer_context or {}).items()
                    if key != "allowed_files"
                },
                "public_failure": failure,
                "attempt": attempt,
                "allowed_files": files,
            },
            BUILDER_SCHEMA,
        )

    def analyze_failure(
        self, order: WorkOrder, verification: dict[str, Any], attempt: int
    ) -> dict[str, Any]:
        return self._call(
            order,
            "failure_analyst",
            "Classify only the sanitized gate metadata supplied by the controller. Give bounded "
            "engineering guidance without inventing private inputs, outputs, or expected values.",
            {"work_order": order.to_dict(), "public_verification": verification, "attempt": attempt},
            VERIFIER_SCHEMA,
        )

    def _call(
        self,
        order: WorkOrder,
        role: str,
        instruction: str,
        payload: dict[str, Any],
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        bounded = self._provider_for(order)
        result = bounded.complete(role, instruction, payload, schema)
        self.pending_evidence.append(result.evidence)
        return result.content

    def _provider_for(self, order: WorkOrder) -> BoundedModelProvider:
        if self.bounded_provider is None:
            self.bounded_provider = BoundedModelProvider(self.provider, order)
            self.order_sha256 = order.content_sha256
        elif self.order_sha256 != order.content_sha256:
            raise ContractError("A model agent set cannot span different work orders")
        return self.bounded_provider

    def drain_evidence(self) -> list[dict[str, Any]]:
        evidence = list(self.pending_evidence)
        self.pending_evidence.clear()
        return evidence

    def intelligence_summary(self) -> dict[str, Any]:
        if self.bounded_provider is None:
            payload = {
                "mode": "model-backed",
                "provider": self.provider.provider_id,
                "model": self.provider.model,
                "calls": 0,
                "input_bytes": 0,
                "output_bytes": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "estimated_cost_usd": 0.0,
                "cost_estimate_available": False,
                "call_evidence_sha256": [],
            }
            payload["content_sha256"] = canonical_hash(payload)
            return payload
        return self.bounded_provider.summary()


class OpenAIAgentSet(ModelAgentSet):
    """Compatibility constructor for the OpenAI Responses provider."""

    name = "openai-responses"

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-5.6",
        opener: Callable[..., Any] | None = None,
    ) -> None:
        kwargs: dict[str, Any] = {}
        if opener is not None:
            kwargs["opener"] = opener
        super().__init__(
            OpenAIResponsesProvider(
                api_key,
                model,
                input_usd_per_million=float(
                    os.environ.get("LIGHTYEAR_MODEL_INPUT_USD_PER_MILLION", "0")
                ),
                output_usd_per_million=float(
                    os.environ.get("LIGHTYEAR_MODEL_OUTPUT_USD_PER_MILLION", "0")
                ),
                **kwargs,
            )
        )

    @classmethod
    def from_environment(cls) -> "OpenAIAgentSet":
        return cls(
            os.environ.get("OPENAI_API_KEY", ""),
            os.environ.get("LIGHTYEAR_FACTORY_MODEL", "gpt-5.6"),
        )
