from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path


def _candidate() -> object:
    workspace = Path(
        os.environ.get("LIGHTYEAR_CICS_VSAM_WORKSPACE")
        or os.environ.get("LIGHTYEAR_FACTORY_WORKSPACE", "")
    ).resolve()
    path = workspace / "factory" / "benchmarks" / "cics_vsam_account_candidate.py"
    if not workspace.is_dir() or workspace not in path.resolve().parents or not path.is_file():
        raise RuntimeError("CICS/VSAM candidate is unavailable")
    spec = importlib.util.spec_from_file_location("lightyear_cics_vsam_candidate", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("CICS/VSAM candidate cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def policy_checks(candidate: object) -> tuple[bool, ...]:
    xref = candidate.KeyedStore(
        "CXACAIX", {"00000000001": {"customer_id": "000000001", "card_number": "4111111111111111"}}
    )
    accounts = candidate.KeyedStore(
        "ACCTDAT", {"00000000001": {"status": "Y", "current_balance": "125.25", "credit_limit": "5000.00"}}
    )
    customers = candidate.KeyedStore("CUSTDAT", {"000000001": {"name": "JANE CUSTOMER"}})
    result = candidate.account_view("00000000001", xref, accounts, customers)
    missing = candidate.account_view(
        "00000000002",
        candidate.KeyedStore("CXACAIX", {}),
        candidate.KeyedStore("ACCTDAT", {}),
        candidate.KeyedStore("CUSTDAT", {}),
    )
    return (
        candidate.TRANSACTION_ID == "CAVW",
        candidate.PROGRAM_ID == "COACTVWC",
        candidate.MAPSET == "COACTVW",
        candidate.MAP == "CACTVWA",
        candidate.ACCOUNT_INPUT_LENGTH == 11,
        candidate.XREF_ACCOUNT_KEY_LENGTH == 11,
        candidate.XREF_ACCOUNT_KEY_OFFSET == 25,
        candidate.ACCOUNT_KEY_LENGTH == 11,
        candidate.CUSTOMER_KEY_LENGTH == 9,
        candidate.READ_ONLY is True,
        result.get("status") == "NORMAL",
        result.get("view", {}).get("customer_name") == "JANE CUSTOMER",
        result.get("mutations") == [],
        [item["resource"] for item in [*xref.trace, *accounts.trace, *customers.trace]]
        == ["CXACAIX", "ACCTDAT", "CUSTDAT"],
        missing.get("status") == "NOT_FOUND",
        missing.get("mutations") == [],
    )


def main() -> int:
    checks = policy_checks(_candidate())
    if all(checks):
        print("CICS/VSAM private account-view gate passed")
        return 0
    print("CICS/VSAM private account-view gate failed", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
