from __future__ import annotations

import importlib.util
import os
import sys
from decimal import Decimal
from pathlib import Path


def main() -> int:
    workspace = Path(os.environ.get("LIGHTYEAR_FACTORY_WORKSPACE", "")).resolve()
    path = workspace / "factory/benchmarks/posttran_candidate.py"
    if not workspace.is_dir() or workspace not in path.resolve().parents or not path.is_file():
        raise RuntimeError("POSTTRAN candidate is unavailable")
    spec = importlib.util.spec_from_file_location("posttran_candidate", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("POSTTRAN candidate cannot be loaded")
    candidate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(candidate)
    checks = (
        candidate.POSTTRAN_JOB == "POSTTRAN",
        candidate.POSTTRAN_PROGRAM == "CBTRN02C",
        candidate.ACCOUNT_ID_WIDTH == 11,
        candidate.TRANSACTION_ID_WIDTH == 16,
        candidate.TRANSACTION_RECORD_LENGTH == 350,
        candidate.CATEGORY_BALANCE_LENGTH == 50,
        candidate.REJECT_RECORD_LENGTH == 80,
        candidate.apply_amount("100.00", "25.00", "01") == Decimal("125.00"),
        candidate.apply_amount("100.00", "25.00", "02") == Decimal("75.00"),
        candidate.should_reject(True, True, "25.00") is False,
        candidate.should_reject(False, True, "25.00") is True,
    )
    if all(checks):
        print("POSTTRAN private policy gate passed")
        return 0
    print("POSTTRAN private policy gate failed", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
