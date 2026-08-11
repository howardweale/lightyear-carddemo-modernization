from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .contracts import ContractError, WorkOrder


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

    def diagnose(
        self, order: WorkOrder, verification: dict[str, Any], attempt: int
    ) -> dict[str, Any]: ...


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

    def diagnose(
        self, order: WorkOrder, verification: dict[str, Any], attempt: int
    ) -> dict[str, Any]:
        failed = [item["id"] for item in verification.get("gates", []) if item["status"] != "passed"]
        return {
            "summary": f"Deterministic gates rejected attempt {attempt}.",
            "failure_codes": [f"GATE_FAILED:{item}" for item in failed],
            "builder_guidance": "Inspect only the approved files and restore source-faithful behavior.",
            "risk": "medium",
        }


class OpenAIAgentSet:
    """Responses API adapter with strict structured artifacts for all three roles."""

    name = "openai"

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-5.6",
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        if not api_key:
            raise ContractError("OPENAI_API_KEY is required for the OpenAI factory provider")
        self.api_key = api_key
        self.model = model
        self.opener = opener

    @classmethod
    def from_environment(cls) -> "OpenAIAgentSet":
        return cls(
            os.environ.get("OPENAI_API_KEY", ""),
            os.environ.get("LIGHTYEAR_FACTORY_MODEL", "gpt-5.6"),
        )

    def plan(self, order: WorkOrder, context: dict[str, Any]) -> dict[str, Any]:
        return self._call(
            "planner",
            "Decompose the approved work order. Do not propose paths outside allowed_paths.",
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
                files[relative] = path.read_text(encoding="utf-8", errors="replace")[:200_000]
        return self._call(
            "builder",
            "Return exact bounded find/replace edits. Never claim verification or request holdout data.",
            {
                "work_order": order.to_dict(),
                "plan": plan,
                "public_failure": failure,
                "attempt": attempt,
                "allowed_files": files,
            },
            BUILDER_SCHEMA,
        )

    def diagnose(
        self, order: WorkOrder, verification: dict[str, Any], attempt: int
    ) -> dict[str, Any]:
        return self._call(
            "verifier",
            "Classify failure without revealing holdout inputs or expected outputs in builder_guidance.",
            {"work_order": order.to_dict(), "verification": verification, "attempt": attempt},
            VERIFIER_SCHEMA,
        )

    def _call(
        self,
        role: str,
        instruction: str,
        payload: dict[str, Any],
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        body = {
            "model": self.model,
            "store": False,
            "instructions": (
                f"You are the LIGHTYEAR {role} agent. Communicate only through the required JSON artifact. "
                f"{instruction} The deterministic harness, never you, decides acceptance."
            ),
            "input": json.dumps(payload, sort_keys=True),
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": f"lightyear_{role}_artifact",
                    "schema": schema,
                    "strict": True,
                }
            },
        }
        request = Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(body).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self.opener(request, timeout=180) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise ContractError(f"OpenAI {role} request failed with HTTP {exc.code}") from exc
        except (URLError, TimeoutError) as exc:
            raise ContractError(f"OpenAI {role} request failed: {exc.reason if hasattr(exc, 'reason') else exc}") from exc
        for output in response_payload.get("output", []):
            for content in output.get("content", []):
                if content.get("type") == "output_text":
                    return json.loads(content["text"])
        raise ContractError(f"OpenAI {role} response did not contain structured output")

