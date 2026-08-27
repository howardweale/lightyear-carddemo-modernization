from __future__ import annotations

import json
import hashlib
import shutil
import sys
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from lightyear_common.io import write_text as write_deterministic_text

from .agents import AgentSet
from .contracts import ContractError, WorkOrder, canonical_hash, safe_relative_path, write_json
from .orchestrator import FactoryOrchestrator
from .providers import ProviderError
from .quality import QualityPolicy, quality_scorecard
from .workspace import IsolatedWorkspace
from .workloads import workload_profile
from lightyear_knowledge_graph.evidence_pack import load_evidence_pack


EVALUATION_CLASSES = {"public-calibration", "sealed-holdout"}


@dataclass(frozen=True)
class EvaluationPolicy:
    """Controller-owned limits for a multi-case model evaluation."""

    max_cost_usd: float = 15.0
    max_tokens: int = 8_000_000
    max_model_calls: int = 180
    max_case_cost_usd: float = 2.0
    max_case_tokens: int = 400_000
    pace_seconds: float = 1.0
    require_cost_estimate: bool = False

    def __post_init__(self) -> None:
        if self.max_cost_usd <= 0 or self.max_case_cost_usd <= 0:
            raise ContractError("Evaluation cost budgets must be greater than zero")
        if self.max_tokens < 1_000 or self.max_case_tokens < 1_000 or self.max_model_calls < 1:
            raise ContractError("Evaluation token and call budgets must be positive")
        if self.pace_seconds < 0 or self.pace_seconds > 300:
            raise ContractError("Evaluation pacing must be between zero and 300 seconds")

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_cost_usd": self.max_cost_usd,
            "max_tokens": self.max_tokens,
            "max_model_calls": self.max_model_calls,
            "max_case_cost_usd": self.max_case_cost_usd,
            "max_case_tokens": self.max_case_tokens,
            "pace_seconds": self.pace_seconds,
            "require_cost_estimate": self.require_cost_estimate,
        }


def normalize_evaluation_catalog(payload: dict[str, Any]) -> dict[str, Any]:
    payload = json.loads(json.dumps(payload))
    if payload.get("schema_version") != "1.0":
        raise ContractError("Unsupported evaluation catalog schema")
    if payload.get("evaluation_class") not in EVALUATION_CLASSES:
        raise ContractError("evaluation_class must be public-calibration or sealed-holdout")
    target = safe_relative_path(str(payload.get("target_path", "")))
    workload_profile(payload.get("workload_id"), target)
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ContractError("Evaluation catalog requires at least one case")
    seen: set[str] = set()
    for case in cases:
        case_id = str(case.get("id", "")).strip()
        if not case_id or case_id in seen:
            raise ContractError(f"Evaluation case id is missing or duplicated: {case_id}")
        seen.add(case_id)
        if not str(case.get("category", "")).strip():
            raise ContractError(f"Evaluation case {case_id} requires a category")
        expectation = str(case.get("expectation", "reject-and-repair"))
        if expectation not in {"reject-and-repair", "accept-unchanged"}:
            raise ContractError(f"Evaluation case {case_id} has an invalid expectation")
        case["expectation"] = expectation
        if expectation == "reject-and-repair":
            before = case.get("before")
            after = case.get("after")
            if not isinstance(before, str) or not before or not isinstance(after, str):
                raise ContractError(f"Evaluation case {case_id} requires text mutation markers")
            if before == after:
                raise ContractError(f"Evaluation case {case_id} does not change the target")
        for field in ("relevant_evidence_owner_ids", "forbidden_public_markers"):
            values = case.get(field, [])
            if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
                raise ContractError(f"Evaluation case {case_id} {field} must be strings")
    minimum = float(payload.get("minimum_repair_rate", 0.7))
    if not 0 <= minimum <= 1:
        raise ContractError("minimum_repair_rate must be between zero and one")
    payload["target_path"] = target
    payload["minimum_repair_rate"] = minimum
    return payload


def load_evaluation_catalog(path: Path) -> dict[str, Any]:
    return normalize_evaluation_catalog(json.loads(path.read_text(encoding="utf-8")))


