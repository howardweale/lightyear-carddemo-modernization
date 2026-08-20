"""Bounded local candidate for the CAVW CICS/VSAM account-view behavior.

This is deliberately a semantic replacement surface, not a CICS or VSAM emulator.
The private gate owns the acceptance behavior; the candidate may only read the
three keyed stores supplied to ``account_view``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


TRANSACTION_ID = "CAVW"
PROGRAM_ID = "COACTVWC"
MAPSET = "COACTVW"
MAP = "CACTVWA"
ACCOUNT_INPUT_LENGTH = 11
XREF_ACCOUNT_KEY_LENGTH = 11
XREF_ACCOUNT_KEY_OFFSET = 25
ACCOUNT_KEY_LENGTH = 11
CUSTOMER_KEY_LENGTH = 9
READ_ONLY = True


@dataclass
class KeyedStore:
    name: str
    records: dict[str, dict[str, str]]
    trace: list[dict[str, str]] = field(default_factory=list)

    def read(self, key: str) -> dict[str, str] | None:
        self.trace.append({"operation": "READ", "resource": self.name, "key": key})
        value = self.records.get(key)
        return dict(value) if value is not None else None


def account_view(
    account_id: str,
    xref_by_account: KeyedStore,
    accounts: KeyedStore,
    customers: KeyedStore,
) -> dict[str, Any]:
    if len(account_id) != ACCOUNT_INPUT_LENGTH or not account_id.isdigit():
        return _error("INVALID_ACCOUNT", "Account number must contain 11 digits")

    xref = xref_by_account.read(account_id)
    if xref is None:
        return _error("NOT_FOUND", "Account not found in cross-reference")
    account = accounts.read(account_id)
    if account is None:
        return _error("NOT_FOUND", "Account not found in account master")
    customer_id = xref["customer_id"]
    customer = customers.read(customer_id)
    if customer is None:
        return _error("NOT_FOUND", "Customer not found in customer master")

    return {
        "status": "NORMAL",
        "transaction": TRANSACTION_ID,
        "program": PROGRAM_ID,
        "mapset": MAPSET,
        "map": MAP,
        "view": {
            "account_id": account_id,
            "card_number": xref["card_number"],
            "customer_id": customer_id,
            "account_status": account["status"],
            "current_balance": account["current_balance"],
            "credit_limit": account["credit_limit"],
            "customer_name": customer["name"],
        },
        "mutations": [],
    }


def _error(code: str, message: str) -> dict[str, Any]:
    return {
        "status": code,
        "transaction": TRANSACTION_ID,
        "program": PROGRAM_ID,
        "mapset": MAPSET,
        "map": MAP,
        "message": message,
        "mutations": [],
    }
