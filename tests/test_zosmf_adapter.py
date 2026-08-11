from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from lightyear_knowledge_graph.model import load_graph
from lightyear_runtime.engine import RuntimeEvidenceEngine
from lightyear_runtime.mock_zosmf import RunningMockZosmf, load_mock_fixture
from lightyear_runtime.zosmf import (
    HttpClientTransport,
    HttpResponse,
    ZosmfClient,
    ZosmfConfig,
    ZosmfCredentials,
    ZosmfError,
    ZosmfJobsAdapter,
    redact_payload,
)


ROOT = Path(__file__).resolve().parents[1]
GRAPH = load_graph(ROOT / "knowledge" / "graph.snapshot.json.gz")
MAPPING = ROOT / "knowledge" / "runtime" / "zosmf" / "intcalc-mapping.json"
FIXTURE = ROOT / "knowledge" / "runtime" / "zosmf" / "mock-intcalc.json"


class StubTransport:
    def __init__(self, fixture: dict, content_type: str = "application/json") -> None:
        self.fixture = fixture
        self.content_type = content_type
        self.requests: list[tuple[str, dict, dict]] = []

    def get(self, path: str, *, query=None, headers=None) -> HttpResponse:
        self.requests.append((path, dict(query or {}), dict(headers or {})))
        job = self.fixture["job"]
        root = f"/zosmf/restjobs/jobs/{job['jobname']}/{job['jobid']}"
        if path == "/zosmf/restjobs/jobs":
            value = [job]
        elif path == root:
            value = job
        elif path == root + "/files":
            value = self.fixture["files"]
        elif path.endswith("/records"):
            file_id = path.split("/")[-2]
            body = self.fixture["records"][file_id].encode()
            return HttpResponse(200, {"content-type": "text/plain"}, body)
        else:
            return HttpResponse(404, {"content-type": "application/json"}, b"{}")
        body = json.dumps(value).encode()
        return HttpResponse(200, {"content-type": self.content_type}, body)


class ZosmfAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = load_mock_fixture(FIXTURE)

    def test_ibm_shaped_simulator_exercises_status_steps_spool_and_record_range(self) -> None:
        with RunningMockZosmf(self.fixture) as mock:
            config = ZosmfConfig(mock.base_url, "local-simulator", allow_loopback_http=True)
            credentials = ZosmfCredentials("IBMUSER", "not-retained")
            adapter = ZosmfJobsAdapter(
                ZosmfClient(HttpClientTransport(config), credentials),
                config,
                MAPPING,
                "INTCALC",
                "JOB00001",
            )
            snapshot = RuntimeEvidenceEngine(GRAPH).build([adapter.capture()])
        self.assertEqual({"simulated": 8}, snapshot["statistics"]["evidence_classes"])
        run = snapshot["runs"][0]
        self.assertEqual("passed", run["policies"]["development_readiness"]["status"])
        self.assertEqual("blocked", run["policies"]["mainframe_equivalence"]["status"])
        self.assertEqual(4, len(mock.server.requests))
        self.assertTrue(all(item["authorization_present"] for item in mock.server.requests))
        record_requests = [item for item in mock.server.requests if item["path"].endswith("/records")]
        self.assertTrue(all(item["record_range"] == "0,5000" for item in record_requests))
        serialized = json.dumps(snapshot)
        self.assertNotIn("not-retained", serialized)
        self.assertNotIn("TCATBALF DD DSN", serialized)
        self.assertTrue(all(not item["content_retained"] for item in run["artifacts"]))

    def test_real_zos_class_requires_explicit_attestation_and_remote_https(self) -> None:
        transport = StubTransport(self.fixture)
        config = ZosmfConfig("https://zosmf.example.test:10443", "SY1")
        unclaimed = ZosmfJobsAdapter(
            ZosmfClient(transport, ZosmfCredentials()), config, MAPPING, "INTCALC", "JOB00001"
        ).capture()
        self.assertTrue(all(item.evidence_class == "simulated" for item in unclaimed.observations))
        claimed = ZosmfJobsAdapter(
            ZosmfClient(transport, ZosmfCredentials()), config, MAPPING, "INTCALC", "JOB00001",
            attest_real_zos=True,
        ).capture()
        snapshot = RuntimeEvidenceEngine(GRAPH).build([claimed])
        self.assertEqual({"zos_observed": 8}, snapshot["statistics"]["evidence_classes"])
        self.assertEqual("passed", snapshot["runs"][0]["policies"]["mainframe_equivalence"]["status"])

    def test_loopback_or_plain_http_cannot_be_attested_as_real_zos(self) -> None:
        with self.assertRaisesRegex(ZosmfError, "HTTP is permitted only"):
            ZosmfConfig("http://mainframe.example.test", "SY1").validate()
        local = ZosmfConfig("http://127.0.0.1:1234", "mock", allow_loopback_http=True)
        with self.assertRaisesRegex(ZosmfError, "requires verified HTTPS"):
            ZosmfJobsAdapter(
                ZosmfClient(StubTransport(self.fixture), ZosmfCredentials()),
                local,
                MAPPING,
                "INTCALC",
                "JOB00001",
                attest_real_zos=True,
            )

    def test_url_credentials_paths_and_invalid_identifiers_are_rejected(self) -> None:
        for url in (
            "https://user:password@zosmf.example.test",
            "https://zosmf.example.test/zosmf/restjobs",
            "ftp://zosmf.example.test",
        ):
            with self.subTest(url=url), self.assertRaises(ZosmfError):
                ZosmfConfig(url, "SY1").validate()
        config = ZosmfConfig("https://zosmf.example.test", "SY1")
        with self.assertRaisesRegex(ZosmfError, "Invalid z/OS job"):
            ZosmfJobsAdapter(
                ZosmfClient(StubTransport(self.fixture), ZosmfCredentials()),
                config,
                MAPPING,
                "../BAD",
                "JOB00001",
            )

    def test_program_mismatch_is_a_contradiction_and_blocks_acceptance(self) -> None:
        fixture = copy.deepcopy(self.fixture)
        fixture["job"]["step-data"][0]["program-name"] = "WRONGPGM"
        transport = StubTransport(fixture)
        config = ZosmfConfig("https://zosmf.example.test", "SY1")
        bundle = ZosmfJobsAdapter(
            ZosmfClient(transport, ZosmfCredentials()),
            config,
            MAPPING,
            "INTCALC",
            "JOB00001",
            attest_real_zos=True,
        ).capture()
        snapshot = RuntimeEvidenceEngine(GRAPH).build([bundle])
        run = snapshot["runs"][0]
        self.assertEqual("blocked", run["policies"]["development_readiness"]["status"])
        self.assertEqual("blocked", run["policies"]["mainframe_equivalence"]["status"])
        projection = snapshot["projections"]["nodes"]["legacy:cobol-program:CBACT04C"]
        self.assertEqual("runtime_contradicted", projection["state"])

    def test_unexpected_content_type_and_unsafe_response_limit_fail_closed(self) -> None:
        bad = StubTransport(self.fixture, "text/html")
        client = ZosmfClient(bad, ZosmfCredentials())
        with self.assertRaisesRegex(ZosmfError, "Unexpected z/OSMF content type"):
            client.list_jobs("IBMUSER", "INTCALC")
        with self.assertRaisesRegex(ZosmfError, "between 1 KiB"):
            ZosmfConfig("https://zosmf.example.test", "SY1", max_response_bytes=100).validate()

    def test_redaction_is_recursive_and_does_not_mutate_safe_metadata(self) -> None:
        value = {
            "authorization": "Basic abc",
            "nested": {"password": "secret", "status": "OUTPUT"},
            "items": [{"token": "secret", "jobid": "JOB00001"}],
        }
        redacted = redact_payload(value)
        self.assertEqual("[REDACTED]", redacted["authorization"])
        self.assertEqual("[REDACTED]", redacted["nested"]["password"])
        self.assertEqual("OUTPUT", redacted["nested"]["status"])
        self.assertEqual("JOB00001", redacted["items"][0]["jobid"])


if __name__ == "__main__":
    unittest.main()
