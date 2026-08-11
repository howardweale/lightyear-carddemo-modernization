"""Small executable policy surface used to test the factory loop offline."""

from __future__ import annotations

from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP


ROUNDING = "down"
MONTHS_PERCENT = 1200
DEFAULT_GROUP = "DEFAULT"
SKIP_ZERO_RATE = True
PRESERVE_FINAL_ACCOUNT = True

# Cross-layer modernization facts used by the v0.12 evaluation surface. These values are
# independently asserted by the pinned specification, record codecs, oracle, and JCL mapping.
CATEGORY_BALANCE_LENGTH = 50
DISCLOSURE_LENGTH = 50
CARD_XREF_LENGTH = 50
ACCOUNT_LENGTH = 300
TRANSACTION_LENGTH = 350
ACCOUNT_ID_WIDTH = 11
GROUP_ID_WIDTH = 10
TRANSACTION_ID_WIDTH = 16
AMOUNT_SCALE = 2
TRANSACTION_TYPE = "01"
TRANSACTION_CATEGORY = "0005"
TRANSACTION_SOURCE = "System"
MERCHANT_ID = "000000000"
PROCESSING_DATE_WIDTH = 10
TIMESTAMP_WIDTH = 26
INTCALC_JOB = "INTCALC"
BALANCE_DATASET = "tcatbal.txt"
ACCOUNT_DATASET = "acctdata.txt"


def monthly_interest(balance: str, annual_rate: str) -> Decimal:
    rounding = ROUND_DOWN if ROUNDING == "down" else ROUND_HALF_UP
    return (Decimal(balance) * Decimal(annual_rate) / Decimal(MONTHS_PERCENT)).quantize(
        Decimal("0.01"), rounding=rounding
    )


def disclosure_group(available_groups: set[str], account_group: str) -> str | None:
    if account_group in available_groups:
        return account_group
    return DEFAULT_GROUP if DEFAULT_GROUP in available_groups else None


def emits_transaction(annual_rate: str) -> bool:
    return not (SKIP_ZERO_RATE and Decimal(annual_rate) == 0)


def rewrites_final_account(policy: str) -> bool:
    if policy == "intended":
        return True
    return not PRESERVE_FINAL_ACCOUNT
