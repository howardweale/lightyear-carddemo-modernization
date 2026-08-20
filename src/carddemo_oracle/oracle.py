from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from lightyear_common.io import write_json

from .records import (
    Account,
    CardXref,
    CategoryBalance,
    Disclosure,
    Transaction,
    cobol_truncate,
    read_records,
    write_records,
)


class OracleExecutionError(RuntimeError):
    pass


@dataclass(frozen=True)
class RunResult:
    accounts: list[Account]
    transactions: list[Transaction]
    observations: dict[str, Any]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _decimal_json(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, dict):
        return {key: _decimal_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_decimal_json(item) for item in value]
    return value


def _load(path: Path, record_type: type[Any]) -> list[Any]:
    return [record_type.parse(raw) for raw in read_records(path, record_type.LENGTH)]


def run_intcalc(
    balances: list[CategoryBalance],
    disclosures: list[Disclosure],
    xrefs: list[CardXref],
    accounts: list[Account],
    processing_date: str,
    timestamp: str,
    final_account_policy: str = "source-faithful",
) -> RunResult:
    if len(processing_date) != 10:
        raise OracleExecutionError("processing_date must be exactly 10 characters")
    if len(timestamp) != 26:
        raise OracleExecutionError("timestamp must be exactly 26 characters")
    if final_account_policy not in {"source-faithful", "intended"}:
        raise OracleExecutionError("final_account_policy must be source-faithful or intended")

    account_order = [account.account_id for account in accounts]
    account_by_id = {account.account_id: account for account in accounts}
    xref_by_account = {xref.account_id: xref for xref in xrefs}
    disclosure_by_key = {
        (item.group_id, item.type_code, item.category_code): item for item in disclosures
    }

    current_account_id: str | None = None
    current_account: Account | None = None
    current_xref: CardXref | None = None
    total_interest = Decimal("0.00")
    generated: list[Transaction] = []
    used_default_rate = 0
    zero_rate_rows = 0
    account_updates = 0

    def apply_previous_account() -> None:
        nonlocal account_updates
        if current_account is None:
            return
        account_by_id[current_account.account_id] = current_account.with_interest(total_interest)
        account_updates += 1

    for balance in balances:
        if balance.account_id != current_account_id:
            if current_account_id is not None:
                apply_previous_account()
            current_account_id = balance.account_id
            total_interest = Decimal("0.00")
            try:
                current_account = account_by_id[balance.account_id]
            except KeyError as exc:
                raise OracleExecutionError(f"ACCOUNT NOT FOUND: {balance.account_id}") from exc
            try:
                current_xref = xref_by_account[balance.account_id]
            except KeyError as exc:
                raise OracleExecutionError(f"XREF NOT FOUND: {balance.account_id}") from exc

        assert current_account is not None and current_xref is not None
        key = (current_account.group_id, balance.type_code, balance.category_code)
        disclosure = disclosure_by_key.get(key)
        if disclosure is None:
            default_key = ("DEFAULT".ljust(10), balance.type_code, balance.category_code)
            disclosure = disclosure_by_key.get(default_key)
            used_default_rate += 1
        if disclosure is None:
            raise OracleExecutionError(
                f"DEFAULT DISCLOSURE MISSING: type={balance.type_code} category={balance.category_code}"
            )
        if disclosure.annual_rate == 0:
            zero_rate_rows += 1
            continue

        monthly = cobol_truncate(balance.balance * disclosure.annual_rate / Decimal("1200"), 2)
        total_interest = cobol_truncate(total_interest + monthly, 2)
        suffix = len(generated) + 1
        generated.append(
            Transaction(
                transaction_id=f"{processing_date}{suffix:06d}",
                type_code="01",
                category_code="0005",
                source="System",
                description=f"Int. for a/c {current_account.account_id}",
                amount=monthly,
                merchant_id="000000000",
                merchant_name="",
                merchant_city="",
                merchant_zip="",
                card_number=current_xref.card_number,
                original_timestamp=timestamp,
                processing_timestamp=timestamp,
            )
        )

    # CBACT04C sets EOF during the final read after the outer IF was already
    # evaluated. Its ELSE is therefore not entered, and the final account is
    # not rewritten. "source-faithful" preserves that source-level behavior.
    if final_account_policy == "intended" and current_account_id is not None:
        apply_previous_account()

    ordered_accounts = [account_by_id[account_id] for account_id in account_order]
    observations = {
        "balance_rows": len(balances),
        "account_updates": account_updates,
        "transactions_created": len(generated),
        "default_rates_used": used_default_rate,
        "zero_rate_rows": zero_rate_rows,
        "final_account_policy": final_account_policy,
        "known_behavior": (
            "final account is not rewritten" if final_account_policy == "source-faithful"
            else "final account is rewritten"
        ),
    }
    return RunResult(ordered_accounts, generated, observations)


def run_directory(
    input_dir: Path,
    output_dir: Path,
    processing_date: str,
    timestamp: str,
    final_account_policy: str = "source-faithful",
) -> dict[str, Any]:
    inputs = {
        "tcatbal": input_dir / "tcatbal.txt",
        "discgrp": input_dir / "discgrp.txt",
        "cardxref": input_dir / "cardxref.txt",
        "acctdata": input_dir / "acctdata.txt",
    }
    missing = [str(path) for path in inputs.values() if not path.exists()]
    if missing:
        raise OracleExecutionError("Missing input files: " + ", ".join(missing))

    result = run_intcalc(
        balances=_load(inputs["tcatbal"], CategoryBalance),
        disclosures=_load(inputs["discgrp"], Disclosure),
        xrefs=_load(inputs["cardxref"], CardXref),
        accounts=_load(inputs["acctdata"], Account),
        processing_date=processing_date,
        timestamp=timestamp,
        final_account_policy=final_account_policy,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    account_path = output_dir / "acctdata.txt"
    transaction_path = output_dir / "transactions.txt"
    canonical_path = output_dir / "canonical.json"
    receipt_path = output_dir / "receipt.json"
    write_records(account_path, (record.render() for record in result.accounts), Account.LENGTH)
    write_records(transaction_path, (record.render() for record in result.transactions), Transaction.LENGTH)

    canonical = {
        "accounts": [_decimal_json(asdict(account)) for account in result.accounts],
        "transactions": [_decimal_json(asdict(txn)) for txn in result.transactions],
        "observations": result.observations,
    }
    write_json(canonical_path, canonical)

    receipt = {
        "oracle": "carddemo-intcalc-source-faithful-local",
        "oracle_version": "0.1.0",
        "upstream_commit": "59cc6c2fd7ebd7ef7925cad552a01a4b8b6e4d5e",
        "processing_date": processing_date,
        "timestamp": timestamp,
        "limitations": [
            "Derived from source and copybooks; not captured from a running z/OS system",
            "Models the CBACT04C path needed by the supplied and synthetic fixtures",
            "Does not emulate VSAM locking, JES, LE runtime, or EBCDIC collation",
        ],
        "inputs": {name: {"sha256": _sha256(path)} for name, path in inputs.items()},
        "outputs": {
            "accounts": {"sha256": _sha256(account_path), "records": len(result.accounts)},
            "transactions": {"sha256": _sha256(transaction_path), "records": len(result.transactions)},
            "canonical": {"sha256": _sha256(canonical_path)},
        },
        "observations": result.observations,
    }
    write_json(receipt_path, receipt)
    return receipt
