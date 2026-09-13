#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from lightyear_common.io import write_json
from lightyear_data.idempiere_divergence import (
    MANIFEST_PATH,
    RECEIPT_PATH,
    build_stage1_artifacts,
    validate_stage1_artifacts,
)
from lightyear_data.idempiere_comparison import (
    ROOT_PATH as STAGE2_ROOT,
    REPORT_PATH as STAGE2_REPORT,
    build_stage2_artifacts,
    validate_stage2_artifacts,
)
from lightyear_data.idempiere_triage import (
    RECEIPT_PATH as STAGE4_RECEIPT,
    ROOT_PATH as TRIAGE_ROOT,
    WORK_PACKAGE_PATH,
    build_stage3_artifacts,
    run_model_triage,
    validate_stage3_artifacts,
)
from lightyear_factory.providers import OpenAIResponsesProvider


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build or verify bounded iDempiere pairing (MS68), comparison (MS69), and triage calibration (MS70)."
    )
    parser.add_argument("action", choices=("build", "verify", "verify-source", "compare", "verify-comparison", "verify-comparison-source", "triage", "verify-triage", "verify-triage-source", "run-triage"))
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--planner-model", default="gpt-5.6-luna")
    parser.add_argument("--analyst-model", default="gpt-6-astra")
    parser.add_argument("--planner-input-usd-per-million", type=float)
    parser.add_argument("--planner-output-usd-per-million", type=float)
    parser.add_argument("--analyst-input-usd-per-million", type=float)
    parser.add_argument("--analyst-output-usd-per-million", type=float)
    args = parser.parse_args()
    project_root = args.project_root.resolve()

    if args.action in {"build", "verify-source", "compare", "verify-comparison-source", "verify-triage-source", "run-triage"} and args.source_root is None:
        parser.error(f"{args.action} requires --source-root")

    if args.action == "run-triage":
        prices = (
            args.planner_input_usd_per_million,
            args.planner_output_usd_per_million,
            args.analyst_input_usd_per_million,
            args.analyst_output_usd_per_million,
        )
        if args.output is None or any(value is None or value <= 0 for value in prices):
            parser.error("run-triage requires --output and four explicit positive pricing arguments")
        key = os.environ.get("OPENAI_API_KEY", "")
        if not key:
            parser.error("run-triage requires OPENAI_API_KEY")
        planner = OpenAIResponsesProvider(
            key,
            model=args.planner_model,
            input_usd_per_million=prices[0],
            output_usd_per_million=prices[1],
            token_preflight=True,
            max_input_tokens_per_call=60_000,
            max_output_tokens=25_000,
        )
        analyst = OpenAIResponsesProvider(
            key,
            model=args.analyst_model,
            input_usd_per_million=prices[2],
            output_usd_per_million=prices[3],
            token_preflight=True,
            max_input_tokens_per_call=60_000,
            max_output_tokens=25_000,
        )
        output = args.output.resolve()
        payload = run_model_triage(
            project_root, args.source_root.resolve(), planner, analyst
        )
        write_json(output, payload)
        result = {
            "status": "written",
            "model_triage_run": str(output),
            "statistics": payload["statistics"],
            "claims": payload["claims"],
        }
    elif args.action == "triage":
        artifacts = build_stage3_artifacts(project_root)
        for name, payload in artifacts.items():
            write_json(project_root / TRIAGE_ROOT / name, payload)
        result = {
            "status": "written",
            "work_package": str(project_root / WORK_PACKAGE_PATH),
            "receipt": str(project_root / STAGE4_RECEIPT),
            "statistics": artifacts[STAGE4_RECEIPT.name]["statistics"],
            "claims": artifacts[STAGE4_RECEIPT.name]["claims"],
        }
    elif args.action in {"verify-triage", "verify-triage-source"}:
        errors = validate_stage3_artifacts(
            project_root,
            source_root=args.source_root.resolve() if args.source_root else None,
        )
        result = {
            "status": "passed" if not errors else "failed",
            "verification": "source-bound-context-replay" if args.source_root else "committed-integrity-and-accounting-only",
            "errors": errors,
            "audit_complete": False,
            "production_ready": False,
        }
    elif args.action == "compare":
        artifacts = build_stage2_artifacts(project_root, args.source_root.resolve())
        for name, payload in artifacts.items():
            write_json(project_root / STAGE2_ROOT / name, payload)
        result = {"status": "written", "comparison": str(project_root / STAGE2_REPORT), "statistics": artifacts[STAGE2_REPORT.name]["statistics"], "model_calls": 0, "audit_complete": False, "production_ready": False}
    elif args.action in {"verify-comparison", "verify-comparison-source"}:
        errors = validate_stage2_artifacts(project_root, source_root=args.source_root.resolve() if args.source_root else None)
        result = {"status": "passed" if not errors else "failed", "verification": "source-bound-semantic-replay" if args.source_root else "committed-integrity-and-accounting-only", "errors": errors, "audit_complete": False, "production_ready": False}
    elif args.action == "build":
        artifacts = build_stage1_artifacts(project_root, args.source_root.resolve())
        write_json(project_root / MANIFEST_PATH, artifacts["pairing-manifest.json"])
        write_json(project_root / RECEIPT_PATH, artifacts["stage1.receipt.json"])
        result = {
            "status": "written",
            "manifest": str(project_root / MANIFEST_PATH),
            "receipt": str(project_root / RECEIPT_PATH),
            "pairs": artifacts["pairing-manifest.json"]["statistics"]["paired_script_pairs"],
            "pilot_pairs": artifacts["pairing-manifest.json"]["statistics"][
                "order_to_cash_pilot_pairs"
            ],
            "semantic_comparison_complete": False,
            "audit_complete": False,
            "production_ready": False,
        }
    else:
        errors = validate_stage1_artifacts(
            project_root,
            source_root=args.source_root.resolve() if args.source_root else None,
        )
        result = {
            "status": "passed" if not errors else "failed",
            "verification": "source-bound" if args.source_root else "committed-artifacts",
            "errors": errors,
            "semantic_comparison_complete": False,
            "audit_complete": False,
            "production_ready": False,
        }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
