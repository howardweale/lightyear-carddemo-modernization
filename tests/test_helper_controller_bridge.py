"""CI-only public fixture envelopes; no real helper, plaintext or imports."""
import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from lightyear_control_tower.decisions import canonical
from lightyear_execution.helper_controller_bridge import HelperControllerBridge
from lightyear_execution.helper_route_contract import HelperRouteRefused
import test_helper_route_provenance as provenance_fixtures
import test_external_custody_signing as signing_fixtures
from test_external_custody_signing import digest


class HelperControllerBridgeTests(unittest.TestCase):
    def setUp(self):
        self.provenance = provenance_fixtures.HelperRouteProvenanceTests()
        self.provenance.setUp()
        self.origin = signing_fixtures.ExternalCustodySigningTests()
        self.origin.setUp()
        self.addCleanup(self.origin.doCleanups)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/"attempt.journal"
        self.mono = 1
        p = self.provenance
        self.options = dict(
            binding=p.binding, admission_sha256="7"*64, execution_id=p.execution,
            source_index=p.index, ciphertext_inventory=p.inventory(),
            source_names=p.names, artifacts=p.rows, original_monotonic_deadline=50,
            owner_public_key=self.origin.pem, owner_key_sha256=digest(self.origin.pem),
            wall_clock=lambda: datetime(2098,1,1,tzinfo=timezone.utc),
            monotonic_clock=lambda: self.mono)
        self.bridge = HelperControllerBridge(self.path, **self.options)
        self.addCleanup(self.bridge.close)

    def response(self, **updates):
        request = self.bridge.export_once()
        value = json.loads(request)
        reply = canonical(dict(
            schema="helper-route-response/1", request_sha256=digest(request),
            binding=value["binding"], artifacts=value["artifacts"], result="ciphertext-received"))
        body = dict(schema="helper-controller-response/1",
                    context_sha256=self.bridge.context_sha256,
                    request_sha256=digest(request), response_base64=base64.b64encode(reply).decode())
        body.update(updates)
        signature = self.origin.key.sign(canonical(body))
        return canonical(dict(body, signature_base64=base64.b64encode(signature).decode()))

    def test_journal_records_preserve_exact_lf_bytes(self):
        self.bridge.export_once()
        raw = self.path.read_bytes()
        self.assertEqual(2, raw.count(b"\n"))
        self.assertNotIn(b"\r", raw)
        self.assertEqual(len(raw), self.bridge._size)
        self.assertEqual(["CREATED", "EXPORTED"],
                         [json.loads(row)["state"] for row in raw.splitlines()])

    def test_one_authenticated_match_returns_only_digests_and_status(self):
        result = self.bridge.consume_once(self.response())
        self.assertEqual(result.admission_sha256, "7"*64)
        self.assertFalse(result.native_qualified)
        self.assertNotIn("response_base64", vars(result))
        self.assertNotIn("sealed-a", self.path.read_text())
        with self.assertRaises(HelperRouteRefused):
            self.bridge.consume_once(b"{}")

    def test_mixed_context_and_changed_inventory_refused(self):
        with self.assertRaises(HelperRouteRefused):
            self.bridge.consume_once(self.response(context_sha256="8"*64))
        bad = dict(self.options, ciphertext_inventory=self.provenance.inventory(artifacts=[]))
        with self.assertRaises(HelperRouteRefused):
            HelperControllerBridge(Path(self.tmp.name)/"other", **bad)

    def test_forged_origin_consumed_before_failure(self):
        packet = json.loads(self.response())
        packet["signature_base64"] = base64.b64encode(b"x"*64).decode()
        with self.assertRaises(HelperRouteRefused):
            self.bridge.consume_once(canonical(packet))
        self.assertEqual("CONSUMED", json.loads(self.path.read_text().splitlines()[-1])["state"])
        with self.assertRaises(HelperRouteRefused):
            self.bridge.consume_once(canonical(packet))

    def test_late_response_and_uncertain_delivery_cannot_retry(self):
        response = self.response()
        self.mono = 50
        with self.assertRaises(HelperRouteRefused):
            self.bridge.consume_once(response)
        self.mono = 1
        self.bridge = HelperControllerBridge(Path(self.tmp.name)/"fresh", **self.options)
        self.addCleanup(self.bridge.close)
        self.response()
        self.bridge.mark_delivery_uncertain()
        with self.assertRaises(HelperRouteRefused):
            self.bridge.export_once()

    def test_existing_journal_cannot_resume_and_mutation_fails_closed(self):
        with self.assertRaises(FileExistsError):
            HelperControllerBridge(self.path, **self.options)
        response = self.response()
        with self.path.open("ab") as f:
            f.write(b"drift")
        with self.assertRaises(HelperRouteRefused):
            self.bridge.consume_once(response)
