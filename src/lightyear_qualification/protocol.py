"""Strict observation admission and narrowly scoped representation normalizations."""
from __future__ import annotations

import json
import re
from datetime import date
from decimal import Decimal
from typing import Any


class ObservationError(ValueError):
    pass


def strict_json(text: str) -> Any:
    def pairs(items: list) -> dict:
        result = {}
        for key, value in items:
            if key in result:
                raise ObservationError("duplicate JSON key")
            result[key] = value
        return result

    def invalid_constant(value: str) -> None:
        raise ObservationError("non-finite JSON number")

    try:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=invalid_constant)
    except (ValueError, TypeError, RecursionError) as exc:
        raise ObservationError(str(exc)) from exc


def keys(value: Any, required: set[str]) -> None:
    if not isinstance(value, dict) or set(value) != required:
        raise ObservationError("missing, additional, or malformed fields")


def identifier(value: Any) -> str:
    # No stripping or case folding: these are business identities, not padding.
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value):
        raise ObservationError("unsupported identifier")
    return value


def validate_command(command: Any) -> None:
    if not isinstance(command, dict):
        raise ObservationError("command must be an object")
    kind = command.get("kind")
    if kind == "observe":
        keys(command, {"kind"})
    elif kind == "transfer":
        fields = {"kind", "id", "from", "to", "actor", "amount", "date"}
        keys(command, fields | ({"crash_after_debit"} if "crash_after_debit" in command else set()))
        for field in ("id", "from", "to", "actor"):
            identifier(command[field])
        # Invalid business values are legal test inputs; malformed protocol types are not.
        for field in ("amount", "date"):
            if not isinstance(command[field], str) or len(command[field]) > 64:
                raise ObservationError("amount/date inputs must be bounded strings")
        if "crash_after_debit" in command and type(command["crash_after_debit"]) is not bool:
            raise ObservationError("crash hook requires a boolean")
    elif kind == "concurrent":
        keys(command, {"kind", "operations"})
        operations = command["operations"]
        if not isinstance(operations, list) or not 2 <= len(operations) <= 16:
            raise ObservationError("concurrency requires 2 to 16 operations")
        for operation in operations:
            if not isinstance(operation, dict) or operation.get("kind") != "transfer" or operation.get("crash_after_debit"):
                raise ObservationError("concurrent group supports non-crashing transfers only")
            validate_command(operation)
        if len({op["id"] for op in operations}) != len(operations):
            raise ObservationError("concurrent duplicate-key races are outside this contract")
    else:
        raise ObservationError("unsupported command kind")


def amount(value: Any, decimal: bool) -> int:
    if not decimal:
        if type(value) is not int or not 0 <= value <= 10**12:
            raise ObservationError("invalid integer cents")
        return value
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,11}(\.[0-9]{1,6})?", value):
        raise ObservationError("unsupported decimal representation")
    cents = Decimal(value) * 100
    # Normalize formatting, NEVER round away an actual observed discrepancy.
    if cents != cents.to_integral_value() or not 0 <= cents <= 10**12:
        raise ObservationError("sub-cent or out-of-range observation")
    return int(cents)


def normalize(raw: Any) -> dict:
    keys(raw, {"encoding", "accounts", "operations", "outcomes"})
    if raw["encoding"] not in {"integer-cents-v1", "decimal-journal-v1"}:
        raise ObservationError("unsupported encoding")
    decimal = raw["encoding"] == "decimal-journal-v1"
    money_key = "amount" if decimal else "cents"
    for name in ("accounts", "operations", "outcomes"):
        if not isinstance(raw[name], list) or len(raw[name]) > 10000:
            raise ObservationError("invalid observation collection")
    if not raw["accounts"]:
        raise ObservationError("empty account observation")
    accounts = []
    for row in raw["accounts"]:
        keys(row, {"id", "owner", money_key})
        accounts.append({"id": identifier(row["id"]), "owner": identifier(row["owner"]),
                         "cents": amount(row[money_key], decimal)})
    operations = []
    for row in raw["operations"]:
        keys(row, {"id", "from", "to", money_key, "date"})
        if not isinstance(row["date"], str):
            raise ObservationError("invalid date")
        try:
            if date.fromisoformat(row["date"]).isoformat() != row["date"]:
                raise ValueError("noncanonical date")
        except ValueError as exc:
            raise ObservationError("invalid date") from exc
        operations.append({"id": identifier(row["id"]), "from": identifier(row["from"]),
                           "to": identifier(row["to"]), "cents": amount(row[money_key], decimal), "date": row["date"]})
    outcomes = []
    for row in raw["outcomes"]:
        keys(row, {"id", "status"})
        if row["status"] not in {"applied", "replayed", "conflict", "forbidden", "invalid", "insufficient", "interrupted"}:
            raise ObservationError("unsupported outcome")
        outcomes.append({"id": identifier(row["id"]), "status": row["status"]})
    for rows in (accounts, operations, outcomes):
        if len({r["id"] for r in rows}) != len(rows):
            raise ObservationError("duplicate identity")
    ids = {row["id"] for row in accounts}
    if any(row["from"] not in ids or row["to"] not in ids for row in operations):
        raise ObservationError("unobserved operation account")
    return {"accounts": sorted(accounts, key=lambda x: x["id"]),
            "operations": sorted(operations, key=lambda x: x["id"]),
            "outcomes": sorted(outcomes, key=lambda x: x["id"])}


def compare(expected: dict, raw: Any) -> dict:
    try:
        actual = normalize(raw)
    except (ObservationError, TypeError, KeyError) as exc:
        return {"verdict": "indeterminate", "reason": str(exc), "differences": []}
    # Full account cardinality and identity is an observation prerequisite.
    if {r["id"] for r in actual["accounts"]} != {r["id"] for r in expected["accounts"]}:
        return {"verdict": "indeterminate", "reason": "account observation scope mismatch", "differences": []}
    if {r["id"] for r in actual["outcomes"]} != {r["id"] for r in expected["outcomes"]}:
        return {"verdict": "indeterminate", "reason": "command outcome observation scope mismatch", "differences": []}
    differences = [{"field": field, "expected": expected[field], "actual": actual[field]}
                   for field in ("accounts", "operations", "outcomes") if expected[field] != actual[field]]
    return {"verdict": "failed" if differences else "passed", "reason": None, "differences": differences}
