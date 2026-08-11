from __future__ import annotations

import json
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Callable

from .agents import AgentSet
from .contracts import ContractError, WorkOrder, canonical_hash, safe_relative_path, write_json
from .orchestrator import FactoryOrchestrator
from .workspace import IsolatedWorkspace


EVALUATION_CLASSES = {"public-calibration", "sealed-holdout"}


def load_evaluation_catalog(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "1.0":
        raise ContractError("Unsupported evaluation catalog schema")
    if payload.get("evaluation_class") not in EVALUATION_CLASSES:
        raise ContractError("evaluation_class must be public-calibration or sealed-holdout")
    target = safe_relative_path(str(payload.get("target_path", "")))
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
        before = case.get("before")
        after = case.get("after")
        if not isinstance(before, str) or not before or not isinstance(after, str):
            raise ContractError(f"Evaluation case {case_id} requires text mutation markers")
        if before == after:
            raise ContractError(f"Evaluation case {case_id} does not change the target")
    minimum = float(payload.get("minimum_repair_rate", 0.7))
    if not 0 <= minimum <= 1:
        raise ContractError("minimum_repair_rate must be between zero and one")
    payload["target_path"] = target
    payload["minimum_repair_rate"] = minimum
    return payload


def validate_evaluation_catalog(project_root: Path, catalog: dict[str, Any]) -> dict[str, Any]:
    target = project_root.resolve() / catalog["target_path"]
    if not target.is_file():
        raise ContractError(f"Evaluation target does not exist: {catalog['target_path']}")
    content = target.read_text(encoding="utf-8")
    for case in catalog["cases"]:
        count = content.count(case["before"])
        if count != 1:
            raise ContractError(
                f"Evaluation case {case['id']} expected one canonical marker; found {count}"
            )
    summary = {
        "schema_version": "1.0",
        "catalog_id": catalog["id"],
        "evaluation_class": catalog["evaluation_class"],
        "cases": len(catalog["cases"]),
        "categories": dict(sorted(Counter(item["category"] for item in catalog["cases"]).items())),
        "target_path": catalog["target_path"],
        "minimum_repair_rate": catalog["minimum_repair_rate"],
        "status": "passed",
    }
    summary["content_sha256"] = canonical_hash(summary)
    return summary


def evaluation_work_order(case: dict[str, Any], target_path: str) -> WorkOrder:
    return WorkOrder.from_dict(
        {
            "schema_version": "1.0",
            "id": f"evaluation:carddemo:{case['id']}",
            "title": f"Repair isolated CardDemo {case['category']} regression",
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
                "graph_node_ids": ["workload:carddemo-intcalc"],
            },
            "acceptance": {
                "baseline_first": True,
                "max_attempts": 3,
                "gates": [
                    {
                        "id": "private-carddemo-policy",
                        "command": [sys.executable, "-m", "lightyear_factory.private_benchmark"],
                        "timeout_seconds": 30,
                        "expose_output_to_builder": False,
                    }
                ],
            },
            "policy": {
                "audience": "implementer",
                "allow_network": False,
                "max_files_changed": 1,
                "max_patch_bytes": 8_192,
                "max_changed_lines": 80,
                "max_context_bytes": 200_000,
                "max_file_bytes": 250_000,
                "max_model_calls": 10,
                "max_model_input_bytes": 2_000_000,
                "max_model_output_bytes": 500_000,
                "max_model_tokens": 250_000,
                "max_model_cost_usd": 25.0,
                "max_elapsed_seconds": 1_800,
            },
            "metadata": {
                "evaluation_case_id": case["id"],
                "evaluation_category": case["category"],
            },
        }
    )


