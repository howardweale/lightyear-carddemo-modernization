"""Bounded policy surface for the POSTTRAN portfolio work cell."""

from __future__ import annotations

from decimal import Decimal


POSTTRAN_JOB = "POSTTRAN"
POSTTRAN_PROGRAM = "CBTRN02C"
ACCOUNT_ID_WIDTH = 11
TRANSACTION_ID_WIDTH = 16
TRANSACTION_RECORD_LENGTH = 350
CATEGORY_BALANCE_LENGTH = 50
REJECT_RECORD_LENGTH = 80
APPROVED_STATUS = "00"


def apply_amount(balance: str, amount: str, transaction_type: str) -> Decimal:
    """Debit type 01 increases the account balance; type 02 reverses it."""
    current = Decimal(balance)
    delta = Decimal(amount)
    return current + delta if transaction_type == "01" else current - delta


def should_reject(account_found: bool, card_active: bool, amount: str) -> bool:
    return not account_found or not card_active or Decimal(amount) <= 0
