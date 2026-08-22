from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from carddemo_oracle.compare import compare_directories
from carddemo_oracle.demo import create_demo_inputs
from carddemo_oracle.oracle import run_directory, run_intcalc
from carddemo_oracle.records import (
    Account,
    CardXref,
    CategoryBalance,
    Disclosure,
    Transaction,
    cobol_truncate,
    decode_zoned,
    encode_zoned,
    read_records,
    write_records,
)


PROCESSING_DATE = "2022071800"
TIMESTAMP = "2022-07-18-00.00.00.000000"


class ZonedDecimalTests(unittest.TestCase):
    def test_positive_round_trip(self) -> None:
        encoded = encode_zoned(Decimal("123.45"), 7, 2)
        self.assertEqual("001234E", encoded)
        self.assertEqual(Decimal("123.45"), decode_zoned(encoded, 2))

    def test_negative_round_trip(self) -> None:
        encoded = encode_zoned(Decimal("-123.45"), 7, 2)
        self.assertEqual("001234N", encoded)
        self.assertEqual(Decimal("-123.45"), decode_zoned(encoded, 2))

    def test_cobol_truncation_is_toward_zero(self) -> None:
        self.assertEqual(Decimal("1.23"), cobol_truncate(Decimal("1.239"), 2))
        self.assertEqual(Decimal("-1.23"), cobol_truncate(Decimal("-1.239"), 2))


class OracleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        create_demo_inputs(self.root / "input")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_demo_matches_interest_and_default_rate_rules(self) -> None:
        receipt = run_directory(
            self.root / "input",
            self.root / "output",
            PROCESSING_DATE,
            TIMESTAMP,
        )
        accounts = [
            Account.parse(record)
            for record in read_records(self.root / "output" / "acctdata.txt", Account.LENGTH)
        ]
        transactions = [
            Transaction.parse(record)
            for record in read_records(self.root / "output" / "transactions.txt", Transaction.LENGTH)
        ]
        self.assertEqual(Decimal("1024.00"), accounts[0].current_balance)
        self.assertEqual(Decimal("0.00"), accounts[0].current_cycle_credit)
        self.assertEqual(Decimal("0.00"), accounts[0].current_cycle_debit)
        self.assertEqual(Decimal("2000.00"), accounts[1].current_balance)
        self.assertEqual([Decimal("12.00"), Decimal("12.00"), Decimal("6.00")], [t.amount for t in transactions])
        self.assertEqual(1, receipt["observations"]["default_rates_used"])

    def test_source_faithful_policy_preserves_final_account_non_rewrite(self) -> None:
        run_directory(
            self.root / "input",
            self.root / "legacy",
            PROCESSING_DATE,
            TIMESTAMP,
            "source-faithful",
        )
        run_directory(
            self.root / "input",
            self.root / "intended",
            PROCESSING_DATE,
            TIMESTAMP,
            "intended",
        )
        legacy_last = Account.parse(read_records(self.root / "legacy" / "acctdata.txt", Account.LENGTH)[-1])
        intended_last = Account.parse(read_records(self.root / "intended" / "acctdata.txt", Account.LENGTH)[-1])
        self.assertEqual(Decimal("2000.00"), legacy_last.current_balance)
        self.assertEqual(Decimal("2006.00"), intended_last.current_balance)

    def test_zero_rate_emits_no_transaction(self) -> None:
        account = Account.parse(read_records(self.root / "input" / "acctdata.txt", Account.LENGTH)[0])
        xref = CardXref.parse(read_records(self.root / "input" / "cardxref.txt", CardXref.LENGTH)[0])
        result = run_intcalc(
            [CategoryBalance(account.account_id, "01", "0001", Decimal("1200.00"))],
            [Disclosure(account.group_id, "01", "0001", Decimal("0.00"))],
            [xref],
            [account],
            PROCESSING_DATE,
            TIMESTAMP,
        )
        self.assertEqual([], result.transactions)
        self.assertEqual(1, result.observations["zero_rate_rows"])

    def test_comparator_requires_same_injected_timestamp(self) -> None:
        expected = self.root / "expected"
        actual = self.root / "actual"
        run_directory(self.root / "input", expected, PROCESSING_DATE, TIMESTAMP)
        run_directory(self.root / "input", actual, PROCESSING_DATE, "2023-01-01-12.00.00.000000")
        report = compare_directories(expected, actual)
        self.assertEqual("failed", report["status"])
        fields = {item.get("field") for item in report["differences"]}
        self.assertIn("original_timestamp", fields)
        self.assertIn("processing_timestamp", fields)

    def test_comparator_detects_amount_mutation_with_same_clock(self) -> None:
        expected = self.root / "expected"
        actual = self.root / "actual"
        run_directory(self.root / "input", expected, PROCESSING_DATE, TIMESTAMP)
        run_directory(self.root / "input", actual, PROCESSING_DATE, TIMESTAMP)
        self.assertEqual("passed", compare_directories(expected, actual)["status"])
        records = read_records(actual / "transactions.txt", Transaction.LENGTH)
        first = Transaction.parse(records[0])
        records[0] = replace(first, amount=Decimal("12.01")).render()
        write_records(actual / "transactions.txt", records, Transaction.LENGTH)
        report = compare_directories(expected, actual)
        self.assertEqual("failed", report["status"])
        self.assertTrue(any(item.get("field") == "amount" for item in report["differences"]))

    def test_receipt_is_machine_readable_and_hashed(self) -> None:
        run_directory(self.root / "input", self.root / "output", PROCESSING_DATE, TIMESTAMP)
        receipt = json.loads((self.root / "output" / "receipt.json").read_text(encoding="utf-8"))
        self.assertEqual("carddemo-intcalc-source-faithful-local", receipt["oracle"])
        self.assertEqual(64, len(receipt["outputs"]["canonical"]["sha256"]))


if __name__ == "__main__":
    unittest.main()
