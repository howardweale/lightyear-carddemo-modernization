from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lightyear_data.cloudbank_edge_ai import RECEIPT_TYPE as MS64_RECEIPT_TYPE
from lightyear_data.cloudbank_oracle_equivalence import RECEIPT_TYPE as MS61_RECEIPT_TYPE
from lightyear_data.cloudbank_whole_application_equivalence import (
    MINIMUM_START_COUNTS,
    NORMALIZED_MARKER,
    OBSERVATION_SHA256,
    OUTPUT_ROOT,
    RECEIPT_TYPE,
    SCENARIOS,
    SCENARIO_IDS,
    SERVICES,
    acceptance_contract,
    build_artifacts,
    compatibility_ledger,
    execute_equivalence,
    execution_plan,
    journey_contract,
    lane_contract,
    readiness_receipt,
    validate_artifacts,
    validate_execution_receipt,
    validate_lane_observation,
)
from lightyear_data.contracts import content_hash, sign


ROOT = Path(__file__).resolve().parents[1]
KEY = "unit-test-cloudbank-whole-application-key"
HEX_A = "a" * 64
HEX_B = "b" * 64
HEX_C = "c" * 64
HEX_D = "d" * 64
PAIR_ID = "ms66-unit-comparison"


def ms61_receipt() -> dict[str, object]:
    return {"receipt_type": MS61_RECEIPT_TYPE, "content_sha256": HEX_A,
            "oracle_image_id_sha256": HEX_C, "postgresql_image_id_sha256": HEX_D}


def ms64_receipt() -> dict[str, object]:
    return {"receipt_type": MS64_RECEIPT_TYPE, "content_sha256": HEX_B,
            "postgresql_image_id_sha256": HEX_D}


def observation(lane: str, *, pair_id: str = PAIR_ID) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "observation_type": "lightyear-cloudbank-ms66-lane-observation",
        "release": "0.66.0",
        "lane": lane,
        "bindings": {
            "source_ms61_receipt_sha256": HEX_A,
            "source_ms64_receipt_sha256": HEX_B,
            "oracle_image_id_sha256": HEX_C,
            "postgresql_image_id_sha256": HEX_D,
            "lane_contract_sha256": lane_contract()["content_sha256"],
            "journey_contract_sha256": journey_contract()["content_sha256"],
            "comparison_run_id": pair_id,
        },
        "database_engine": lane,
        "services": [
            {"service": service, "executable_sha256": f"{index:064x}",
             "start_count": MINIMUM_START_COUNTS[service], "final_status": "ready"}
            for index, service in enumerate(SERVICES, start=1)
        ],
        "scenarios": [
            {"id": identifier, "normalized_result": result,
             "evidence_sha256": f"{index:064x}"}
            for index, (identifier, result) in enumerate(SCENARIOS, start=100)
        ],
        "normalized_marker": NORMALIZED_MARKER,
        "normalized_observation_sha256": OBSERVATION_SHA256,
        "synthetic_data_only": True,
        "production_environment": False,
        "credentials_persisted": False,
        "raw_output_persisted": False,
    }
    return sign(payload, KEY, f"unit-{lane}-observer")


def materialize(_project: Path, _source: Path, output: Path) -> Path:
    for service in SERVICES:
        path = output / service
        path.mkdir(parents=True, exist_ok=True)
        (path / "pom.xml").write_text("<project/>", encoding="utf-8")
    return output


