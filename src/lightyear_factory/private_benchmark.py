from __future__ import annotations

import importlib.util
import os
import sys
from decimal import Decimal
from pathlib import Path


def _candidate() -> object:
    workspace = Path(os.environ.get("LIGHTYEAR_FACTORY_WORKSPACE", "")).resolve()
    path = workspace / "factory" / "benchmarks" / "intcalc_candidate.py"
    if not workspace.is_dir() or workspace not in path.resolve().parents or not path.is_file():
        raise RuntimeError("Factory candidate is unavailable")
    spec = importlib.util.spec_from_file_location("lightyear_factory_candidate", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Factory candidate cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def policy_checks(candidate: object) -> tuple[bool, ...]:
    return (
        candidate.monthly_interest("10.01", "5.99") == Decimal("0.04"),
        candidate.monthly_interest("1200.00", "12.00") == Decimal("12.00"),
        candidate.disclosure_group({"DEFAULT", "STANDARD"}, "SPECIAL") == "DEFAULT",
        candidate.disclosure_group({"DEFAULT", "STANDARD"}, "STANDARD") == "STANDARD",
        candidate.emits_transaction("0.00") is False,
        candidate.emits_transaction("1.00") is True,
        candidate.rewrites_final_account("source-faithful") is False,
        candidate.rewrites_final_account("intended") is True,
        candidate.CATEGORY_BALANCE_LENGTH == 50,
        candidate.DISCLOSURE_LENGTH == 50,
        candidate.CARD_XREF_LENGTH == 50,
        candidate.ACCOUNT_LENGTH == 300,
        candidate.TRANSACTION_LENGTH == 350,
        candidate.ACCOUNT_ID_WIDTH == 11,
        candidate.GROUP_ID_WIDTH == 10,
        candidate.TRANSACTION_ID_WIDTH == 16,
        candidate.AMOUNT_SCALE == 2,
        candidate.TRANSACTION_TYPE == "01",
        candidate.TRANSACTION_CATEGORY == "0005",
        candidate.TRANSACTION_SOURCE == "System",
        candidate.MERCHANT_ID == "000000000",
        candidate.PROCESSING_DATE_WIDTH == 10,
        candidate.TIMESTAMP_WIDTH == 26,
        candidate.INTCALC_JOB == "INTCALC",
        candidate.BALANCE_DATASET == "tcatbal.txt",
        candidate.ACCOUNT_DATASET == "acctdata.txt",
    )


def main() -> int:
    candidate = _candidate()
    checks = policy_checks(candidate)
    if all(checks):
        print("INTCALC private policy gate passed")
        return 0
    print("INTCALC private policy gate failed", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
