from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

from .context import GraphContextAssembler
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
                    "evidence_capsule_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": [
                    "id", "objective", "paths", "graph_node_ids", "evidence_capsule_ids"
                ],
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
    RepairRule(
        "factory/benchmarks/posttran_candidate.py",
        'POSTTRAN_PROGRAM = "CBTRN02X"',
        'POSTTRAN_PROGRAM = "CBTRN02C"',
        "Restore the POSTTRAN program binding.",
    ),
    RepairRule(
        "factory/benchmarks/posttran_candidate.py",
        "TRANSACTION_RECORD_LENGTH = 300",
        "TRANSACTION_RECORD_LENGTH = 350",
        "Restore the POSTTRAN transaction record layout.",
    ),
    RepairRule(
        "factory/benchmarks/posttran_candidate.py",
        "CATEGORY_BALANCE_LENGTH = 49",
        "CATEGORY_BALANCE_LENGTH = 50",
        "Restore the POSTTRAN category-balance layout.",
    ),
    RepairRule(
        "factory/benchmarks/posttran_candidate.py",
        'APPROVED_STATUS = "01"',
        'APPROVED_STATUS = "00"',
        "Restore the approved transaction status.",
    ),
    RepairRule(
        "factory/benchmarks/posttran_candidate.py",
        'transaction_type == "02"',
        'transaction_type == "01"',
        "Restore debit and reversal direction.",
    ),
    RepairRule(
        "factory/benchmarks/posttran_candidate.py",
        "Decimal(amount) < 0",
        "Decimal(amount) <= 0",
        "Restore zero-amount rejection.",
    ),
    RepairRule(
        "factory/benchmarks/statement_candidate.py",
        'STATEMENT_PROGRAM = "CBSTM03X"',
        'STATEMENT_PROGRAM = "CBSTM03A"',
        "Restore the CREASTMT program binding.",
    ),
    RepairRule(
        "factory/benchmarks/statement_candidate.py",
        "STATEMENT_RECORD_LENGTH = 79",
        "STATEMENT_RECORD_LENGTH = 80",
        "Restore the statement record layout.",
    ),
    RepairRule(
        "factory/benchmarks/statement_candidate.py",
        "HTML_OUTPUT_ENABLED = False",
        "HTML_OUTPUT_ENABLED = True",
        "Restore HTML statement generation.",
    ),
    RepairRule(
        "factory/benchmarks/statement_candidate.py",
        "SORT_BEFORE_RENDER = False",
        "SORT_BEFORE_RENDER = True",
        "Restore deterministic pre-render ordering.",
    ),
    RepairRule(
        "factory/benchmarks/statement_candidate.py",
        "return account_found or customer_found",
        "return account_found and customer_found",
        "Restore the dual-record render predicate.",
    ),
    RepairRule(
        "factory/benchmarks/pli_authorization_candidate.py",
        '"fraud_score": "10.00"',
        '"fraud_score": "100.00"',
        "Restore the ACCTPL1 fraud score.",
    ),
    RepairRule(
        "factory/benchmarks/pli_authorization_candidate.py",
        '"divisor": "10"',
        '"divisor": "100"',
        "Restore PL/I-compatible risk scaling.",
    ),
    RepairRule(
        "factory/benchmarks/pli_authorization_candidate.py",
        '"overwrite_db_fields": False',
        '"overwrite_db_fields": True',
        "Restore the Db2 result assignment boundary.",
    ),
    RepairRule(
        "factory/benchmarks/pli_authorization_candidate.py",
        '"cobol_program": "CBACT04X"',
        '"cobol_program": "CBACT04C"',
        "Restore the OPTIONS(COBOL) target.",
    ),
    RepairRule(
        "factory/benchmarks/pli_authorization_candidate.py",
        '"parm_length": 8',
        '"parm_length": 10',
        "Restore the mixed-language parameter length.",
    ),
    RepairRule(
        "factory/benchmarks/pli_authorization_candidate.py",
        '"call_on_error": True',
        '"call_on_error": False',
        "Restore the error-path COBOL call boundary.",
    ),
    RepairRule(
        "factory/benchmarks/pli_authorization_candidate.py",
        '"write_on_error": True',
        '"write_on_error": False',
        "Restore the error-path output boundary.",
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
                    "evidence_capsule_ids": [
                        item["capsule_id"]
                        for item in context.get("source_excerpts", [])[:8]
                    ],
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
        self.context_projections: dict[str, dict[str, Any]] = {}

    def plan(self, order: WorkOrder, context: dict[str, Any]) -> dict[str, Any]:
        self.implementer_context = context
        planner_context = GraphContextAssembler.planner_context(context)
        planner_limit = min(order.max_context_bytes, 80_000)
        if planner_context["statistics"]["context_bytes"] > planner_limit:
            raise ContractError("Planner evidence catalog exceeded its role context budget")
        self.context_projections["planner"] = planner_context["statistics"]
        return self._call(
            order,
            "planner",
            "Use the supplied graph relationships and evidence catalog to decompose the work "
            "order. Every task must cite graph_node_ids and select only evidence_capsule_ids "
            "listed in the catalog for later builder retrieval. Do not propose paths outside "
            "allowed_paths and state uncertainty as risk.",
            {"work_order": order.to_dict(), "planner_context": planner_context},
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
        evidence_capsule_ids = list(
            dict.fromkeys(
                str(item)
                for task in plan.get("tasks", [])
                for item in task.get("evidence_capsule_ids", [])
            )
        )
        graph_node_ids = list(
            dict.fromkeys(
                str(item)
                for task in plan.get("tasks", [])
                for item in task.get("graph_node_ids", [])
            )
        )
        full_context = self.implementer_context or {}
        if full_context.get("source_excerpts") and not evidence_capsule_ids:
            raise ContractError("Planner did not select source evidence for the builder")
        builder_context = GraphContextAssembler.builder_context(
            full_context, evidence_capsule_ids, graph_node_ids
        )
        builder_limit = min(order.max_context_bytes, 80_000)
        if builder_context["statistics"]["context_bytes"] > builder_limit:
            raise ContractError("Builder selected evidence exceeded its role context budget")
        self.context_projections["builder"] = builder_context["statistics"]
        return self._call(
            order,
            "builder",
            "Return exact bounded find/replace edits supported by the plan and public failure "
            "envelope. Never claim verification, request holdout data, or modify unapproved paths.",
            {
                "work_order": order.to_dict(),
                "plan": plan,
                "graph_context": builder_context,
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
                "provider_attempts": 0,
                "provider_retries": 0,
                "input_bytes": 0,
                "output_bytes": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "estimated_cost_usd": 0.0,
                "cost_estimate_available": False,
                "call_evidence_sha256": [],
            }
            payload["context_projections"] = self.context_projections
            payload["content_sha256"] = canonical_hash(payload)
            return payload
        payload = self.bounded_provider.summary()
        payload["context_projections"] = self.context_projections
        payload["content_sha256"] = canonical_hash(payload, {"content_sha256"})
        return payload


class OpenAIAgentSet(ModelAgentSet):
    """Compatibility constructor for the OpenAI Responses provider."""

    name = "openai-responses"

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-5.6-terra",
        opener: Callable[..., Any] | None = None,
        token_preflight: bool | None = None,
    ) -> None:
        kwargs: dict[str, Any] = {}
        if opener is not None:
            kwargs["opener"] = opener
        if token_preflight is None:
            token_preflight = opener is None and os.environ.get(
                "LIGHTYEAR_MODEL_TOKEN_PREFLIGHT", "true"
            ).casefold() not in {"0", "false", "no", "off"}
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
                max_output_tokens=int(
                    os.environ.get("LIGHTYEAR_MODEL_MAX_OUTPUT_TOKENS", "25000")
                ),
                max_retries=int(os.environ.get("LIGHTYEAR_MODEL_MAX_RETRIES", "4")),
                request_timeout_seconds=int(
                    os.environ.get("LIGHTYEAR_MODEL_TIMEOUT_SECONDS", "240")
                ),
                token_preflight=token_preflight,
                max_input_tokens_per_call=int(
                    os.environ.get(
                        "LIGHTYEAR_MODEL_MAX_INPUT_TOKENS_PER_CALL", "60000"
                    )
                ),
                **kwargs,
            )
        )

    @classmethod
    def from_environment(cls) -> "OpenAIAgentSet":
        return cls(
            os.environ.get("OPENAI_API_KEY", ""),
            os.environ.get("LIGHTYEAR_FACTORY_MODEL", "gpt-5.6-terra"),
        )
