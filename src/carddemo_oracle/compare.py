from __future__ import annotations

from collections import Counter
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from typing import Any

from lightyear_common.io import write_json

from .records import Account, Transaction, read_records


IGNORED_FIELDS = {"filler"}

NORMALIZATION_RULES = (
    {
        "id": "decimal-canonical-text",
        "scope": "all decimal fields",
        "behavior": "format Decimal values without exponent notation",
    },
    {
        "id": "fixed-width-right-padding",
        "scope": "all text fields",
        "behavior": "ignore right-padding spaces added by fixed-width rendering",
    },
    {
        "id": "copybook-filler",
        "scope": "account.filler and transaction.filler",
        "behavior": "exclude non-business filler bytes",
    },
)


def _normalized(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    return value.rstrip() if isinstance(value, str) else value


def _index_by_key(
    entity: str,
    side: str,
    key_field: str,
    records: list[Any],
) -> tuple[dict[Any, Any], list[dict[str, Any]]]:
    counts = Counter(getattr(item, key_field) for item in records)
    differences = [
        {
            "entity": entity,
            "key": key,
            "side": side,
            "occurrences": count,
            "classification": "duplicate_record",
        }
        for key, count in sorted(counts.items(), key=lambda item: str(item[0]))
        if count > 1
    ]
    indexed: dict[Any, Any] = {}
    for item in records:
        indexed.setdefault(getattr(item, key_field), item)
    return indexed, differences


def _diff_records(entity: str, key_field: str, expected: list[Any], actual: list[Any]) -> list[dict[str, Any]]:
    expected_by_key, differences = _index_by_key(entity, "expected", key_field, expected)
    actual_by_key, actual_duplicates = _index_by_key(entity, "actual", key_field, actual)
    differences.extend(actual_duplicates)
    if len(expected) != len(actual):
        differences.append(
            {
                "entity": entity,
                "expected_count": len(expected),
                "actual_count": len(actual),
                "classification": "record_count_mismatch",
            }
        )
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
    expected_total = len(expected_accounts) + len(expected_txns)
    actual_total = len(actual_accounts) + len(actual_txns)
    if expected_total == 0 and actual_total == 0:
        status = "indeterminate"
        reason_code = "NO_COMPARABLE_RECORDS"
    else:
        status = "passed" if not differences else "failed"
        reason_code = None
    matched_accounts = len(
        {item.account_id for item in expected_accounts}
        & {item.account_id for item in actual_accounts}
    )
    matched_transactions = len(
        {item.transaction_id for item in expected_txns}
        & {item.transaction_id for item in actual_txns}
    )
    report = {
        "schema_version": "1.0",
        "comparison_type": "factorydark-carddemo-intcalc-differential",
        "status": status,
        "reason_code": reason_code,
        "expected_accounts": len(expected_accounts),
        "actual_accounts": len(actual_accounts),
        "expected_transactions": len(expected_txns),
        "actual_transactions": len(actual_txns),
        "compared_accounts": matched_accounts,
        "compared_transactions": matched_transactions,
        "differences": differences,
        "normalizations": [dict(item) for item in NORMALIZATION_RULES],
    }
    report["content_sha256"] = hashlib.sha256(
        json.dumps(report, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return report


def write_comparison(report: dict[str, Any], path: Path) -> None:
    write_json(path, report)