def validate_evaluation_catalog(project_root: Path, catalog: dict[str, Any]) -> dict[str, Any]:
    profile = workload_profile(catalog.get("workload_id"), catalog["target_path"])
    target = project_root.resolve() / catalog["target_path"]
    if not target.is_file():
        raise ContractError(f"Evaluation target does not exist: {catalog['target_path']}")
    content = target.read_text(encoding="utf-8")
    for case in catalog["cases"]:
        if case["expectation"] == "accept-unchanged":
            continue
        count = content.count(case["before"])
        if count != 1:
            raise ContractError(
                f"Evaluation case {case['id']} expected one canonical marker; found {count}"
            )
    minimum = catalog["minimum_repair_rate"]
    summary = {
        "schema_version": "1.0",
        "catalog_id": catalog["id"],
        "evaluation_class": catalog["evaluation_class"],
        "cases": len(catalog["cases"]),
        "categories": dict(sorted(Counter(item["category"] for item in catalog["cases"]).items())),
        "expectations": dict(
            sorted(Counter(item["expectation"] for item in catalog["cases"]).items())
        ),
        "target_path": catalog["target_path"],
        "workload_id": profile.workload_id,
        "workload_profile_sha256": canonical_hash(profile.to_dict()),
        "minimum_repair_rate": minimum,
        "status": "passed",
    }
    summary["content_sha256"] = canonical_hash(summary)
    return summary


def evaluation_work_order(
    case: dict[str, Any],
    target_path: str,
    policy: EvaluationPolicy | None = None,
    remaining: dict[str, float | int] | None = None,
    *,
    evaluation_class: str = "public-calibration",
    case_ref: str | None = None,
    workload_id: str = "INTCALC",
) -> WorkOrder:
    policy = policy or EvaluationPolicy()
    remaining = remaining or {
        "cost_usd": policy.max_cost_usd,
        "tokens": policy.max_tokens,
        "model_calls": policy.max_model_calls,
    }
    sealed = evaluation_class == "sealed-holdout"
    public_id = case_ref or case["id"]
    profile = workload_profile(workload_id, target_path)
    return WorkOrder.from_dict(
        {
            "schema_version": "1.0",
            "id": f"evaluation:carddemo:{profile.workload_id.lower()}:{public_id}",
            "title": (
                "Evaluate an unfamiliar isolated CardDemo candidate"
                if sealed
                else f"Repair isolated CardDemo {case['category']} regression"
            ),
            "goal": (
                "Restore source-faithful CardDemo behavior using graph and source evidence, then "
                "prove the result with the private acceptance gate."
            ),
            "non_goals": [
                "Do not access the mutation catalog or verifier-private cases.",
                "Do not widen the modernization architecture or claim z/OS equivalence.",
            ],
            "scope": {
                "allowed_paths": [target_path],
                "graph_node_ids": list(profile.graph_node_ids),
            },
            "acceptance": {
                "baseline_first": True,
                "max_attempts": 3,
                "gates": [{
                    "id": profile.gate_id,
                    "command": [sys.executable, "-m", profile.gate_module],
                    "timeout_seconds": 30,
                    "expose_output_to_builder": False,
                }],
            },
            "policy": {
                "audience": "implementer",
                "allow_network": False,
                "max_files_changed": 1,
                "max_patch_bytes": 8_192,
                "max_changed_lines": 80,
                "max_context_bytes": 200_000,
                "max_file_bytes": 250_000,
                "max_model_calls": min(10, int(remaining["model_calls"])),
                "max_model_input_bytes": 2_000_000,
                "max_model_output_bytes": 500_000,
                "max_model_tokens": min(policy.max_case_tokens, int(remaining["tokens"])),
                "max_model_cost_usd": min(
                    policy.max_case_cost_usd, float(remaining["cost_usd"])
                ),
                "max_elapsed_seconds": 1_800,
            },
            "metadata": {
                "evaluation_case_ref": public_id,
                "evaluation_class": evaluation_class,
                "workload_id": profile.workload_id,
                **({} if sealed else {
                    "evaluation_case_id": case["id"],
                    "evaluation_category": case["category"],
                }),
            },
        }
    )


