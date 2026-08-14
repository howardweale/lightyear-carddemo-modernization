"""Bounded policy surface for the CREASTMT portfolio work cell."""

from __future__ import annotations


STATEMENT_JOB = "CREASTMT"
STATEMENT_PROGRAM = "CBSTM03A"
STATEMENT_RECORD_LENGTH = 80
ACCOUNT_ID_WIDTH = 11
TRANSACTION_ID_WIDTH = 16
HTML_OUTPUT_ENABLED = True
SORT_BEFORE_RENDER = True


def statement_key(account_id: str, cycle: str) -> str:
    return account_id.zfill(ACCOUNT_ID_WIDTH) + ":" + cycle


def should_render(account_found: bool, customer_found: bool) -> bool:
    return account_found and customer_found
