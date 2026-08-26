"""Independent bounded candidate for the MS #22 mixed PL/I workload."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_DOWN
from typing import Any, Mapping


DEFAULT_POLICY = {
    "fraud_score": "100.00",
    "divisor": "100",
    "rounding": ROUND_DOWN,
    "overwrite_db_fields": True,
    "cobol_program": "CBACT04C",
    "parm_length": 10,
    "parm_date": "2026-08-20",
    "call_on_error": False,
    "write_on_error": False,
}


def execute(
    record: Mapping[str, Any],
    authfrds: Mapping[str, Mapping[str, str]],
    policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    rules = {**DEFAULT_POLICY, **(policy or {})}
    trace: list[str] = []
    calls: list[dict[str, Any]] = []

    required = {
        "card_number": 16,
        "transaction_id": 15,
        "authorization_code": 6,
    }
    invalid = next(
        (
            name
            for name, width in required.items()
            if not isinstance(record.get(name), str) or len(record[name]) != width
        ),
        None,
    )
    if invalid or record.get("fraud_flag") not in {"N", "Y"} or not _decimal_12_2(record.get("approved_amount")):
        if rules["call_on_error"]:
            calls.append(_call(rules))
        if rules["write_on_error"]:
            trace.append("WRITE_AUTHOUT")
        return _failure("INPUT_ERROR", "record-contract", trace, calls)

    trace.append("READ_AUTHIN")
    transaction_id = record["transaction_id"]
    trace.append("SELECT_AUTHFRDS")
    row = authfrds.get(transaction_id)
    if row is None:
        if rules["call_on_error"]:
            calls.append(_call(rules))
        if rules["write_on_error"]:
            trace.append("WRITE_AUTHOUT")
        return _failure("SQL_NOT_FOUND", transaction_id, trace, calls)

    amount = Decimal(str(record["approved_amount"]))
    fraud = str(record["fraud_flag"])
    if rules["overwrite_db_fields"]:
        amount = Decimal(row["approved_amount"])
        fraud = row["fraud_flag"]

    trace.append("CALC_RISK")
    if fraud == "Y":
        score = Decimal(str(rules["fraud_score"]))
    else:
        score = (amount / Decimal(str(rules["divisor"]))).quantize(
            Decimal("0.01"), rounding=rules["rounding"]
        )
    call = _call(rules)
    calls.append(call)
    trace.extend(("CALL_CBACT04C", "WRITE_AUTHOUT"))
    output = {
        "card_number": record["card_number"],
        "transaction_id": transaction_id,
        "transaction_id_fixed_16": transaction_id.ljust(16),
        "authorization_code": record["authorization_code"],
        "approved_amount": f"{amount:.2f}",
        "fraud_flag": fraud,
    }
    return {
        "status": "NORMAL",
        "error": None,
        "authorization_record": output,
        "risk_score": f"{score:.2f}",
        "cobol_calls": calls,
        "trace": trace,
    }


def _call(policy: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "program": policy["cobol_program"],
        "calling_convention": "OPTIONS(COBOL)",
        "parm_length": policy["parm_length"],
        "parm_date": policy["parm_date"],
    }


def _failure(status: str, error: str, trace: list[str], calls: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "status": status,
        "error": error,
        "authorization_record": None,
        "risk_score": None,
        "cobol_calls": calls,
        "trace": trace,
    }


def _decimal_12_2(value: Any) -> bool:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return False
    return number.is_finite() and number.as_tuple().exponent >= -2 and len(number.as_tuple().digits) <= 12
