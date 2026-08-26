from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from lightyear_extensions.campaign import (
    BoundedHttpTransport,
    CampaignError,
    FixtureTransport,
    REQUIRED_ADAPTERS,
    build_campaign_receipt,
    collect_campaign,
    load_profile,
    validate_campaign_receipt,
    validate_profile,
)
from lightyear_extensions.contracts import validate_envelope
from lightyear_knowledge_graph.model import load_graph


ROOT = Path(__file__).resolve().parents[2]
GRAPH = load_graph(ROOT / "knowledge" / "graph.snapshot.json.gz")
PROFILE_PATH = ROOT / "extensions" / "adapters" / "mainframe-access.profile.json"
RESPONSES_PATH = ROOT / "extensions" / "adapters" / "fixtures" / "mainframe-access.simulated.responses.json"
CAMPAIGN_ROOT = ROOT / "extensions" / "adapters" / "campaign"


class _Headers:
    def __init__(self, content_type: str) -> None:
        self.content_type = content_type

    def get_content_type(self) -> str:
        return self.content_type


class _Response:
    def __init__(self, body: bytes, content_type: str = "application/json") -> None:
        self.body = body
        self.headers = _Headers(content_type)

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def getcode(self) -> int:
        return 200

    def read(self, maximum: int) -> bytes:
        return self.body[:maximum]


class MainframeAccessCampaignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.profile = load_profile(PROFILE_PATH)
        cls.responses = json.loads(RESPONSES_PATH.read_text(encoding="utf-8"))

    def fixture_campaign(self):
        return collect_campaign(
            self.profile,
            GRAPH,
            FixtureTransport(self.responses),
            evidence_class="simulated",
            collected_at=self.responses["collected_at"],
        )

    def test_profile_has_exact_adapters_bounds_and_no_credentials(self) -> None:
        self.assertEqual([], validate_profile(self.profile))
        self.assertEqual(set(REQUIRED_ADAPTERS), set(self.profile["adapters"]))
        serialized = json.dumps(self.profile).lower()
        for word in ("password", "token", "authorization", "secret"):
            self.assertNotIn(f'"{word}"', serialized)

    def test_fixture_campaign_is_deterministic_complete_and_graph_bound(self) -> None:
        first_captures, first_receipt = self.fixture_campaign()
        second_captures, second_receipt = self.fixture_campaign()
        self.assertEqual(first_captures, second_captures)
        self.assertEqual(first_receipt, second_receipt)
        self.assertEqual("passed", first_receipt["status"])
        self.assertEqual("simulated", first_receipt["evidence_class"])
        self.assertFalse(first_receipt["production_ready"])
        self.assertTrue(all(first_receipt["checks"].values()))
        self.assertEqual(set(REQUIRED_ADAPTERS), {
            capture["adapter"]["id"] for capture in first_captures
        })
        self.assertTrue(all(
            validate_envelope(capture, graph=GRAPH) == [] for capture in first_captures
        ))

    def test_campaign_parsers_emit_graph_addressed_bounded_claims(self) -> None:
        captures, _ = self.fixture_campaign()
        by_adapter = {item["adapter"]["id"]: item for item in captures}
        zosmf = by_adapter["lightyear.zosmf-jobs"]
        self.assertEqual("CC 0000", zosmf["claims"][0]["details"]["completion_code"])
        db2 = by_adapter["lightyear.db2-zos-catalog"]
        self.assertEqual(26, db2["claims"][0]["details"]["column_count"])
        cics = by_adapter["lightyear.cics-cmci"]
        self.assertEqual("CAVW", cics["claims"][0]["details"]["transaction"])
        self.assertTrue(all(
            capture["artifacts"][0]["content_retained"] is False for capture in captures
        ))

    def test_generated_campaign_matches_committed_evidence(self) -> None:
        captures, receipt = self.fixture_campaign()
        expected_receipt = json.loads(
            (CAMPAIGN_ROOT / "campaign.receipt.json").read_text(encoding="utf-8")
        )
        self.assertEqual(receipt, expected_receipt)
        for capture in captures:
            adapter_id = capture["adapter"]["id"]
            expected = json.loads(
                (CAMPAIGN_ROOT / f"{adapter_id}.capture.json").read_text(encoding="utf-8")
            )
            self.assertEqual(capture, expected)

    def test_live_campaign_requires_and_verifies_a_separate_evidence_key(self) -> None:
        with self.assertRaisesRegex(CampaignError, "requires an evidence signing key"):
            collect_campaign(
                self.profile, GRAPH, FixtureTransport(self.responses), evidence_class="live"
            )
        key = b"mainframe-access-campaign-test-key-32bytes"
        captures, receipt = collect_campaign(
            self.profile,
            GRAPH,
            FixtureTransport(self.responses),
            evidence_class="live",
            collected_at="2026-08-26T00:00:00Z",
            signing_key=key,
            key_id="customer-campaign-key",
        )
        self.assertEqual("live", receipt["evidence_class"])
        self.assertTrue(receipt["checks"]["live_signatures_trusted"])
        self.assertTrue(all(validate_envelope(
            item, graph=GRAPH, trusted_keys={"customer-campaign-key": key}
        ) == [] for item in captures))

    def test_missing_duplicate_mixed_and_tampered_evidence_fail_closed(self) -> None:
        captures, receipt = self.fixture_campaign()
        missing = build_campaign_receipt(self.profile, GRAPH, captures[:-1])
        self.assertEqual("failed", missing["status"])
        self.assertFalse(missing["checks"]["exact_adapter_set"])
        duplicate = build_campaign_receipt(self.profile, GRAPH, captures + [captures[0]])
        self.assertFalse(duplicate["checks"]["unique_adapters"])
        mixed_captures = copy.deepcopy(captures)
        mixed_captures[0]["evidence_class"] = "live"
        mixed = build_campaign_receipt(self.profile, GRAPH, mixed_captures)
        self.assertFalse(mixed["checks"]["consistent_evidence_class"])
        tampered = copy.deepcopy(receipt)
        tampered["status"] = "failed"
        self.assertIn(
            "campaign receipt field differs: status",
            validate_campaign_receipt(tampered, self.profile, GRAPH, captures),
        )

    def test_http_transport_rejects_insecure_urls_paths_types_and_oversize(self) -> None:
        with self.assertRaisesRegex(CampaignError, "credential-free HTTPS"):
            BoundedHttpTransport("http://mainframe.example", "credential")
        with self.assertRaisesRegex(CampaignError, "credential-free HTTPS"):
            BoundedHttpTransport("https://user:pass@mainframe.example", "credential")
        transport = BoundedHttpTransport(
            "https://mainframe.example", "credential",
            opener=lambda *args, **kwargs: _Response(b"{}"),
        )
        with self.assertRaisesRegex(CampaignError, "credential-free absolute path"):
            transport.get("/zosmf/../admin", ("application/json",))
        wrong_type = BoundedHttpTransport(
            "https://mainframe.example", "credential",
            opener=lambda *args, **kwargs: _Response(b"{}", "text/html"),
        )
        with self.assertRaisesRegex(CampaignError, "type is not allowed"):
            wrong_type.get("/zosmf/jobs", ("application/json",))
        oversized = BoundedHttpTransport(
            "https://mainframe.example", "credential", max_response_bytes=1024,
            opener=lambda *args, **kwargs: _Response(b"x" * 1025),
        )
        with self.assertRaisesRegex(CampaignError, "exceeded"):
            oversized.get("/zosmf/jobs", ("application/json",))

    def test_http_transport_uses_get_and_does_not_disclose_credentials_in_errors(self) -> None:
        observed: dict[str, Any] = {}

        def opener(request: Any, **kwargs: Any) -> _Response:
            observed["method"] = request.get_method()
            observed["authorization"] = request.get_header("Authorization")
            return _Response(b"{}")

        transport = BoundedHttpTransport(
            "https://mainframe.example", "do-not-persist", opener=opener
        )
        response = transport.get("/bounded", ("application/json",))
        self.assertEqual(200, response.status)
        self.assertEqual("GET", observed["method"])
        self.assertEqual("Bearer do-not-persist", observed["authorization"])
        with self.assertRaises(CampaignError) as raised:
            BoundedHttpTransport(
                "https://mainframe.example", "do-not-persist",
                opener=lambda *args, **kwargs: (_ for _ in ()).throw(OSError("private")),
            ).get("/bounded", ("application/json",))
        self.assertNotIn("do-not-persist", str(raised.exception))
        self.assertNotIn("private", str(raised.exception))

    def test_malformed_adapter_responses_fail_before_evidence_is_written(self) -> None:
        malformed = copy.deepcopy(self.responses)
        path = self.profile["adapters"]["lightyear.db2-zos-catalog"]["path"]
        malformed["responses"][path]["body"].pop("primary_key")
        with self.assertRaisesRegex(CampaignError, "primary_key"):
            collect_campaign(
                self.profile,
                GRAPH,
                FixtureTransport(malformed),
                evidence_class="simulated",
                collected_at=malformed["collected_at"],
            )
        malformed_xml = copy.deepcopy(self.responses)
        path = self.profile["adapters"]["lightyear.cics-cmci"]["path"]
        malformed_xml["responses"][path]["body"] = "<cmci>"
        with self.assertRaisesRegex(CampaignError, "malformed XML"):
            collect_campaign(
                self.profile,
                GRAPH,
                FixtureTransport(malformed_xml),
                evidence_class="simulated",
                collected_at=malformed_xml["collected_at"],
            )

    def test_remote_identity_mismatch_and_unbounded_db2_projection_fail_closed(self) -> None:
        wrong_job = copy.deepcopy(self.responses)
        path = self.profile["adapters"]["lightyear.zosmf-jobs"]["path"]
        wrong_job["responses"][path]["body"]["jobname"] = "OTHERJOB"
        with self.assertRaisesRegex(CampaignError, "different job identity"):
            collect_campaign(
                self.profile, GRAPH, FixtureTransport(wrong_job),
                evidence_class="simulated", collected_at=wrong_job["collected_at"],
            )
        extra_db2 = copy.deepcopy(self.responses)
        path = self.profile["adapters"]["lightyear.db2-zos-catalog"]["path"]
        extra_db2["responses"][path]["body"]["rows"] = ["must-not-cross-boundary"]
        with self.assertRaisesRegex(CampaignError, "exact bounded projection"):
            collect_campaign(
                self.profile, GRAPH, FixtureTransport(extra_db2),
                evidence_class="simulated", collected_at=extra_db2["collected_at"],
            )

    def test_profile_rejects_extra_adapter_and_credential_fields(self) -> None:
        extra = copy.deepcopy(self.profile)
        extra["adapters"]["untrusted.adapter"] = copy.deepcopy(
            extra["adapters"]["lightyear.zosmf-jobs"]
        )
        self.assertIn(
            "access profile must configure the exact required adapter set",
            validate_profile(extra),
        )
        credentialed = copy.deepcopy(self.profile)
        credentialed["token"] = "must-not-be-stored"
        self.assertIn(
            "access profile must not contain credential-shaped fields",
            validate_profile(credentialed),
        )
        wrong_path = copy.deepcopy(self.profile)
        wrong_path["adapters"]["lightyear.db2-zos-catalog"]["path"] = "/zosmf/jobs"
        self.assertIn(
            "lightyear.db2-zos-catalog path has an invalid resource prefix",
            validate_profile(wrong_path),
        )


if __name__ == "__main__":
    unittest.main()