def run_model_evaluation(
    project_root: Path,
    output_root: Path,
    catalog_path: Path,
    agents_factory: Callable[[WorkOrder], AgentSet],
    *,
    policy: EvaluationPolicy | None = None,
    catalog_override: dict[str, Any] | None = None,
    sealed_binding: dict[str, Any] | None = None,
    quality_policy: QualityPolicy | None = None,
    resume: bool = False,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    output_root = output_root.resolve()
    policy = policy or EvaluationPolicy()
    catalog = (
        normalize_evaluation_catalog(catalog_override)
        if catalog_override is not None
        else load_evaluation_catalog(catalog_path)
    )
    if catalog["evaluation_class"] == "sealed-holdout":
        if not sealed_binding or not sealed_binding.get("signature_valid"):
            raise ContractError("Sealed holdout evaluation requires a verified envelope")
    elif sealed_binding:
        raise ContractError("Public calibration catalogs cannot use a sealed binding")
    validation = validate_evaluation_catalog(project_root, catalog)
    catalog_sha256 = canonical_hash(catalog)
    if sealed_binding and sealed_binding.get("catalog_sha256") != catalog_sha256:
        raise ContractError("Sealed binding does not match the evaluation catalog")
    quality_policy = quality_policy or QualityPolicy.load(
        project_root / "factory" / "evals" / "quality-policy.json"
    )
    checkpoint_path = output_root / "evaluation.checkpoint.json"
    receipt_path = output_root / "evaluation.receipt.json"
    results: list[dict[str, Any]] = []
    resume_count = 0
    if resume:
        if not checkpoint_path.is_file():
            raise ContractError("Resume requested but evaluation.checkpoint.json is missing")
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        if checkpoint.get("catalog_sha256") != catalog_sha256:
            raise ContractError("Resume catalog does not match the evaluation checkpoint")
        if checkpoint.get("policy") != policy.to_dict():
            raise ContractError("Resume policy does not match the evaluation checkpoint")
        if checkpoint.get("quality_policy_sha256") != quality_policy.content_sha256:
            raise ContractError("Resume quality policy does not match the evaluation checkpoint")
        if checkpoint.get("sealed_binding_sha256") != (
            sealed_binding.get("content_sha256") if sealed_binding else None
        ):
            raise ContractError("Resume sealed binding does not match the evaluation checkpoint")
        results = list(checkpoint.get("results", []))
        resume_count = int(checkpoint.get("resume_count", 0)) + 1
    elif checkpoint_path.exists() or receipt_path.exists():
        raise ContractError("Evaluation output already exists; use --resume or a new output root")

    target_source = project_root / catalog["target_path"]
    seed_root = output_root / "seed"
    target_seed = seed_root / catalog["target_path"]
    if not target_seed.exists():
        target_seed.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target_source, target_seed)
    elif target_seed.read_bytes() != target_source.read_bytes():
        raise ContractError("Evaluation seed differs from the current canonical target")
    runs_root = output_root / "runs"
    case_refs = {
        case["id"]: _case_ref(catalog_sha256, case["id"])
        for case in catalog["cases"]
    }
    completed_case_refs = {item["case_ref"] for item in results}
    stopped_reason: dict[str, Any] | None = None
    _write_checkpoint(
        checkpoint_path, catalog, catalog_sha256, validation, policy, quality_policy,
        sealed_binding, results, "running", None, resume_count
    )
    evidence_pack = load_evidence_pack(
        project_root / "knowledge" / "evidence" / "source.pack.json.gz"
    )

    for case_index, case in enumerate(catalog["cases"]):
        case_ref = case_refs[case["id"]]
        if case_ref in completed_case_refs:
            continue
        totals = _totals(results)
        remaining = {
            "cost_usd": round(policy.max_cost_usd - totals["estimated_cost_usd"], 8),
            "tokens": policy.max_tokens - totals["input_tokens"] - totals["output_tokens"],
            "model_calls": policy.max_model_calls - totals["model_calls"],
        }
        exhausted = [name for name, value in remaining.items() if value <= 0]
        if remaining["tokens"] < 1_000 and "tokens" not in exhausted:
            exhausted.append("tokens")
        if exhausted:
            stopped_reason = {
                "code": "evaluation_budget_exhausted",
                "budgets": exhausted,
                "case_ref": case_ref,
            }
            break
        order = evaluation_work_order(
            case,
            catalog["target_path"],
            policy,
            remaining,
            evaluation_class=catalog["evaluation_class"],
            case_ref=case_ref,
            workload_id=workload_profile(
                catalog.get("workload_id"), catalog["target_path"]
            ).workload_id,
        )

        def prepare(
            workspace: IsolatedWorkspace,
            _: WorkOrder,
            current_case: dict[str, Any] = case,
        ) -> None:
            if current_case["expectation"] == "accept-unchanged":
                return
            path = workspace.resolve(catalog["target_path"])
            content = path.read_text(encoding="utf-8")
            before = current_case["before"]
            after = current_case["after"]
            if content.count(before) != 1:
                raise ContractError("Mutation marker is not unique for the sealed case")
            write_deterministic_text(path, content.replace(before, after, 1))

        try:
            receipt = FactoryOrchestrator(
                seed_root,
                runs_root,
                agents_factory(order),
                graph_path=project_root / "knowledge" / "graph.snapshot.json.gz",
                evidence_path=project_root / "knowledge" / "evidence" / "source.pack.json.gz",
                prepare_workspace=prepare,
            ).run(order, _next_run_id(runs_root, case_ref))
        except ProviderError as exc:
            stopped_reason = {
                "code": "provider_error",
                "case_ref": case_ref,
                "provider_error": exc.safe_dict(),
            }
            break
        except ContractError as exc:
            stopped_reason = {
                "code": "controller_error",
                "case_ref": case_ref,
                "error_type": type(exc).__name__,
            }
            break

        events = [
            json.loads(line)
            for line in (runs_root / receipt["run_id"] / "events.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line
        ]
        baseline = [item for item in events if item["kind"] == "baseline_verified"]
        baseline_status = baseline[-1]["payload"].get("status") if baseline else "not_run"
        baseline_rejected = baseline_status == "failed"
        mutation = case["expectation"] == "reject-and-repair"
        repaired = (
            mutation and baseline_rejected and receipt["status"] == "passed"
            and receipt["attempts"] > 0
        )
        correct_no_change = (
            not mutation and baseline_status == "passed" and receipt["status"] == "passed"
            and receipt["attempts"] == 0
        )
        false_acceptance = bool(
            mutation and receipt["status"] == "passed" and not baseline_rejected
        )
        intelligence = receipt.get("intelligence", {})
        result = {
            "case_ref": case_ref,
            **({} if catalog["evaluation_class"] == "sealed-holdout" else {
                "case_id": case["id"],
                "category": case["category"],
            }),
            "expectation": case["expectation"],
            "status": receipt["status"],
            "attempts": receipt["attempts"],
            "baseline_rejected": baseline_rejected,
            "autonomously_repaired": repaired,
            "correct_no_change": correct_no_change,
            "false_acceptance": false_acceptance,
            "first_attempt_repair": repaired and receipt["attempts"] == 1,
            "evidence_selection": _score_evidence_selection(
                runs_root / receipt["run_id"], receipt, case, evidence_pack
            ),
            "private_evidence_leaks": _private_evidence_leaks(
                runs_root / receipt["run_id"], receipt, case
            ),
            "unauthorized_edit_attempts": _unauthorized_edit_attempts(events),
            "model_calls": intelligence.get("calls", 0),
            "provider_attempts": intelligence.get("provider_attempts", intelligence.get("calls", 0)),
            "provider_retries": intelligence.get("provider_retries", 0),
            "input_tokens": intelligence.get("input_tokens", 0),
            "output_tokens": intelligence.get("output_tokens", 0),
            "estimated_cost_usd": intelligence.get("estimated_cost_usd", 0.0),
            "elapsed_ms": intelligence.get("elapsed_ms", 0),
            "cost_estimate_available": intelligence.get("cost_estimate_available", False),
            "receipt_sha256": receipt["content_sha256"],
        }
        results.append(result)
        completed_case_refs.add(case_ref)
        if policy.require_cost_estimate and not result["cost_estimate_available"]:
            stopped_reason = {"code": "cost_estimate_unavailable", "case_ref": case_ref}
        _write_checkpoint(
            checkpoint_path,
            catalog,
            catalog_sha256,
            validation,
            policy,
            quality_policy,
            sealed_binding,
            results,
            "stopped" if stopped_reason else "running",
            stopped_reason,
            resume_count,
        )
        if stopped_reason:
            break
        if case_index < len(catalog["cases"]) - 1 and policy.pace_seconds:
            sleep(policy.pace_seconds)

    status = "stopped" if stopped_reason else _evaluation_status(catalog, results)
    payload = _evaluation_receipt(
        catalog, catalog_sha256, validation, policy, quality_policy, sealed_binding,
        results, status, stopped_reason, resume_count
    )
    write_json(payload, receipt_path)
    _write_checkpoint(
        checkpoint_path,
        catalog,
        catalog_sha256,
        validation,
        policy,
        quality_policy,
        sealed_binding,
        results,
        "completed" if status in {"passed", "failed"} else "stopped",
        stopped_reason,
        resume_count,
    )
    return payload


def _next_run_id(runs_root: Path, case_id: str) -> str:
    base = f"eval-{case_id}"
    if not (runs_root / base).exists():
        return base
    sequence = 2
    while (runs_root / f"{base}-run-{sequence}").exists():
        sequence += 1
    return f"{base}-run-{sequence}"


def _case_ref(catalog_sha256: str, case_id: str) -> str:
    digest = hashlib.sha256(f"{catalog_sha256}:{case_id}".encode("utf-8")).hexdigest()
    return f"case-{digest[:20]}"


def _artifact_content(run_dir: Path, receipt: dict[str, Any], artifact_type: str) -> dict[str, Any]:
    for reference in receipt.get("artifacts", []):
        if reference.get("artifact_type") != artifact_type:
            continue
        path = (run_dir / str(reference.get("path", ""))).resolve()
        if run_dir.resolve() not in path.parents or not path.is_file():
            continue
        return json.loads(path.read_text(encoding="utf-8")).get("content", {})
    return {}


def _score_evidence_selection(
    run_dir: Path,
    receipt: dict[str, Any],
    case: dict[str, Any],
    evidence_pack: dict[str, Any],
) -> dict[str, Any]:
    expected = set(case.get("relevant_evidence_owner_ids", []))
    if not expected:
        return {"available": False, "selected_capsules": 0, "precision": 0.0, "recall": 0.0}
    plan = _artifact_content(run_dir, receipt, "plan")
    selected = {
        capsule_id
        for task in plan.get("tasks", [])
        for capsule_id in task.get("evidence_capsule_ids", [])
    }
    owners_by_capsule = {
        item["capsule_id"]: {
            support.get("owner_id") for support in item.get("supports", [])
            if support.get("owner_id")
        }
        for item in evidence_pack.get("capsules", [])
    }
    selected_owners = set().union(*(owners_by_capsule.get(item, set()) for item in selected)) \
        if selected else set()
    relevant = selected_owners & expected
    return {
        "available": True,
        "selected_capsules": len(selected),
        "precision": round(len(relevant) / len(selected_owners), 6) if selected_owners else 0.0,
        "recall": round(len(relevant) / len(expected), 6),
    }


def _private_evidence_leaks(
    run_dir: Path, receipt: dict[str, Any], case: dict[str, Any]
) -> int:
    markers = {"inspector_private", *case.get("forbidden_public_markers", [])}
    leaks = 0
    for reference in receipt.get("artifacts", []):
        if reference.get("visibility") == "verifier_private":
            continue
        path = (run_dir / str(reference.get("path", ""))).resolve()
        if run_dir.resolve() not in path.parents or not path.is_file():
            continue
        content = path.read_text(encoding="utf-8")
        leaks += sum(marker in content for marker in markers if marker)
    return leaks


def _unauthorized_edit_attempts(events: list[dict[str, Any]]) -> int:
    indicators = ("unauthorized path", "outside allowed", "not approved", "unsafe")
    return sum(
        event.get("kind") == "controller_error"
        and any(marker in str(event.get("payload", {}).get("message", "")).lower() for marker in indicators)
        for event in events
    )


def _totals(results: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "model_calls": sum(int(item["model_calls"]) for item in results),
        "provider_attempts": sum(int(item.get("provider_attempts", item["model_calls"])) for item in results),
        "provider_retries": sum(int(item.get("provider_retries", 0)) for item in results),
        "input_tokens": sum(int(item["input_tokens"]) for item in results),
        "output_tokens": sum(int(item["output_tokens"]) for item in results),
        "estimated_cost_usd": round(
            sum(float(item["estimated_cost_usd"]) for item in results), 8
        ),
        "cost_estimate_available": bool(results)
        and all(bool(item["cost_estimate_available"]) for item in results),
    }


def _evaluation_status(catalog: dict[str, Any], results: list[dict[str, Any]]) -> str:
    mutation = [item for item in results if item["expectation"] == "reject-and-repair"]
    clean = [item for item in results if item["expectation"] == "accept-unchanged"]
    repaired = sum(bool(item["autonomously_repaired"]) for item in mutation)
    rejected = sum(bool(item["baseline_rejected"]) for item in mutation)
    false_acceptances = sum(bool(item["false_acceptance"]) for item in results)
    repair_rate = repaired / len(mutation) if mutation else 1.0
    return (
        "passed"
        if len(results) == len(catalog["cases"])
        and rejected == len(mutation)
        and all(item["correct_no_change"] for item in clean)
        and false_acceptances == 0
        and repair_rate >= catalog["minimum_repair_rate"]
        else "failed"
    )


def _evaluation_receipt(
    catalog: dict[str, Any],
    catalog_sha256: str,
    validation: dict[str, Any],
    policy: EvaluationPolicy,
    quality_policy: QualityPolicy,
    sealed_binding: dict[str, Any] | None,
    results: list[dict[str, Any]],
    status: str,
    stopped_reason: dict[str, Any] | None,
    resume_count: int,
) -> dict[str, Any]:
    mutation = [item for item in results if item["expectation"] == "reject-and-repair"]
    clean = [item for item in results if item["expectation"] == "accept-unchanged"]
    repaired = sum(bool(item["autonomously_repaired"]) for item in mutation)
    correct_no_change = sum(bool(item["correct_no_change"]) for item in clean)
    false_acceptances = sum(bool(item["false_acceptance"]) for item in results)
    rejected = sum(bool(item["baseline_rejected"]) for item in mutation)
    quality = quality_scorecard(
        catalog["evaluation_class"], validation["categories"], results,
        quality_policy, sealed_binding,
    )
    payload = {
        "schema_version": "2.0",
        "receipt_type": "lightyear-model-workcell-evaluation",
        "evaluation_id": (
            f"sealed:{catalog_sha256[:20]}"
            if catalog["evaluation_class"] == "sealed-holdout" else catalog["id"]
        ),
        "evaluation_class": catalog["evaluation_class"],
        "workload_id": workload_profile(
            catalog.get("workload_id"), catalog["target_path"]
        ).workload_id,
        "catalog_sha256": catalog_sha256,
        "catalog_validation_sha256": validation["content_sha256"],
        "planned_cases": len(catalog["cases"]),
        "completed_cases": len(results),
        "cases": len(results),
        "categories": (
            {"sealed": len(results)}
            if catalog["evaluation_class"] == "sealed-holdout" else validation["categories"]
        ),
        "mutation_cases": len(mutation),
        "clean_cases": len(clean),
        "baselines_rejected": rejected,
        "autonomously_repaired": repaired,
        "repair_rate": round(repaired / len(mutation), 6) if mutation else 1.0,
        "correct_no_changes": correct_no_change,
        "correct_no_change_rate": round(correct_no_change / len(clean), 6) if clean else 1.0,
        "minimum_repair_rate": catalog["minimum_repair_rate"],
        "false_acceptances": false_acceptances,
        "status": status,
        "stopped_reason": stopped_reason,
        "resume_count": resume_count,
        "policy": policy.to_dict(),
        "quality_gate": quality,
        "sealed_binding": sealed_binding,
        "results": results,
        "totals": _totals(results),
        "limitations": [
            "Public calibration cases are not evidence of blind generalization.",
            "Only an externally controlled sealed-holdout catalog can produce holdout evidence.",
            "Synthetic faults do not prove z/OS equivalence.",
            "A qualified scorecard is a promotion input, not an autonomous production approval.",
        ],
    }
    payload["content_sha256"] = canonical_hash(payload)
    return payload


def _write_checkpoint(
    path: Path,
    catalog: dict[str, Any],
    catalog_sha256: str,
    validation: dict[str, Any],
    policy: EvaluationPolicy,
    quality_policy: QualityPolicy,
    sealed_binding: dict[str, Any] | None,
    results: list[dict[str, Any]],
    status: str,
    stopped_reason: dict[str, Any] | None,
    resume_count: int,
) -> None:
    payload = {
        "schema_version": "1.1",
        "receipt_type": "lightyear-model-workcell-evaluation-checkpoint",
        "evaluation_id": (
            f"sealed:{catalog_sha256[:20]}"
            if catalog["evaluation_class"] == "sealed-holdout" else catalog["id"]
        ),
        "catalog_sha256": catalog_sha256,
        "catalog_validation_sha256": validation["content_sha256"],
        "status": status,
        "completed_case_refs": [item["case_ref"] for item in results],
        **({
            "completed_case_ids": [item["case_id"] for item in results]
        } if catalog["evaluation_class"] == "public-calibration" else {}),
        "results": results,
        "totals": _totals(results),
        "policy": policy.to_dict(),
        "quality_policy_sha256": quality_policy.content_sha256,
        "sealed_binding_sha256": sealed_binding.get("content_sha256") if sealed_binding else None,
        "stopped_reason": stopped_reason,
        "resume_count": resume_count,
    }
    payload["content_sha256"] = canonical_hash(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    write_deterministic_text(temporary, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)
