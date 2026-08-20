from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

from lightyear_common.io import write_text as write_deterministic_text

from .agents import DEFAULT_REPAIR_RULES, LocalAgentSet
from .contracts import WorkOrder, canonical_hash, write_json
from .orchestrator import FactoryOrchestrator
from .workspace import IsolatedWorkspace


MUTATIONS = {
    "rounding-mode": ('ROUNDING = "down"', 'ROUNDING = "half-up"'),
    "monthly-divisor": ("MONTHS_PERCENT = 1200", "MONTHS_PERCENT = 100"),
    "default-disclosure": ('DEFAULT_GROUP = "DEFAULT"', 'DEFAULT_GROUP = "STANDARD"'),
    "zero-rate": ("SKIP_ZERO_RATE = True", "SKIP_ZERO_RATE = False"),
    "final-account": ("PRESERVE_FINAL_ACCOUNT = True", "PRESERVE_FINAL_ACCOUNT = False"),
}


def benchmark_work_order(mutation_id: str) -> WorkOrder:
    if mutation_id not in MUTATIONS:
        raise ValueError(f"Unknown factory mutation: {mutation_id}")
    return WorkOrder.from_dict(
        {
            "schema_version": "1.0",
            "id": f"benchmark:intcalc:{mutation_id}",
            "title": f"Repair INTCALC {mutation_id} regression",
            "goal": "Restore source-faithful INTCALC behavior and prove it with private gates.",
            "non_goals": [
                "Do not change the target architecture.",
                "Do not access or modify verifier-private cases.",
            ],
            "scope": {
                "allowed_paths": ["factory/benchmarks/intcalc_candidate.py"],
                "graph_node_ids": ["workload:carddemo-intcalc"],
            },
            "acceptance": {
                "baseline_first": True,
                "max_attempts": 3,
                "gates": [
                    {
                        "id": "private-intcalc-policy",
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
                "max_patch_bytes": 4096,
            },
            "metadata": {"benchmark_mutation_id": mutation_id},
        }
    )


def run_mutation_benchmark(
    project_root: Path,
    output_root: Path,
    mutation_ids: list[str] | None = None,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    output_root = output_root.resolve()
    seed_root = output_root / "seed"
    candidate_source = project_root / "factory" / "benchmarks" / "intcalc_candidate.py"
    candidate_target = seed_root / "factory" / "benchmarks" / "intcalc_candidate.py"
    candidate_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(candidate_source, candidate_target)
    selected = mutation_ids or list(MUTATIONS)
    runs_root = output_root / "runs"
    results = []

    for mutation_id in selected:
        if mutation_id not in MUTATIONS:
            raise ValueError(f"Unknown factory mutation: {mutation_id}")
        original, mutated = MUTATIONS[mutation_id]

        def prepare(
            workspace: IsolatedWorkspace,
            order: WorkOrder,
            *,
            before=original,
            after=mutated,
            prepared_mutation_id=mutation_id,
        ) -> None:
            path = workspace.resolve("factory/benchmarks/intcalc_candidate.py")
            content = path.read_text(encoding="utf-8")
            if content.count(before) != 1:
                raise ValueError(
                    f"Mutation source marker is not unique for {prepared_mutation_id}"
                )
            write_deterministic_text(path, content.replace(before, after, 1))

        receipt = FactoryOrchestrator(
            seed_root,
            runs_root,
            LocalAgentSet(DEFAULT_REPAIR_RULES),
            graph_path=project_root / "knowledge" / "graph.snapshot.json.gz",
            prepare_workspace=prepare,
        ).run(benchmark_work_order(mutation_id), run_id=f"benchmark-{mutation_id}")
        event_path = runs_root / receipt["run_id"] / "events.jsonl"
        events = [
            json.loads(line)
            for line in event_path.read_text(encoding="utf-8").splitlines()
            if line
        ]
        baseline_events = [item for item in events if item["kind"] == "baseline_verified"]
        baseline_status = (
            baseline_events[-1]["payload"].get("status") if baseline_events else "not_run"
        )
        baseline_rejected = baseline_status == "failed"
        autonomously_repaired = (
            baseline_rejected and receipt["status"] == "passed" and receipt["attempts"] > 0
        )
        false_acceptance = receipt["status"] == "passed" and not baseline_rejected
        results.append(
            {
                "mutation_id": mutation_id,
                "run_id": receipt["run_id"],
                "status": receipt["status"],
                "attempts": receipt["attempts"],
                "baseline_status": baseline_status,
                "baseline_rejected": baseline_rejected,
                "autonomously_repaired": autonomously_repaired,
                "false_acceptance": false_acceptance,
                "receipt_sha256": receipt["content_sha256"],
            }
        )

    repaired = sum(item["autonomously_repaired"] for item in results)
    false_acceptances = sum(item["false_acceptance"] for item in results)
    payload = {
        "schema_version": "1.0",
        "benchmark": "lightyear-intcalc-mutation-gauntlet",
        "status": (
            "passed"
            if repaired == len(results) and false_acceptances == 0
            else "failed"
        ),
        "mutations": len(results),
        "autonomously_repaired": repaired,
        "false_acceptances": false_acceptances,
        "results": results,
        "limitations": [
            "This benchmark proves factory mechanics against synthetic faults, not z/OS equivalence.",
            "The local reference builder recognizes only the published mutation family.",
        ],
    }
    payload["content_sha256"] = canonical_hash(payload)
    write_json(payload, output_root / "benchmark.receipt.json")
    return payload
