from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .contracts import ContractError, canonical_hash, write_json
from .workloads import WORKLOAD_PROFILES


QUALIFICATION_VERSION = "1.0"


@dataclass(frozen=True)
class QualificationPolicy:
    minimum_runs_per_workload: int
    minimum_repair_rate: float
    minimum_correct_no_change_rate: float
    minimum_first_attempt_repair_rate: float
    maximum_false_acceptances: int
    maximum_false_rejections: int
    maximum_average_latency_ms: int
    maximum_average_input_tokens: int
    maximum_total_cost_usd: float

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "QualificationPolicy":
        policy = cls(
            minimum_runs_per_workload=int(payload.get("minimum_runs_per_workload", 2)),
            minimum_repair_rate=float(payload.get("minimum_repair_rate", 0.8)),
            minimum_correct_no_change_rate=float(
                payload.get("minimum_correct_no_change_rate", 0.95)
            ),
            minimum_first_attempt_repair_rate=float(
                payload.get("minimum_first_attempt_repair_rate", 0.6)
            ),
            maximum_false_acceptances=int(payload.get("maximum_false_acceptances", 0)),
            maximum_false_rejections=int(payload.get("maximum_false_rejections", 0)),
            maximum_average_latency_ms=int(
                payload.get("maximum_average_latency_ms", 900_000)
            ),
            maximum_average_input_tokens=int(
                payload.get("maximum_average_input_tokens", 75_000)
            ),
            maximum_total_cost_usd=float(payload.get("maximum_total_cost_usd", 120.0)),
        )
        if policy.minimum_runs_per_workload < 2:
            raise ContractError("Qualification requires at least two runs per workload")
        for value in (
            policy.minimum_repair_rate,
            policy.minimum_correct_no_change_rate,
            policy.minimum_first_attempt_repair_rate,
        ):
            if not 0 <= value <= 1:
                raise ContractError("Qualification rates must be between zero and one")
        if policy.maximum_false_acceptances != 0:
            raise ContractError("Critical false acceptance tolerance must remain zero")
        if min(
            policy.maximum_false_rejections,
            policy.maximum_average_latency_ms,
            policy.maximum_average_input_tokens,
        ) < 0 or policy.maximum_total_cost_usd <= 0:
            raise ContractError("Qualification limits are invalid")
        return policy

    def to_dict(self) -> dict[str, Any]:
        return {
            "minimum_runs_per_workload": self.minimum_runs_per_workload,
            "minimum_repair_rate": self.minimum_repair_rate,
            "minimum_correct_no_change_rate": self.minimum_correct_no_change_rate,
            "minimum_first_attempt_repair_rate": self.minimum_first_attempt_repair_rate,
            "maximum_false_acceptances": self.maximum_false_acceptances,
            "maximum_false_rejections": self.maximum_false_rejections,
            "maximum_average_latency_ms": self.maximum_average_latency_ms,
            "maximum_average_input_tokens": self.maximum_average_input_tokens,
            "maximum_total_cost_usd": self.maximum_total_cost_usd,
        }