def run_model_evaluation(
    project_root: Path,
    output_root: Path,
    catalog_path: Path,
    agents_factory: Callable[[WorkOrder], AgentSet],
) -> dict[str, Any]:
    project_root = project_root.resolve()
    output_root = output_root.resolve()
    catalog = load_evaluation_catalog(catalog_path)
    validation = validate_evaluation_catalog(project_root, catalog)
    target_source = project_root / catalog["target_path"]
    seed_root = output_root / "seed"
    target_seed = seed_root / catalog["target_path"]
    target_seed.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(target_source, target_seed)
    runs_root = output_root / "runs"
    results: list[dict[str, Any]] = []

    for case in catalog["cases"]:
        order = evaluation_work_order(case, catalog["target_path"])

        def prepare(
            workspace: IsolatedWorkspace,
            _: WorkOrder,
            *,
            before: str = case["before"],
            after: str = case["after"],
            case_id: str = case["id"],
        ) -> None:
            path = workspace.resolve(catalog["target_path"])
            content = path.read_text(encoding="utf-8")
            if content.count(before) != 1:
                raise ContractError(f"Mutation marker is not unique for {case_id}")
            path.write_text(content.replace(before, after, 1), encoding="utf-8")

        receipt = FactoryOrchestrator(
            seed_root,
            runs_root,
            agents_factory(order),
            graph_path=project_root / "knowledge" / "graph.snapshot.json.gz",
            evidence_path=project_root / "knowledge" / "evidence" / "source.pack.json.gz",
            prepare_workspace=prepare,
        ).run(order, f"eval-{case['id']}")
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
        repaired = baseline_rejected and receipt["status"] == "passed" and receipt["attempts"] > 0
        false_acceptance = receipt["status"] == "passed" and not baseline_rejected
        intelligence = receipt.get("intelligence", {})
        results.append(
            {
                "case_id": case["id"],
                "category": case["category"],
                "status": receipt["status"],
                "attempts": receipt["attempts"],
                "baseline_rejected": baseline_rejected,
                "autonomously_repaired": repaired,
                "false_acceptance": false_acceptance,
                "model_calls": intelligence.get("calls", 0),
                "input_tokens": intelligence.get("input_tokens", 0),
                "output_tokens": intelligence.get("output_tokens", 0),
                "estimated_cost_usd": intelligence.get("estimated_cost_usd", 0.0),
                "cost_estimate_available": intelligence.get(
                    "cost_estimate_available", False
                ),
                "receipt_sha256": receipt["content_sha256"],
            }
        )

    repaired_count = sum(item["autonomously_repaired"] for item in results)
    false_acceptances = sum(item["false_acceptance"] for item in results)
    baselines_rejected = sum(item["baseline_rejected"] for item in results)
    repair_rate = repaired_count / len(results)
    payload = {
        "schema_version": "1.0",
        "receipt_type": "lightyear-model-workcell-evaluation",
        "evaluation_id": catalog["id"],
        "evaluation_class": catalog["evaluation_class"],
        "catalog_sha256": canonical_hash(catalog),
        "catalog_validation_sha256": validation["content_sha256"],
        "cases": len(results),
        "categories": validation["categories"],
        "baselines_rejected": baselines_rejected,
        "autonomously_repaired": repaired_count,
        "repair_rate": round(repair_rate, 6),
        "minimum_repair_rate": catalog["minimum_repair_rate"],
        "false_acceptances": false_acceptances,
        "status": (
            "passed"
            if baselines_rejected == len(results)
            and false_acceptances == 0
            and repair_rate >= catalog["minimum_repair_rate"]
            else "failed"
        ),
        "results": results,
        "totals": {
            "model_calls": sum(item["model_calls"] for item in results),
            "input_tokens": sum(item["input_tokens"] for item in results),
            "output_tokens": sum(item["output_tokens"] for item in results),
            "estimated_cost_usd": round(
                sum(float(item["estimated_cost_usd"]) for item in results), 8
            ),
            "cost_estimate_available": all(
                item["cost_estimate_available"] for item in results
            ),
        },
        "limitations": [
            "Public calibration cases are not evidence of blind generalization.",
            "Only an externally controlled sealed-holdout catalog can produce holdout evidence.",
            "Synthetic faults do not prove z/OS equivalence.",
        ],
    }
    payload["content_sha256"] = canonical_hash(payload)
    write_json(payload, output_root / "evaluation.receipt.json")
    return payload