class CloudBankWholeApplicationEquivalenceTests(unittest.TestCase):
    def test_committed_artifacts_are_deterministic_and_readiness_is_fail_closed(self) -> None:
        self.assertEqual([], validate_artifacts(ROOT))
        for name, expected in build_artifacts().items():
            actual = json.loads((ROOT / OUTPUT_ROOT / name).read_text(encoding="utf-8"))
            self.assertEqual(expected, actual)
        receipt = readiness_receipt()
        self.assertFalse(receipt["all_eight_services_observed_in_both_lanes"])
        self.assertFalse(receipt["bounded_whole_application_equivalent"])
        self.assertFalse(receipt["whole_application_equivalent"])
        self.assertFalse(receipt["production_ready"])

    def test_contract_requires_all_services_same_scenarios_and_restarts(self) -> None:
        lanes = lane_contract()
        self.assertEqual(list(SERVICES), lanes["services"])
        self.assertEqual(set(SERVICES), set(lanes["required_service_state"]))
        self.assertTrue(all(
            state["minimum_start_count"] >= 2
            for state in lanes["required_service_state"].values()
        ))
        journeys = journey_contract()
        self.assertEqual(18, journeys["scenario_count"])
        self.assertEqual(SCENARIO_IDS, execution_plan()["required_scenarios"])
        self.assertEqual(OBSERVATION_SHA256, journeys["normalized_observation_sha256"])

    def test_ledger_distinguishes_business_equivalence_from_internal_identity(self) -> None:
        ledger = compatibility_ledger()
        entries = {item["capability"]: item for item in ledger["entries"]}
        self.assertEqual("intentional-change", entries["oracle-aq-versus-postgresql-queue"]["classification"])
        self.assertEqual("not-qualified", entries["real-credit-decision"]["classification"])
        self.assertEqual("not-qualified", entries["production-platform"]["classification"])
        self.assertTrue(ledger["whole_application_equivalence_eligible"])
        self.assertFalse(ledger["exact_internal_implementation_equivalent"])

    def test_signed_lane_observations_are_exact_and_safe(self) -> None:
        for lane in ("oracle", "postgresql"):
            self.assertEqual([], validate_lane_observation(
                observation(lane), KEY, lane, ms61_sha256=HEX_A, ms64_sha256=HEX_B,
                oracle_image=HEX_C, postgres_image=HEX_D, comparison_run_id=PAIR_ID,
            ))
        damaged = observation("oracle")
        damaged["services"][0]["start_count"] = 1
        damaged = sign(damaged, KEY, "unit-oracle-observer")
        errors = validate_lane_observation(
            damaged, KEY, "oracle", ms61_sha256=HEX_A, ms64_sha256=HEX_B,
            oracle_image=HEX_C, postgres_image=HEX_D, comparison_run_id=PAIR_ID,
        )
        self.assertIn("cloudbank-whole-application-oracle-services-invalid", errors)

    @patch("lightyear_data.cloudbank_whole_application_equivalence.validate_ms64_receipt", return_value=[])
    @patch("lightyear_data.cloudbank_whole_application_equivalence.validate_ms61_receipt", return_value=[])
    @patch("lightyear_data.cloudbank_whole_application_equivalence.validate_edge_source", return_value=[])
    def test_passing_pair_closes_only_bounded_equivalence(
        self, _source: object, _ms61: object, _ms64: object,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            receipt = execute_equivalence(
                ROOT, ROOT, ms61_receipt(), ms64_receipt(), observation("oracle"),
                observation("postgresql"), Path(directory) / "evidence", KEY, "unit-test",
                "ms66-unit-run", materializer=materialize,
            )
            self.assertEqual(RECEIPT_TYPE, receipt["receipt_type"])
            self.assertTrue(receipt["all_eight_services_observed_in_both_lanes"])
            self.assertTrue(receipt["bounded_whole_application_equivalent"])
            self.assertTrue(receipt["whole_application_equivalent"])
            self.assertFalse(receipt["exact_internal_implementation_equivalent"])
            self.assertFalse(receipt["migration_complete"])
            self.assertFalse(receipt["production_deployed"])
            self.assertFalse(receipt["production_ready"])
            self.assertEqual([], validate_execution_receipt(receipt, KEY, ROOT))
            tampered = copy.deepcopy(receipt)
            tampered["production_ready"] = True
            errors = validate_execution_receipt(tampered, KEY, ROOT)
            self.assertIn("cloudbank-whole-application-receipt-signature-invalid", errors)
            self.assertIn("cloudbank-whole-application-receipt-claims-invalid", errors)
            extra = copy.deepcopy(receipt)
            extra["unexpected"] = True
            self.assertIn(
                "cloudbank-whole-application-receipt-fields-invalid",
                validate_execution_receipt(extra, KEY, ROOT),
            )

    @patch("lightyear_data.cloudbank_whole_application_equivalence.validate_ms64_receipt", return_value=[])
    @patch("lightyear_data.cloudbank_whole_application_equivalence.validate_ms61_receipt", return_value=[])
    @patch("lightyear_data.cloudbank_whole_application_equivalence.validate_edge_source", return_value=[])
    def test_misbound_or_failed_lane_is_rejected_without_raw_evidence(
        self, _source: object, _ms61: object, _ms64: object,
    ) -> None:
        target = observation("postgresql", pair_id="wrong-pair")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "evidence"
            with self.assertRaisesRegex(ValueError, "acceptance-failed"):
                execute_equivalence(
                    ROOT, ROOT, ms61_receipt(), ms64_receipt(), observation("oracle"), target,
                    output, KEY, "unit-test", materializer=materialize,
                )
            failure = json.loads((output / "cloudbank-whole-application-equivalence.failure.json").read_text())
            self.assertFalse(failure["credentials_persisted"])
            self.assertFalse(failure["raw_output_persisted"])
            self.assertNotIn("services", failure)
            self.assertNotIn("scenarios", failure)

    @patch("lightyear_data.cloudbank_whole_application_equivalence.validate_ms64_receipt", return_value=[])
    @patch("lightyear_data.cloudbank_whole_application_equivalence.validate_ms61_receipt", return_value=[])
    @patch("lightyear_data.cloudbank_whole_application_equivalence.validate_edge_source", return_value=[])
    def test_image_chain_fresh_output_and_signer_fail_closed(
        self, _source: object, _ms61: object, _ms64: object,
    ) -> None:
        wrong = ms64_receipt()
        wrong["postgresql_image_id_sha256"] = "e" * 64
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "image-chain-invalid"):
                execute_equivalence(
                    ROOT, ROOT, ms61_receipt(), wrong, observation("oracle"),
                    observation("postgresql"), Path(directory), KEY, "unit",
                )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "evidence"
            output.mkdir()
            (output / "existing").write_text("x", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "fresh-output-required"):
                execute_equivalence(
                    ROOT, ROOT, ms61_receipt(), ms64_receipt(), observation("oracle"),
                    observation("postgresql"), output, KEY, "unit", materializer=materialize,
                )
        with self.assertRaisesRegex(ValueError, "signer-required"):
            execute_equivalence(
                ROOT, ROOT, ms61_receipt(), ms64_receipt(), observation("oracle"),
                observation("postgresql"), ROOT.parent / "unused", KEY, " ",
            )

    def test_launchers_schemas_and_acceptance_exist(self) -> None:
        for relative in (
            "cloudbank-whole-application-equivalence.sh",
            "cloudbank-whole-application-equivalence.ps1",
            "tools/cloudbank_whole_application_equivalence.py",
            "reference-estates/cloudbank/schema/whole-application-equivalence-readiness.schema.json",
            "reference-estates/cloudbank/schema/whole-application-equivalence-lane-observation.schema.json",
            "reference-estates/cloudbank/schema/whole-application-equivalence-execution-receipt.schema.json",
        ):
            self.assertTrue((ROOT / relative).is_file(), relative)
        acceptance = acceptance_contract()
        self.assertEqual(18, len(acceptance["required_scenarios"]))
        self.assertEqual(list(SERVICES), acceptance["required_services"])
        self.assertTrue(acceptance["eligible_claim"]["bounded_whole_application_equivalent"])
        self.assertIn("Invoke-FactoryDarkPython", (ROOT / "cloudbank-whole-application-equivalence.ps1").read_text())


if __name__ == "__main__":
    unittest.main()