@dataclass(frozen=True)
class QualificationManifest:
    qualification_id: str
    required_workloads: tuple[str, ...]
    policy: QualificationPolicy

    @classmethod
    def load(cls, path: Path) -> "QualificationManifest":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != QUALIFICATION_VERSION:
            raise ContractError("Unsupported qualification manifest schema")
        qualification_id = str(payload.get("id", "")).strip()
        workloads = tuple(str(item).strip().upper() for item in payload.get("workloads", []))
        if not qualification_id or set(workloads) != set(WORKLOAD_PROFILES):
            raise ContractError("Qualification manifest must contain all four trusted workloads")
        if len(workloads) != len(set(workloads)):
            raise ContractError("Qualification workloads must be unique")
        return cls(
            qualification_id,
            workloads,
            QualificationPolicy.from_dict(payload.get("policy", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": QUALIFICATION_VERSION,
            "id": self.qualification_id,
            "workloads": list(self.required_workloads),
            "policy": self.policy.to_dict(),
        }

    @property
    def content_sha256(self) -> str:
        return canonical_hash(self.to_dict())


def _valid_hash(payload: dict[str, Any], label: str) -> None:
    if payload.get("content_sha256") != canonical_hash(payload, {"content_sha256"}):
        raise ContractError(f"{label} content hash is invalid")


def _run_provenance(evaluation_root: Path, evaluation: dict[str, Any]) -> dict[str, Any]:
    results = evaluation.get("results", [])
    expected = {str(item.get("receipt_sha256")) for item in results}
    if len(expected) != len(results):
        raise ContractError("Evaluation results must resolve to unique factory receipts")
    result_by_receipt = {str(item.get("receipt_sha256")): item for item in results}
    seen: set[str] = set()
    call_hashes: list[str] = []
    providers: set[str] = set()
    models: set[str] = set()
    elapsed_ms = 0
    retries = 0
    for path in sorted((evaluation_root / "runs").glob("*/receipt.json")):
        receipt = json.loads(path.read_text(encoding="utf-8"))
        _valid_hash(receipt, "Factory run receipt")
        if receipt["content_sha256"] not in expected:
            continue
        if receipt.get("schema_version") != "1.0" or receipt.get(
            "receipt_type"
        ) != "lightyear-autonomous-factory-run":
            raise ContractError("Unsupported factory run receipt in qualification evidence")
        seen.add(receipt["content_sha256"])
        result = result_by_receipt[receipt["content_sha256"]]
        intelligence = receipt.get("intelligence", {})
        _valid_hash(intelligence, "Factory intelligence summary")
        if intelligence.get("mode") != "model-backed":
            raise ContractError("Qualification rejects non-model-backed factory runs")
        provider = str(intelligence.get("provider", ""))
        model = str(intelligence.get("model", ""))
        if provider in {"", "local-reference", "scripted-test"} or not model:
            raise ContractError("Qualification rejects reference or unidentified model providers")
        providers.add(provider)
        models.add(model)
        if result.get("status") != receipt.get("status") or int(
            result.get("attempts", -1)
        ) != int(receipt.get("attempts", -2)):
            raise ContractError("Evaluation result disagrees with its factory run receipt")
        metric_fields = {
            "model_calls": "calls",
            "provider_attempts": "provider_attempts",
            "provider_retries": "provider_retries",
            "input_tokens": "input_tokens",
            "output_tokens": "output_tokens",
            "estimated_cost_usd": "estimated_cost_usd",
            "elapsed_ms": "elapsed_ms",
            "cost_estimate_available": "cost_estimate_available",
        }
        for result_field, intelligence_field in metric_fields.items():
            if result.get(result_field) != intelligence.get(intelligence_field):
                raise ContractError(
                    f"Evaluation result {result_field} disagrees with model provenance"
                )
        elapsed_ms += int(intelligence.get("elapsed_ms", 0))
        retries += int(intelligence.get("provider_retries", 0))
        call_hashes.extend(str(item) for item in intelligence.get("call_evidence_sha256", []))
        artifact_hashes = {
            str(item.get("content_sha256"))
            for item in receipt.get("artifacts", [])
            if item.get("artifact_type") == "model-call-evidence"
        }
        if artifact_hashes != set(intelligence.get("call_evidence_sha256", [])):
            raise ContractError("Model-call provenance does not match run artifacts")
        for reference in receipt.get("artifacts", []):
            if reference.get("artifact_type") != "model-call-evidence":
                continue
            artifact_path = path.parent / str(reference.get("path"))
            if not artifact_path.is_file():
                raise ContractError("Model-call evidence artifact is missing")
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
            _valid_hash(artifact, "Model-call evidence artifact")
            if artifact.get("schema_version") != "1.0" or artifact.get(
                "artifact_type"
            ) != "model-call-evidence":
                raise ContractError("Unsupported model-call evidence artifact")
            if artifact["content_sha256"] != reference.get("content_sha256"):
                raise ContractError("Model-call evidence reference is stale")
            if artifact.get("run_id") != receipt.get("run_id"):
                raise ContractError("Model-call evidence belongs to a different factory run")
            content = artifact.get("content", {})
            _valid_hash(content, "Model-call evidence")
            if content.get("schema_version") != "1.0" or content.get(
                "evidence_type"
            ) != "lightyear-model-call":
                raise ContractError("Unsupported model-call evidence content")
            if content.get("provider") != provider or content.get("model") != model:
                raise ContractError("Model-call evidence disagrees with run provider identity")
            manifest = content.get("request_manifest", {})
            for field in ("instruction_sha256", "payload_sha256", "schema_sha256"):
                if not re.fullmatch(r"[0-9a-f]{64}", str(manifest.get(field, ""))):
                    raise ContractError("Model prompt/context provenance is incomplete")
    if seen != expected:
        raise ContractError("Evaluation results do not resolve to exact factory run receipts")
    totals = evaluation.get("totals", {})
    expected_totals = {
        "model_calls": sum(int(item.get("model_calls", 0)) for item in results),
        "provider_attempts": sum(int(item.get("provider_attempts", 0)) for item in results),
        "provider_retries": sum(int(item.get("provider_retries", 0)) for item in results),
        "input_tokens": sum(int(item.get("input_tokens", 0)) for item in results),
        "output_tokens": sum(int(item.get("output_tokens", 0)) for item in results),
        "estimated_cost_usd": round(
            sum(float(item.get("estimated_cost_usd", 0)) for item in results), 8
        ),
        "cost_estimate_available": all(
            bool(item.get("cost_estimate_available")) for item in results
        ),
    }
    for field, value in expected_totals.items():
        if totals.get(field) != value:
            raise ContractError(f"Evaluation total {field} disagrees with exact run evidence")
    return {
        "providers": sorted(providers),
        "models": sorted(models),
        "call_evidence_sha256": sorted(call_hashes),
        "elapsed_ms": elapsed_ms,
        "provider_retries": retries,
    }


def _load_evaluation(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    if path.name != "evaluation.receipt.json":
        raise ContractError("Qualification inputs must be evaluation.receipt.json files")
    payload = json.loads(path.read_text(encoding="utf-8"))
    _valid_hash(payload, "Evaluation receipt")
    if payload.get("schema_version") != "2.0" or payload.get(
        "receipt_type"
    ) != "lightyear-model-workcell-evaluation":
        raise ContractError("Unsupported qualification evaluation receipt")
    if payload.get("evaluation_class") != "sealed-holdout":
        raise ContractError("Factory qualification requires sealed holdout evidence")
    binding = payload.get("sealed_binding") or {}
    _valid_hash(binding, "Sealed evaluation binding")
    quality = payload.get("quality_gate") or {}
    _valid_hash(quality, "Factory quality gate")
    if not binding.get("signature_valid") or quality.get("status") != "qualified":
        raise ContractError("Evaluation is not independently sealed and qualified")
    if payload.get("status") != "passed" or payload.get("completed_cases") != payload.get(
        "planned_cases"
    ):
        raise ContractError("Evaluation did not complete successfully")
    if not payload.get("totals", {}).get("cost_estimate_available"):
        raise ContractError("Qualification requires enforceable model cost evidence")
    return payload, _run_provenance(path.parent, payload)


def qualify_factory(
    manifest: QualificationManifest,
    evaluation_receipts: list[Path],
    portfolio_plan_path: Path,
    portfolio_run_path: Path,
    output_path: Path | None = None,
) -> dict[str, Any]:
    evaluations: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {
        item: [] for item in manifest.required_workloads
    }
    for path in evaluation_receipts:
        receipt, provenance = _load_evaluation(path.resolve())
        workload_id = str(receipt.get("workload_id", ""))
        if workload_id not in evaluations:
            raise ContractError(f"Unexpected qualification workload: {workload_id}")
        evaluations[workload_id].append((receipt, provenance))

    plan = json.loads(portfolio_plan_path.read_text(encoding="utf-8"))
    run = json.loads(portfolio_run_path.read_text(encoding="utf-8"))
    _valid_hash(plan, "Portfolio plan")
    _valid_hash(run, "Portfolio run receipt")
    if plan.get("schema_version") != "1.0" or plan.get(
        "plan_type"
    ) != "lightyear-modernization-portfolio-plan":
        raise ContractError("Unsupported portfolio plan")
    if run.get("schema_version") != "1.0" or run.get(
        "receipt_type"
    ) != "lightyear-modernization-portfolio-run":
        raise ContractError("Unsupported portfolio run receipt")
    if run.get("plan_sha256") != plan.get("content_sha256"):
        raise ContractError("Portfolio run targets a different plan")
    if run.get("portfolio_id") != plan.get("portfolio_id"):
        raise ContractError("Portfolio run identifies a different portfolio")

    all_receipts = [row for rows in evaluations.values() for row, _ in rows]
    all_provenance = [row for rows in evaluations.values() for _, row in rows]
    results = [item for receipt in all_receipts for item in receipt.get("results", [])]
    mutations = [item for item in results if item.get("expectation") == "reject-and-repair"]
    clean = [item for item in results if item.get("expectation") == "accept-unchanged"]
    repaired = sum(bool(item.get("autonomously_repaired")) for item in mutations)
    correct_no_change = sum(bool(item.get("correct_no_change")) for item in clean)
    first_attempt = sum(bool(item.get("first_attempt_repair")) for item in mutations)
    false_acceptances = sum(bool(item.get("false_acceptance")) for item in results)
    false_rejections = len(clean) - correct_no_change
    escalations = sum(int(item.get("attempts", 0)) > 1 for item in results)
    input_tokens = sum(int(item.get("input_tokens", 0)) for item in results)
    total_cost = round(
        sum(float(receipt.get("totals", {}).get("estimated_cost_usd", 0)) for receipt in all_receipts),
        8,
    )
    elapsed_ms = sum(int(item.get("elapsed_ms", 0)) for item in results)
    policy = manifest.policy
    metrics = {
        "workloads": len(evaluations),
        "evaluation_runs": len(all_receipts),
        "cases": len(results),
        "mutation_cases": len(mutations),
        "clean_cases": len(clean),
        "autonomously_repaired": repaired,
        "repair_rate": round(repaired / len(mutations), 6) if mutations else 0.0,
        "correct_no_changes": correct_no_change,
        "correct_no_change_rate": round(correct_no_change / len(clean), 6) if clean else 0.0,
        "first_attempt_repair_rate": round(first_attempt / len(mutations), 6) if mutations else 0.0,
        "false_acceptances": false_acceptances,
        "false_rejections": false_rejections,
        "escalations": escalations,
        "provider_retries": sum(item["provider_retries"] for item in all_provenance),
        "resume_count": sum(int(item.get("resume_count", 0)) for item in all_receipts),
        "average_latency_ms": round(elapsed_ms / len(results)) if results else 0,
        "average_input_tokens": round(input_tokens / len(results)) if results else 0,
        "total_cost_usd": total_cost,
    }
    workload_rows = []
    for workload_id in manifest.required_workloads:
        rows = evaluations[workload_id]
        workload_rows.append(
            {
                "workload_id": workload_id,
                "runs": len(rows),
                "receipt_sha256": sorted(item[0]["content_sha256"] for item in rows),
                "sealed_binding_sha256": sorted(
                    item[0]["sealed_binding"]["content_sha256"] for item in rows
                ),
                "providers": sorted({v for item in rows for v in item[1]["providers"]}),
                "models": sorted({v for item in rows for v in item[1]["models"]}),
                "model_call_evidence_sha256": sorted(
                    v for item in rows for v in item[1]["call_evidence_sha256"]
                ),
            }
        )
    repeated = all(
        item["runs"] >= policy.minimum_runs_per_workload
        and len(set(item["receipt_sha256"])) == item["runs"]
        for item in workload_rows
    )
    plan_orders = {str(item.get("id")) for item in plan.get("orders", [])}
    cell_rows = run.get("cells", [])
    run_cells = {str(item.get("work_order_id")) for item in cell_rows}
    cells_valid = len(cell_rows) == len(run_cells) and all(
        item.get("status") == "passed"
        and re.fullmatch(r"[0-9a-f]{64}", str(item.get("receipt_sha256", "")))
        for item in cell_rows
    )
    checks = {
        "all_workloads_present": all(bool(evaluations[item]) for item in evaluations),
        "repeated_runs": repeated,
        "sealed_holdouts": all(
            receipt.get("evaluation_class") == "sealed-holdout" for receipt in all_receipts
        ),
        "model_backed": all(bool(item["call_evidence_sha256"]) for item in all_provenance),
        "qualified_workcells": all(
            receipt.get("quality_gate", {}).get("status") == "qualified"
            for receipt in all_receipts
        ),
        "repair_rate": metrics["repair_rate"] >= policy.minimum_repair_rate,
        "correct_no_change_rate": metrics["correct_no_change_rate"]
        >= policy.minimum_correct_no_change_rate,
        "first_attempt_repair_rate": metrics["first_attempt_repair_rate"]
        >= policy.minimum_first_attempt_repair_rate,
        "zero_critical_false_acceptance": false_acceptances
        <= policy.maximum_false_acceptances,
        "false_rejections": false_rejections <= policy.maximum_false_rejections,
        "latency": metrics["average_latency_ms"] <= policy.maximum_average_latency_ms,
        "token_efficiency": metrics["average_input_tokens"]
        <= policy.maximum_average_input_tokens,
        "cost": total_cost <= policy.maximum_total_cost_usd,
        "portfolio_conflict_detection": bool(plan.get("conflicts")),
        "portfolio_parallel_waves": any(
            int(item.get("parallelism", 0)) > 1 for item in plan.get("waves", [])
        ),
        "portfolio_approval_barrier": bool(plan.get("approval", {}).get("required"))
        and bool(re.fullmatch(r"[0-9a-f]{64}", str(run.get("admission_sha256", "")))),
        "portfolio_completed": run.get("status") == "passed"
        and cells_valid
        and len(plan_orders) == 4
        and run_cells == plan_orders,
    }
    status = "qualified" if all(checks.values()) else "blocked"
    payload = {
        "schema_version": QUALIFICATION_VERSION,
        "receipt_type": "lightyear-multi-workload-factory-qualification",
        "qualification_id": manifest.qualification_id,
        "manifest_sha256": manifest.content_sha256,
        "status": status,
        "promotion_allowed": status == "qualified" and false_acceptances == 0,
        "production_ready": False,
        "mainframe_equivalent": False,
        "policy": policy.to_dict(),
        "metrics": metrics,
        "checks": checks,
        "workloads": workload_rows,
        "portfolio": {
            "plan_sha256": plan["content_sha256"],
            "run_receipt_sha256": run["content_sha256"],
            "conflicts": len(plan.get("conflicts", [])),
            "waves": len(plan.get("waves", [])),
            "resume_count": int(run.get("resume_count", 0)),
        },
        "limitations": [
            "Factory qualification measures bounded modernization workcells, not arbitrary codebases.",
            "Qualification does not prove native z/OS execution or mainframe equivalence.",
            "A critical false acceptance blocks promotion regardless of aggregate repair rate.",
        ],
    }
    payload["content_sha256"] = canonical_hash(payload)
    if output_path:
        write_json(payload, output_path)
    return payload
