from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal, ROUND_DOWN
from pathlib import Path
from typing import Iterable


POSITIVE_OVERPUNCH = {str(i): ch for i, ch in enumerate("{ABCDEFGHI")}
NEGATIVE_OVERPUNCH = {str(i): ch for i, ch in enumerate("}JKLMNOPQR")}
OVERPUNCH_TO_SIGNED_DIGIT = {
    **{ch: (1, digit) for digit, ch in POSITIVE_OVERPUNCH.items()},
    **{ch: (-1, digit) for digit, ch in NEGATIVE_OVERPUNCH.items()},
}


class RecordError(ValueError):
    """Raised when a CardDemo fixed-width record is malformed."""


def cobol_truncate(value: Decimal, scale: int) -> Decimal:
    quantum = Decimal(1).scaleb(-scale)
    return value.quantize(quantum, rounding=ROUND_DOWN)


def decode_zoned(text: str, scale: int) -> Decimal:
    if not text:
        raise RecordError("Empty zoned-decimal value")
    last = text[-1]
    if last in OVERPUNCH_TO_SIGNED_DIGIT:
        sign, digit = OVERPUNCH_TO_SIGNED_DIGIT[last]
        digits = text[:-1] + digit
    elif last.isdigit():
        sign, digits = 1, text
    else:
        raise RecordError(f"Invalid zoned-decimal overpunch: {last!r}")
    if not digits.isdigit():
        raise RecordError(f"Invalid zoned-decimal digits: {text!r}")
    return Decimal(sign * int(digits)).scaleb(-scale)


def encode_zoned(value: Decimal, width: int, scale: int) -> str:
    normalized = cobol_truncate(value, scale)
    sign_map = NEGATIVE_OVERPUNCH if normalized < 0 else POSITIVE_OVERPUNCH
    scaled = int(abs(normalized).scaleb(scale))
    digits = f"{scaled:0{width}d}"
    if len(digits) > width:
        raise RecordError(f"{value} overflows PIC S9({width - scale})V9({scale})")
    return digits[:-1] + sign_map[digits[-1]]


def read_records(path: Path, expected_length: int) -> list[str]:
    records: list[str] = []
    with path.open("r", encoding="ascii", newline=None) as handle:
        for line_number, raw in enumerate(handle, start=1):
            record = raw.rstrip("\r\n")
            if len(record) > expected_length:
                raise RecordError(
                    f"{path}:{line_number}: length {len(record)} exceeds {expected_length}"
                )
            records.append(record.ljust(expected_length))
    return records


def write_records(path: Path, records: Iterable[str], expected_length: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="ascii", newline="\n") as handle:
        for number, record in enumerate(records, start=1):
            if len(record) != expected_length:
                raise RecordError(
                    f"Record {number} for {path} has length {len(record)}; expected {expected_length}"
                )
            handle.write(record + "\n")


@dataclass(frozen=True)
class CategoryBalance:
    account_id: str
    type_code: str
    category_code: str
    balance: Decimal
    filler: str = " " * 22

    LENGTH = 50

    @classmethod
    def parse(cls, record: str) -> "CategoryBalance":
        return cls(record[0:11], record[11:13], record[13:17], decode_zoned(record[17:28], 2), record[28:50])

    def render(self) -> str:
        return (
            self.account_id.rjust(11, "0")[:11]
            + self.type_code.ljust(2)[:2]
            + self.category_code.rjust(4, "0")[-4:]
            + encode_zoned(self.balance, 11, 2)
            + self.filler.ljust(22)[:22]
        )


@dataclass(frozen=True)
class Disclosure:
    group_id: str
    type_code: str
    category_code: str
    annual_rate: Decimal
    filler: str = " " * 28

    LENGTH = 50

    @classmethod
    def parse(cls, record: str) -> "Disclosure":
        return cls(record[0:10], record[10:12], record[12:16], decode_zoned(record[16:22], 2), record[22:50])

    def render(self) -> str:
        return (
            self.group_id.ljust(10)[:10]
            + self.type_code.ljust(2)[:2]
            + self.category_code.rjust(4, "0")[-4:]
            + encode_zoned(self.annual_rate, 6, 2)
            + self.filler.ljust(28)[:28]
        )


