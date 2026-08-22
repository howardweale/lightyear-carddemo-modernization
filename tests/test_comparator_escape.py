from __future__ import annotations

import json
import hashlib
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

from carddemo_oracle.cli import main as oracle_cli
from carddemo_oracle.compare import (
    NORMALIZATION_RULES,
    compare_directories,
    validate_normalization_ledger,
)
from carddemo_oracle.demo import create_demo_inputs
from carddemo_oracle.oracle import run_directory
from carddemo_oracle.records import Account, Transaction, read_records, write_records


PROCESSING_DATE = "2022071800"
TIMESTAMP = "2022-07-18-00.00.00.000000"


class ComparatorEscapeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.input = self.root / "input"
        self.expected = self.root / "expected"
        self.actual = self.root / "actual"
        create_demo_inputs(self.input)
        run_directory(self.input, self.expected, PROCESSING_DATE, TIMESTAMP)
        run_directory(self.input, self.actual, PROCESSING_DATE, TIMESTAMP)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _transactions(self, directory: Path) -> list[str]:
        return read_records(directory / "transactions.txt", Transaction.LENGTH)

    def _accounts(self, directory: Path) -> list[str]:
        return read_records(directory / "acctdata.txt", Account.LENGTH)

    def test_identical_nonempty_outputs_pass(self) -> None:
        report = compare_directories(self.expected, self.actual)
        self.assertEqual("passed", report["status"])
        self.assertIsNone(report["reason_code"])
        self.assertEqual([], report["differences"])
        self.assertGreater(report["compared_accounts"] + report["compared_transactions"], 0)
        expected_hash = hashlib.sha256(
            json.dumps(
                {key: value for key, value in report.items() if key != "content_sha256"},
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        self.assertEqual(expected_hash, report["content_sha256"])

    def test_duplicate_actual_transaction_is_rejected(self) -> None:
        records = self._transactions(self.actual)
        write_records(self.actual / "transactions.txt", [*records, records[0]], Transaction.LENGTH)
        report = compare_directories(self.expected, self.actual)
        self.assertEqual("failed", report["status"])
        self.assertEqual(3, report["expected_transactions"])
        self.assertEqual(4, report["actual_transactions"])
        classifications = {item["classification"] for item in report["differences"]}
        self.assertIn("duplicate_record", classifications)
        self.assertIn("record_count_mismatch", classifications)

    def test_duplicate_diagnostics_compare_the_first_observed_record(self) -> None:
        records = self._transactions(self.actual)
        first = Transaction.parse(records[0])
        later_duplicate = replace(first, amount=first.amount + Decimal("1.00")).render()
        write_records(
            self.actual / "transactions.txt",
            [*records, later_duplicate],
            Transaction.LENGTH,
        )
        report = compare_directories(self.expected, self.actual)
        self.assertEqual("failed", report["status"])
        self.assertTrue(
            any(item["classification"] == "duplicate_record" for item in report["differences"])
        )
        self.assertFalse(
            any(
                item["classification"] == "field_difference"
                and item.get("key") == first.transaction_id
                for item in report["differences"]
            ),
            "Duplicate diagnostics must retain the first observed record for field comparison",
        )

    def test_duplicate_expected_account_is_rejected(self) -> None:
        records = self._accounts(self.expected)
        write_records(self.expected / "acctdata.txt", [*records, records[0]], Account.LENGTH)
        report = compare_directories(self.expected, self.actual)
        self.assertEqual("failed", report["status"])
        duplicate = next(
            item for item in report["differences"] if item["classification"] == "duplicate_record"
        )
        self.assertEqual("expected", duplicate["side"])
        self.assertEqual(2, duplicate["occurrences"])

    def test_missing_record_is_rejected_independently_of_keys(self) -> None:
        records = self._transactions(self.actual)
        write_records(self.actual / "transactions.txt", records[:-1], Transaction.LENGTH)
        report = compare_directories(self.expected, self.actual)
        self.assertEqual("failed", report["status"])
        classifications = {item["classification"] for item in report["differences"]}
        self.assertIn("record_count_mismatch", classifications)
        self.assertIn("missing_record", classifications)

    def test_amount_and_sign_mutations_are_rejected(self) -> None:
        records = self._transactions(self.actual)
        first = Transaction.parse(records[0])
        records[0] = replace(first, amount=-first.amount).render()
        write_records(self.actual / "transactions.txt", records, Transaction.LENGTH)
        report = compare_directories(self.expected, self.actual)
        self.assertEqual("failed", report["status"])
        self.assertTrue(any(item.get("field") == "amount" for item in report["differences"]))

    def test_differing_or_blank_timestamp_is_rejected(self) -> None:
        records = self._transactions(self.actual)
        first = Transaction.parse(records[0])
        records[0] = replace(first, original_timestamp="", processing_timestamp="2023-01-01-12.00.00.000000").render()
        write_records(self.actual / "transactions.txt", records, Transaction.LENGTH)
        report = compare_directories(self.expected, self.actual)
        fields = {item.get("field") for item in report["differences"]}
        self.assertEqual("failed", report["status"])
        self.assertIn("original_timestamp", fields)
        self.assertIn("processing_timestamp", fields)

    def test_truncated_business_text_is_rejected(self) -> None:
        records = self._transactions(self.actual)
        first = Transaction.parse(records[0])
        description = first.description.rstrip()
        records[0] = replace(first, description=description[:-1]).render()
        write_records(self.actual / "transactions.txt", records, Transaction.LENGTH)
        report = compare_directories(self.expected, self.actual)
        self.assertEqual("failed", report["status"])
        self.assertTrue(any(item.get("field") == "description" for item in report["differences"]))

    def test_nonbusiness_filler_is_the_only_excluded_dataclass_field(self) -> None:
        records = self._transactions(self.actual)
        first = Transaction.parse(records[0])
        records[0] = replace(first, filler="X" * 20).render()
        write_records(self.actual / "transactions.txt", records, Transaction.LENGTH)
        self.assertEqual("passed", compare_directories(self.expected, self.actual)["status"])

    def test_two_empty_outputs_are_indeterminate_and_exit_two(self) -> None:
        expected = self.root / "empty-expected"
        actual = self.root / "empty-actual"
        for directory in (expected, actual):
            directory.mkdir()
            (directory / "acctdata.txt").write_text("", encoding="ascii")
            (directory / "transactions.txt").write_text("", encoding="ascii")
        report_path = self.root / "empty-report.json"
        with redirect_stdout(io.StringIO()):
            exit_code = oracle_cli(
                [
                    "compare",
                    "--expected",
                    str(expected),
                    "--actual",
                    str(actual),
                    "--report",
                    str(report_path),
                ]
            )
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(2, exit_code)
        self.assertEqual("indeterminate", report["status"])
        self.assertEqual("NO_COMPARABLE_RECORDS", report["reason_code"])

    def test_one_sided_empty_output_fails_as_a_difference(self) -> None:
        empty = self.root / "empty"
        empty.mkdir()
        (empty / "acctdata.txt").write_text("", encoding="ascii")
        (empty / "transactions.txt").write_text("", encoding="ascii")
        report = compare_directories(self.expected, empty)
        self.assertEqual("failed", report["status"])
        self.assertIsNone(report["reason_code"])

    def test_normalization_ledger_matches_runtime_rules(self) -> None:
        root = Path(__file__).resolve().parents[1]
        ledger_path = root / "spec/comparison-normalizations.json"
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        self.assertEqual([item["id"] for item in NORMALIZATION_RULES], [item["id"] for item in ledger["rules"]])
        self.assertTrue(all(item["reason"] and item["owner"] and item["review_after"] for item in ledger["rules"]))
        self.assertEqual(
            "passed",
            validate_normalization_ledger(
                ledger_path, as_of=date(2026, 8, 22)
            )["status"],
        )
        schema = json.loads((root / "spec/comparison-report.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(
            ["passed", "failed", "indeterminate"], schema["properties"]["status"]["enum"]
        )

    def test_expired_normalization_review_fails_closed(self) -> None:
        root = Path(__file__).resolve().parents[1]
        ledger = json.loads(
            (root / "spec/comparison-normalizations.json").read_text(encoding="utf-8")
        )
        ledger["rules"][0]["review_after"] = "2026-08-22"
        path = self.root / "expired-normalizations.json"
        path.write_text(json.dumps(ledger), encoding="utf-8")
        report = validate_normalization_ledger(path, as_of=date(2026, 8, 22))
        self.assertEqual("failed", report["status"])
        self.assertIn(
            "NORMALIZATION_REVIEW_EXPIRED:decimal-canonical-text:2026-08-22",
            report["errors"],
        )

    def test_normalization_scope_or_behavior_drift_fails_closed(self) -> None:
        root = Path(__file__).resolve().parents[1]
        ledger = json.loads(
            (root / "spec/comparison-normalizations.json").read_text(encoding="utf-8")
        )
        ledger["rules"][1]["scope"] = "some text fields"
        path = self.root / "drifted-normalizations.json"
        path.write_text(json.dumps(ledger), encoding="utf-8")
        report = validate_normalization_ledger(path, as_of=date(2026, 8, 22))
        self.assertEqual("failed", report["status"])
        self.assertIn(
            "NORMALIZATION_RUNTIME_MISMATCH:fixed-width-right-padding:scope",
            report["errors"],
        )


if __name__ == "__main__":
    unittest.main()
