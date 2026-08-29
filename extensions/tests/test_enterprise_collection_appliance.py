from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from lightyear_common.io import write_json
from lightyear_extensions.appliance import (
    ApplianceError,
    EnterpriseFixtureTransport,
    EnterpriseHttpTransport,
    build_appliance_evidence,
    run_appliance,
    run_fault_laboratory,
    validate_appliance_evidence,
    validate_appliance_profile,
)
from lightyear_extensions.campaign import load_profile
from lightyear_extensions.contracts import canonical_hash
from lightyear_knowledge_graph.model import load_graph


ROOT = Path(__file__).resolve().parents[2]
APPLIANCE_PROFILE = ROOT / "extensions/adapters/enterprise-appliance.profile.json"
CAMPAIGN_PROFILE = ROOT / "extensions/adapters/mainframe-access.profile.json"
RESPONSES = ROOT / "extensions/adapters/fixtures/enterprise-appliance.simulated.responses.json"
FAULTS = ROOT / "extensions/adapters/fixtures/enterprise-appliance.faults.json"
CANONICAL = ROOT / "extensions/adapters/appliance"
GRAPH = load_graph(ROOT / "knowledge/graph.snapshot.json.gz")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def reseal(payload: dict) -> dict:
    payload["content_sha256"] = canonical_hash(payload, {"content_sha256"})
    return payload


class EnterpriseCollectionApplianceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.appliance = load(APPLIANCE_PROFILE)
        cls.campaign = load_profile(CAMPAIGN_PROFILE)
        cls.responses = load(RESPONSES)
        cls.faults = load(FAULTS)

    def build(self, output: Path) -> dict:
        return build_appliance_evidence(
            self.appliance,
            self.campaign,
            GRAPH,
            self.responses,
            self.faults,
            output,
        )

    def test_committed_appliance_is_deterministic_and_valid(self) -> None:
        self.assertEqual(
            [],
            validate_appliance_evidence(
                self.appliance, self.campaign, GRAPH, CANONICAL
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            rebuilt = self.build(output)
            for name in (
                "appliance.receipt.json",
                "checkpoint.json",
                "fault-lab.receipt.json",
                "lightyear.cics-cmci.capture.json",
                "lightyear.db2-zos-catalog.capture.json",
                "lightyear.zosmf-jobs.capture.json",
            ):
                self.assertEqual((CANONICAL / name).read_bytes(), (output / name).read_bytes(), name)
        self.assertEqual(load(CANONICAL / "appliance.receipt.json"), rebuilt)

    def test_receipt_proves_retry_pagination_resume_and_retention(self) -> None:
        receipt = load(CANONICAL / "appliance.receipt.json")
        self.assertEqual("passed", receipt["status"])
        self.assertTrue(receipt["enterprise_mechanism_ready"])
        self.assertTrue(all(receipt["checks"].values()), receipt["checks"])
        self.assertEqual(3, receipt["operations"]["adapters"])
        self.assertEqual(4, receipt["operations"]["pages"])
        self.assertEqual(2, receipt["operations"]["retries"])
        self.assertEqual(1, receipt["operations"]["resume_count"])
        self.assertEqual([100, 200], receipt["operations"]["backoff_schedule_ms"])
        self.assertFalse(receipt["retention"]["raw_bodies_retained"])
        self.assertFalse(receipt["retention"]["automatic_purge_executed"])
        self.assertFalse(receipt["live_observed"])
        self.assertFalse(receipt["production_ready"])
        self.assertFalse(receipt["mainframe_equivalent"])

    def test_all_eight_fault_classes_are_detected(self) -> None:
        receipt = run_fault_laboratory(self.faults, self.appliance)
        self.assertEqual("passed", receipt["status"])
        self.assertEqual(8, receipt["scenario_count"])
        self.assertTrue(receipt["all_expected_faults_detected"])
        self.assertTrue(all(item["detected"] for item in receipt["results"]))
        self.assertFalse(receipt["credential_material_retained"])

    def test_profile_is_content_addressed_and_contains_no_credentials(self) -> None:
        self.assertEqual([], validate_appliance_profile(self.appliance, self.campaign))
        self.assertEqual(
            self.appliance["content_sha256"],
            canonical_hash(self.appliance, {"content_sha256"}),
        )
        serialized = json.dumps(self.appliance).lower()
        for key in ("password", "token", "authorization", "secret", "private_key"):
            self.assertNotIn(f'"{key}"', serialized)
        self.assertEqual(
            {
                "bearer-env",
                "mtls-bearer-env",
                "externally-issued-oauth-bearer-env",
            },
            set(self.appliance["authentication"]["accepted_modes"]),
        )

    def test_unbounded_or_foreign_profile_fails_closed(self) -> None:
        changed = copy.deepcopy(self.appliance)
        changed["retry"]["max_attempts"] = 100
        changed = reseal(changed)
        self.assertIn(
            "enterprise retry policy is invalid",
            validate_appliance_profile(changed, self.campaign),
        )
        foreign = copy.deepcopy(self.appliance)
        foreign["campaign_profile_sha256"] = "0" * 64
        foreign = reseal(foreign)
        self.assertIn(
            "enterprise appliance profile targets a different campaign profile",
            validate_appliance_profile(foreign, self.campaign),
        )

    def test_checkpoint_tamper_fails_even_when_outer_hash_is_recomputed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            self.build(output)
            checkpoint = load(output / "checkpoint.json")
            checkpoint["total_pages"] += 1
            write_json(output / "checkpoint.json", reseal(checkpoint))
            errors = validate_appliance_evidence(
                self.appliance, self.campaign, GRAPH, output
            )
        self.assertTrue(any("checkpoint-summary-invalid" in error for error in errors), errors)

    def test_receipt_cannot_promote_simulated_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            self.build(output)
            receipt = load(output / "appliance.receipt.json")
            receipt["live_observed"] = True
            receipt["production_ready"] = True
            write_json(output / "appliance.receipt.json", reseal(receipt))
            errors = validate_appliance_evidence(
                self.appliance, self.campaign, GRAPH, output
            )
        self.assertIn("enterprise appliance receipt differs from bound evidence", errors)

    def test_live_operator_path_is_signed_resumable_and_never_production_ready(self) -> None:
        key = b"independent-customer-evidence-key-32-bytes"
        fault_receipt = run_fault_laboratory(self.faults, self.appliance)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            write_json(output / "fault-lab.receipt.json", fault_receipt)
            receipt = run_appliance(
                self.appliance,
                self.campaign,
                GRAPH,
                EnterpriseFixtureTransport(self.responses),
                output,
                collected_at=self.responses["collected_at"],
                evidence_class="live",
                signing_key=key,
                key_id="customer-evidence-key",
                fault_receipt=fault_receipt,
                sleeper=lambda _: None,
            )
            errors = validate_appliance_evidence(
                self.appliance,
                self.campaign,
                GRAPH,
                output,
                trusted_keys={"customer-evidence-key": key},
            )
        self.assertEqual([], errors)
        self.assertEqual("live", receipt["evidence_class"])
        self.assertTrue(receipt["live_observed"])
        self.assertTrue(receipt["enterprise_mechanism_ready"])
        self.assertFalse(receipt["production_ready"])
        self.assertFalse(receipt["mainframe_equivalent"])

    def test_exhausted_network_retry_leaves_a_resumable_checkpoint(self) -> None:
        class ExhaustedTransport:
            def get(self, path: str, accepted_types: tuple[str, ...]) -> object:
                raise ApplianceError("dns-or-network", retryable=True)

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            with self.assertRaisesRegex(ApplianceError, "dns-or-network"):
                run_appliance(
                    self.appliance,
                    self.campaign,
                    GRAPH,
                    ExhaustedTransport(),  # type: ignore[arg-type]
                    output,
                    collected_at=self.responses["collected_at"],
                    sleeper=lambda _: None,
                )
            checkpoint = load(output / "checkpoint.json")
        self.assertEqual("interrupted", checkpoint["status"])
        self.assertEqual(0, checkpoint["total_pages"])
        self.assertFalse(checkpoint["production_ready"])

    def test_fault_catalog_tamper_is_rejected(self) -> None:
        changed = copy.deepcopy(self.faults)
        changed["scenarios"][0]["expected"] = "silently ignored"
        with self.assertRaisesRegex(ApplianceError, "fault-catalog-content-hash-invalid"):
            run_fault_laboratory(changed, self.appliance)

    def test_http_transport_requires_https_and_mtls_material(self) -> None:
        with self.assertRaisesRegex(ApplianceError, "credential-free-https"):
            EnterpriseHttpTransport(
                "http://mainframe.example",
                "credential",
                auth_mode="bearer-env",
                timeout_seconds=15,
                max_response_bytes=65536,
            )
        with self.assertRaisesRegex(ApplianceError, "mtls-certificate-and-key-required"):
            EnterpriseHttpTransport(
                "https://mainframe.example",
                "credential",
                auth_mode="mtls-bearer-env",
                timeout_seconds=15,
                max_response_bytes=65536,
            )

    def test_transport_errors_do_not_disclose_credentials_or_remote_details(self) -> None:
        transport = EnterpriseHttpTransport(
            "https://mainframe.example",
            "do-not-disclose",
            auth_mode="bearer-env",
            timeout_seconds=15,
            max_response_bytes=65536,
            opener=lambda *args, **kwargs: (_ for _ in ()).throw(OSError("private-host-detail")),
        )
        with self.assertRaises(ApplianceError) as raised:
            transport.get("/bounded", ("application/json",))
        self.assertNotIn("do-not-disclose", str(raised.exception))
        self.assertNotIn("private-host-detail", str(raised.exception))

    def test_schemas_are_versioned(self) -> None:
        for name in (
            "enterprise-appliance-profile.schema.json",
            "enterprise-appliance-fixture.schema.json",
            "enterprise-appliance-fault-catalog.schema.json",
            "enterprise-appliance-checkpoint.schema.json",
            "enterprise-appliance-fault-receipt.schema.json",
            "enterprise-appliance-receipt.schema.json",
        ):
            schema = load(ROOT / "extensions/schema" / name)
            self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])
            self.assertRegex(schema["$id"], r"-1\.0\.json$")


if __name__ == "__main__":
    unittest.main()
