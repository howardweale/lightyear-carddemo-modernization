from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from .records import Account, Transaction, read_records


IGNORED_FIELDS = {"filler"}
IGNORED_TRANSACTION_FIELDS = IGNORED_FIELDS | {"original_timestamp", "processing_timestamp"}


def _normalized(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    return value.rstrip() if isinstance(value, str) else value


def _diff_records(entity: str, key_field: str, expected: list[Any], actual: list[Any]) -> list[dict[str, Any]]:
    expected_by_key = {getattr(item, key_field): item for item in expected}
    actual_by_key = {getattr(item, key_field): item for item in actual}
    differences: list[dict[str, Any]] = []
    for key in sorted(set(expected_by_key) | set(actual_by_key)):
        if key not in expected_by_key:
            differences.append({"entity": entity, "key": key, "classification": "unexpected_record"})
            continue
        if key not in actual_by_key:
            differences.append({"entity": entity, "key": key, "classification": "missing_record"})
            continue
        expected_item = expected_by_key[key]
        actual_item = actual_by_key[key]
        for field in expected_item.__dataclass_fields__:
            if field in IGNORED_FIELDS:
                continue
            if entity == "transaction" and field in IGNORED_TRANSACTION_FIELDS:
                continue
            left = _normalized(getattr(expected_item, field))
            right = _normalized(getattr(actual_item, field))
            if left != right:
                differences.append(
                    {
                        "entity": entity,
                        "key": key,
                        "field": field,
                        "expected": left,
                        "actual": right,
                        "classification": "field_difference",
                    }
                )
    return differences


def compare_directories(expected_dir: Path, actual_dir: Path) -> dict[str, Any]:
    expected_accounts = [Account.parse(item) for item in read_records(expected_dir / "acctdata.txt", Account.LENGTH)]
    actual_accounts = [Account.parse(item) for item in read_records(actual_dir / "acctdata.txt", Account.LENGTH)]
    expected_txns = [Transaction.parse(item) for item in read_records(expected_dir / "transactions.txt", Transaction.LENGTH)]
    actual_txns = [Transaction.parse(item) for item in read_records(actual_dir / "transactions.txt", Transaction.LENGTH)]
    differences = _diff_records("account", "account_id", expected_accounts, actual_accounts)
    differences.extend(_diff_records("transaction", "transaction_id", expected_txns, actual_txns))
    return {
        "status": "passed" if not differences else "failed",
        "expected_accounts": len(expected_accounts),
        "actual_accounts": len(actual_accounts),
        "expected_transactions": len(expected_txns),
        "actual_transactions": len(actual_txns),
        "differences": differences,
    }


def write_comparison(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