@dataclass(frozen=True)
class CardXref:
    card_number: str
    customer_id: str
    account_id: str
    filler: str = " " * 14

    LENGTH = 50

    @classmethod
    def parse(cls, record: str) -> "CardXref":
        return cls(record[0:16], record[16:25], record[25:36], record[36:50])

    def render(self) -> str:
        return (
            self.card_number.ljust(16)[:16]
            + self.customer_id.rjust(9, "0")[-9:]
            + self.account_id.rjust(11, "0")[-11:]
            + self.filler.ljust(14)[:14]
        )


@dataclass(frozen=True)
class Account:
    account_id: str
    active_status: str
    current_balance: Decimal
    credit_limit: Decimal
    cash_credit_limit: Decimal
    open_date: str
    expiration_date: str
    reissue_date: str
    current_cycle_credit: Decimal
    current_cycle_debit: Decimal
    address_zip: str
    group_id: str
    filler: str = " " * 178

    LENGTH = 300

    @classmethod
    def parse(cls, record: str) -> "Account":
        return cls(
            account_id=record[0:11],
            active_status=record[11:12],
            current_balance=decode_zoned(record[12:24], 2),
            credit_limit=decode_zoned(record[24:36], 2),
            cash_credit_limit=decode_zoned(record[36:48], 2),
            open_date=record[48:58],
            expiration_date=record[58:68],
            reissue_date=record[68:78],
            current_cycle_credit=decode_zoned(record[78:90], 2),
            current_cycle_debit=decode_zoned(record[90:102], 2),
            address_zip=record[102:112],
            group_id=record[112:122],
            filler=record[122:300],
        )

    def with_interest(self, interest: Decimal) -> "Account":
        return replace(
            self,
            current_balance=cobol_truncate(self.current_balance + interest, 2),
            current_cycle_credit=Decimal("0.00"),
            current_cycle_debit=Decimal("0.00"),
        )

    def render(self) -> str:
        return "".join(
            [
                self.account_id.rjust(11, "0")[-11:],
                self.active_status[:1],
                encode_zoned(self.current_balance, 12, 2),
                encode_zoned(self.credit_limit, 12, 2),
                encode_zoned(self.cash_credit_limit, 12, 2),
                self.open_date.ljust(10)[:10],
                self.expiration_date.ljust(10)[:10],
                self.reissue_date.ljust(10)[:10],
                encode_zoned(self.current_cycle_credit, 12, 2),
                encode_zoned(self.current_cycle_debit, 12, 2),
                self.address_zip.ljust(10)[:10],
                self.group_id.ljust(10)[:10],
                self.filler.ljust(178)[:178],
            ]
        )


@dataclass(frozen=True)
class Transaction:
    transaction_id: str
    type_code: str
    category_code: str
    source: str
    description: str
    amount: Decimal
    merchant_id: str
    merchant_name: str
    merchant_city: str
    merchant_zip: str
    card_number: str
    original_timestamp: str
    processing_timestamp: str
    filler: str = " " * 20

    LENGTH = 350

    @classmethod
    def parse(cls, record: str) -> "Transaction":
        return cls(
            transaction_id=record[0:16],
            type_code=record[16:18],
            category_code=record[18:22],
            source=record[22:32],
            description=record[32:132],
            amount=decode_zoned(record[132:143], 2),
            merchant_id=record[143:152],
            merchant_name=record[152:202],
            merchant_city=record[202:252],
            merchant_zip=record[252:262],
            card_number=record[262:278],
            original_timestamp=record[278:304],
            processing_timestamp=record[304:330],
            filler=record[330:350],
        )

    def render(self) -> str:
        return "".join(
            [
                self.transaction_id.ljust(16)[:16],
                self.type_code.ljust(2)[:2],
                self.category_code.rjust(4, "0")[-4:],
                self.source.ljust(10)[:10],
                self.description.ljust(100)[:100],
                encode_zoned(self.amount, 11, 2),
                self.merchant_id.rjust(9, "0")[-9:],
                self.merchant_name.ljust(50)[:50],
                self.merchant_city.ljust(50)[:50],
                self.merchant_zip.ljust(10)[:10],
                self.card_number.ljust(16)[:16],
                self.original_timestamp.ljust(26)[:26],
                self.processing_timestamp.ljust(26)[:26],
                self.filler.ljust(20)[:20],
            ]
        )

