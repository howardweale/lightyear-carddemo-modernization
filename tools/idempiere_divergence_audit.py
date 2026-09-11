#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from lightyear_common.io import write_json
from lightyear_data.idempiere_divergence import (
    MANIFEST_PATH,
    RECEIPT_PATH,
    build_stage1_artifacts,
    validate_stage1_artifacts,
)


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build or verify the deterministic iDempiere Oracle/PostgreSQL Stage 1 audit evidence."
    )
    parser.add_argument("action", choices=("build", "verify", "verify-source"))
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--source-root", type=Path)
    args = parser.parse_args()
    project_root = args.project_root.resolve()

    if args.action in {"build", "verify-source"} and args.source_root is None:
        parser.error(f"{args.action} requires --source-root")

    if args.action == "build":
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
