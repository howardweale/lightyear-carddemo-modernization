from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from .records import Account, CardXref, CategoryBalance, Disclosure, write_records


def create_demo_inputs(input_dir: Path) -> None:
    input_dir.mkdir(parents=True, exist_ok=True)
    accounts = [
        Account(
            "00000000001", "Y", Decimal("1000.00"), Decimal("5000.00"), Decimal("1000.00"),
            "2020-01-01", "2030-01-01", "2030-01-01", Decimal("25.00"), Decimal("75.00"),
            "3000", "STANDARD  ",
        ),
        Account(
            "00000000002", "Y", Decimal("2000.00"), Decimal("5000.00"), Decimal("1000.00"),
            "2020-01-01", "2030-01-01", "2030-01-01", Decimal("10.00"), Decimal("50.00"),
            "3000", "SPECIAL   ",
        ),
    ]
    xrefs = [
        CardXref("4111111111111111", "000000001", "00000000001"),
        CardXref("4222222222222222", "000000002", "00000000002"),
    ]
    balances = [
        CategoryBalance("00000000001", "01", "0001", Decimal("1200.00")),
        CategoryBalance("00000000001", "01", "0002", Decimal("600.00")),
        CategoryBalance("00000000002", "01", "0001", Decimal("1200.00")),
    ]
    disclosures = [
        Disclosure("STANDARD  ", "01", "0001", Decimal("12.00")),
        Disclosure("STANDARD  ", "01", "0002", Decimal("24.00")),
        Disclosure("DEFAULT   ", "01", "0001", Decimal("6.00")),
    ]
    write_records(input_dir / "acctdata.txt", (item.render() for item in accounts), Account.LENGTH)
    write_records(input_dir / "cardxref.txt", (item.render() for item in xrefs), CardXref.LENGTH)
    write_records(input_dir / "tcatbal.txt", (item.render() for item in balances), CategoryBalance.LENGTH)
    write_records(input_dir / "discgrp.txt", (item.render() for item in disclosures), Disclosure.LENGTH)

