from __future__ import annotations

from decimal import Decimal
from typing import Any

from .contracts import SCHEMA_VERSION, canonical_bytes, seal


def packed_decimal(value: str, precision: int, scale: int) -> str:
    number = Decimal(value)
    digits = f"{abs(int(number * (10 ** scale))):0{precision}d}"
    nibbles = digits + ("D" if number < 0 else "C")
    if len(nibbles) % 2:
        nibbles = "0" + nibbles
    return bytes.fromhex(nibbles).hex().upper()


def zoned_decimal(value: str, precision: int, scale: int) -> str:
    number = Decimal(value)
    digits = f"{abs(int(number * (10 ** scale))):0{precision}d}"
    raw = bytearray((0xF0 | int(char)) for char in digits)
    raw[-1] = (0xD0 if number < 0 else 0xC0) | int(digits[-1])
    return raw.hex().upper()


def ebcdic(value: str, width: int) -> str:
    return value.ljust(width)[:width].encode("cp037").hex().upper()


def fixture_catalog() -> dict[str, Any]:
    rows = [
        {
            "CARD_NUM": "4000000000000001", "AUTH_TS": "2026-08-20T10:15:30.123456",
            "AUTH_TYPE": "SALE", "CARD_EXPIRY_DATE": "2808", "MESSAGE_TYPE": "010000",
            "MESSAGE_SOURCE": "POS001", "AUTH_ID_CODE": "A10001", "AUTH_RESP_CODE": "00",
            "AUTH_RESP_REASON": "APRV", "PROCESSING_CODE": "000000",
            "TRANSACTION_AMT": "125.50", "APPROVED_AMT": "125.50",
            "MERCHANT_CATAGORY_CODE": "5411", "ACQR_COUNTRY_CODE": "840",
            "POS_ENTRY_MODE": 5, "MERCHANT_ID": "M00000000000001",
            "MERCHANT_NAME": "FactoryDark Market", "MERCHANT_CITY": "SAN FRANCISCO",
            "MERCHANT_STATE": "CA", "MERCHANT_ZIP": "941050000",
            "TRANSACTION_ID": "TX0000000000001", "MATCH_STATUS": "M", "AUTH_FRAUD": "N",
            "FRAUD_RPT_DATE": None, "ACCT_ID": "10000000001", "CUST_ID": "100000001",
        },
        {
            "CARD_NUM": "4000000000000002", "AUTH_TS": "2026-08-20T10:16:31.000001",
            "AUTH_TYPE": "RFND", "CARD_EXPIRY_DATE": "2712", "MESSAGE_TYPE": "010000",
            "MESSAGE_SOURCE": "WEB001", "AUTH_ID_CODE": "A10002", "AUTH_RESP_CODE": "05",
            "AUTH_RESP_REASON": "DECL", "PROCESSING_CODE": "200000",
            "TRANSACTION_AMT": "-9.99", "APPROVED_AMT": "0.00",
            "MERCHANT_CATAGORY_CODE": "5999", "ACQR_COUNTRY_CODE": "036",
            "POS_ENTRY_MODE": 81, "MERCHANT_ID": "M00000000000002",
            "MERCHANT_NAME": "Null Name Test", "MERCHANT_CITY": "MELBOURNE",
            "MERCHANT_STATE": "VI", "MERCHANT_ZIP": "300000000",
            "TRANSACTION_ID": "TX0000000000002", "MATCH_STATUS": "U", "AUTH_FRAUD": "Y",
            "FRAUD_RPT_DATE": "2026-08-21", "ACCT_ID": "10000000002", "CUST_ID": None,
        },
    ]
    encodings = [
        {
            "row": index + 1,
            "card_num_ebcdic_hex": ebcdic(row["CARD_NUM"], 16),
            "merchant_name_ebcdic_fixed_22_hex": ebcdic(row["MERCHANT_NAME"], 22),
            "transaction_amount_packed_decimal_hex": packed_decimal(row["TRANSACTION_AMT"], 12, 2),
            "transaction_amount_zoned_decimal_hex": zoned_decimal(row["TRANSACTION_AMT"], 12, 2),
            "null_columns": sorted(key for key, value in row.items() if value is None),
        }
        for index, row in enumerate(rows)
    ]
    row_checksums = sorted(__import__("hashlib").sha256(canonical_bytes(row)).hexdigest() for row in rows)
    return seal({
        "schema_version": SCHEMA_VERSION, "fixture_type": "db2-postgresql-boundary-fixtures",
        "table": "CARDDEMO.AUTHFRDS", "rows": rows, "source_encoding_evidence": encodings,
        "expected_results": {
            "row_count": 2, "fraud_authorization_count": 1,
            "total_approved_amount": "125.50", "rollback_row_count": 2,
            "row_checksums": row_checksums,
        },
        "coverage": ["ebcdic-cp037", "packed-decimal", "zoned-decimal", "date", "null", "fixed-width"],
    })
