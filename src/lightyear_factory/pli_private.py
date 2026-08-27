from __future__ import annotations

import os
import sys
import types
from pathlib import Path


def _candidate() -> object:
    workspace = Path(os.environ.get("LIGHTYEAR_FACTORY_WORKSPACE", "")).resolve()
    path = workspace / "factory" / "benchmarks" / "pli_authorization_candidate.py"
    if not workspace.is_dir() or workspace not in path.resolve().parents or not path.is_file():
        raise RuntimeError("ACCTPL1 candidate is unavailable")
    candidate = types.ModuleType("acctpl1_candidate")
    candidate.__file__ = str(path)
    exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), candidate.__dict__)
    return candidate


def policy_checks(candidate: object) -> tuple[bool, ...]:
    record = {
        "card_number": "4000000000000001",
        "transaction_id": "TXN000000000001",
        "authorization_code": "A00001",
        "approved_amount": "12.34",
        "fraud_flag": "N",
    }
    authfrds = {
        "TXN000000000001": {"approved_amount": "250.99", "fraud_flag": "N"}
    }
    result = candidate.execute(record, authfrds)
    policy = candidate.DEFAULT_POLICY
    return (
        policy["fraud_score"] == "100.00",
        policy["divisor"] == "100",
        str(policy["rounding"]) == "ROUND_DOWN",
        policy["overwrite_db_fields"] is True,
        policy["cobol_program"] == "CBACT04C",
        policy["parm_length"] == 10,
        policy["call_on_error"] is False,
        policy["write_on_error"] is False,
        result["status"] == "NORMAL",
        result["authorization_record"]["approved_amount"] == "250.99",
        result["risk_score"] == "2.50",
        result["cobol_calls"][0]["program"] == "CBACT04C",
        result["cobol_calls"][0]["calling_convention"] == "OPTIONS(COBOL)",
        result["trace"] == [
            "READ_AUTHIN",
            "SELECT_AUTHFRDS",
            "CALC_RISK",
            "CALL_CBACT04C",
            "WRITE_AUTHOUT",
        ],
    )


def main() -> int:
    checks = policy_checks(_candidate())
    if all(checks):
        print("ACCTPL1 private policy gate passed")
        return 0
    print("ACCTPL1 private policy gate failed", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
