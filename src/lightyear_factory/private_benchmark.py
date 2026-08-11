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


def main() -> int:
    candidate = _candidate()
    checks = (
        candidate.monthly_interest("10.01", "5.99") == Decimal("0.04"),
        candidate.monthly_interest("1200.00", "12.00") == Decimal("12.00"),
        candidate.disclosure_group({"DEFAULT", "STANDARD"}, "SPECIAL") == "DEFAULT",
        candidate.disclosure_group({"DEFAULT", "STANDARD"}, "STANDARD") == "STANDARD",
        candidate.emits_transaction("0.00") is False,
        candidate.emits_transaction("1.00") is True,
        candidate.rewrites_final_account("source-faithful") is False,
        candidate.rewrites_final_account("intended") is True,
    )
    if all(checks):
        print("INTCALC private policy gate passed")
        return 0
    print("INTCALC private policy gate failed", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

