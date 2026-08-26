from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from lightyear_extensions.adapters import (
    AdapterDescriptor,
    AdapterRegistry,
    FixtureAdapter,
    RecordedReplayAdapter,
    default_registry,
)
from lightyear_extensions.contracts import (
    ExtensionContractError,
    canonical_hash,
    finalize_envelope,
    validate_envelope,
)
from lightyear_extensions.pli import build_pli_fragment, validate_pli_fragment
from lightyear_knowledge_graph.model import load_graph


ROOT = Path(__file__).resolve().parents[2]
GRAPH = load_graph(ROOT / "knowledge" / "graph.snapshot.json.gz")
SPEC = ROOT / "extensions" / "adapters" / "fixtures" / "zosmf-intcalc.simulated.spec.json"
CAPTURE = ROOT / "extensions" / "adapters" / "fixtures" / "zosmf-intcalc.simulated.capture.json"
PLI_ROOT = ROOT / "extensions" / "pli" / "reference"
PLI_FRAGMENT = ROOT / "extensions" / "pli" / "pli.fragment.json"


class ExtensionFoundationTests(unittest.TestCase):
    def test_fixture_capture_is_deterministic_graph_bound_and_content_minimized(self) -> None:
        first = FixtureAdapter(SPEC, GRAPH).capture()
        second = FixtureAdapter(SPEC, GRAPH).capture()
        self.assertEqual(first, second)
        self.assertEqual([], validate_envelope(first, graph=GRAPH))
        self.assertEqual("simulated", first["evidence_class"])
        self.assertTrue(all(not item["content_retained"] for item in first["artifacts"]))
        self.assertEqual(first, json.loads(CAPTURE.read_text(encoding="utf-8")))

    def test_replay_never_upgrades_evidence_class(self) -> None:
        simulated = FixtureAdapter(SPEC, GRAPH).capture()
        simulated_replay = RecordedReplayAdapter(simulated, GRAPH).capture()
        self.assertEqual("simulated", simulated_replay["evidence_class"])
        live_payload = json.loads(SPEC.read_text(encoding="utf-8"))
        live_payload["evidence_class"] = "live"
        live_payload["source"]["attestation"] = "remote-verified"
        live_payload["graph_binding"] = {
            "graph_id": GRAPH["graph_id"],
            "content_sha256": GRAPH["content_sha256"],
        }
        key = b"extension-foundation-live-replay-key-32bytes"
        live = finalize_envelope(
            live_payload, signing_key=key, key_id="live-replay-key"
        )
        self.assertEqual([], validate_envelope(
            live, graph=GRAPH, trusted_keys={"live-replay-key": key}
        ))
        replay = RecordedReplayAdapter(
            live, GRAPH, {"live-replay-key": key}
        ).capture()
        self.assertEqual("recorded", replay["evidence_class"])
        self.assertEqual(live["content_sha256"], replay["recorded_from_sha256"])

    def test_live_and_recorded_classes_require_attestation_and_chain_of_custody(self) -> None:
        payload = json.loads(SPEC.read_text(encoding="utf-8"))
        payload["graph_binding"] = {
            "graph_id": GRAPH["graph_id"],
            "content_sha256": GRAPH["content_sha256"],
        }
        payload["evidence_class"] = "live"
        unsigned = finalize_envelope(payload)
        errors = validate_envelope(unsigned, graph=GRAPH)
        self.assertIn("live evidence requires a trusted signature", errors)
        self.assertIn(
            "live evidence requires remote-verified or operator-signed attestation", errors
        )
        payload["evidence_class"] = "recorded"
        recorded = finalize_envelope(payload)
        self.assertIn(
            "recorded evidence requires recorded_from_sha256",
            validate_envelope(recorded, graph=GRAPH),
        )

    def test_capture_tamper_graph_drift_and_unknown_entities_fail_closed(self) -> None:
        capture = FixtureAdapter(SPEC, GRAPH).capture()
        changed = copy.deepcopy(capture)
        changed["claims"][0]["details"]["status"] = "ACTIVE"
        self.assertIn("capture content_sha256 is invalid", validate_envelope(changed, graph=GRAPH))
        wrong_graph = copy.deepcopy(capture)
        wrong_graph["graph_binding"]["content_sha256"] = "0" * 64
        wrong_graph = finalize_envelope(wrong_graph)
        self.assertIn(
            "capture targets a different graph content identity",
            validate_envelope(wrong_graph, graph=GRAPH),
        )
        unknown = json.loads(SPEC.read_text(encoding="utf-8"))
        unknown["claims"][0]["entity_id"] = "legacy:cobol-program:DOESNOTEXIST"
        unknown["graph_binding"] = {
            "graph_id": GRAPH["graph_id"],
            "content_sha256": GRAPH["content_sha256"],
        }
        unknown = finalize_envelope(unknown)
        self.assertTrue(any("absent graph node" in item for item in validate_envelope(unknown, graph=GRAPH)))

    def test_credentials_are_redacted_and_signed_evidence_is_verified(self) -> None:
        payload = json.loads(SPEC.read_text(encoding="utf-8"))
        payload["graph_binding"] = {
            "graph_id": GRAPH["graph_id"],
            "content_sha256": GRAPH["content_sha256"],
        }
        payload["claims"][0]["details"]["authorization"] = "Bearer should-not-survive"
        key = b"extension-foundation-unit-test-key-32-bytes"
        envelope = finalize_envelope(payload, signing_key=key, key_id="test-extension-key")
        self.assertNotIn("should-not-survive", json.dumps(envelope))
        self.assertEqual([], validate_envelope(
            envelope, graph=GRAPH, trusted_keys={"test-extension-key": key}
        ))
        self.assertIn("capture signature is invalid", validate_envelope(
            envelope,
            graph=GRAPH,
            trusted_keys={"test-extension-key": b"wrong-extension-foundation-key-32bytes"},
        ))

    def test_adapter_registry_is_versioned_and_rejects_duplicate_ids(self) -> None:
        catalog = default_registry().catalog()
        self.assertEqual(sorted(item["id"] for item in catalog), [item["id"] for item in catalog])
        self.assertIn("lightyear.zosmf-jobs", {item["id"] for item in catalog})
        registry = AdapterRegistry()
        descriptor = AdapterDescriptor("example.adapter", "1.0", ("read",), ("recorded",))
        registry.register(descriptor)
        with self.assertRaisesRegex(ExtensionContractError, "Duplicate adapter"):
            registry.register(descriptor)
        catalog_payload = json.loads((ROOT / "extensions" / "catalog.json").read_text())
        self.assertEqual(
            catalog_payload["content_sha256"],
            canonical_hash(catalog_payload, {"content_sha256"}),
        )

    def test_pli_pack_builds_a_mixed_language_hash_bound_fragment(self) -> None:
        fragment = build_pli_fragment(GRAPH, PLI_ROOT, ROOT)
        self.assertEqual([], validate_pli_fragment(fragment, GRAPH))
        self.assertEqual(fragment, json.loads(PLI_FRAGMENT.read_text(encoding="utf-8")))
        kinds = fragment["statistics"]["nodes_by_kind"]
        relations = fragment["statistics"]["edges_by_relation"]
        self.assertEqual(1, kinds["pli_program"])
        self.assertEqual(1, kinds["pli_procedure"])
        self.assertEqual(1, kinds["pli_include"])
        self.assertGreaterEqual(relations["CALLS"], 2)
        external = {item["entity_id"] for item in fragment["external_references"]}
        self.assertIn("legacy:cobol-program:CBACT04C", external)
        self.assertIn("legacy:db2-table:CARDDEMO.AUTHFRDS", external)
        base_ids = {item["id"] for item in GRAPH["nodes"]}
        self.assertFalse(any("lightyear_extensions" in item for item in base_ids))

    def test_pli_fragment_rejects_base_graph_drift_and_unknown_calls(self) -> None:
        fragment = build_pli_fragment(GRAPH, PLI_ROOT, ROOT)
        drifted = copy.deepcopy(GRAPH)
        drifted["content_sha256"] = "f" * 64
        self.assertIn(
            "PL/I fragment targets a different graph content identity",
            validate_pli_fragment(fragment, drifted),
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "BAD.pli"
            source.write_text(
                "BAD: PROC OPTIONS(MAIN);\n CALL MISSINGPGM;\n END BAD;\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ExtensionContractError, "CALL target"):
                build_pli_fragment(GRAPH, root, root)


if __name__ == "__main__":
    unittest.main()
