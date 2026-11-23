"""CI-only regression coverage for fresh MS70 reproduction and refusal."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lightyear_data import idempiere_triage as triage
from lightyear_data import ms70_current_evidence as evidence
from lightyear_data.contracts import content_hash, seal

ROOT = Path(__file__).resolve().parents[1]


class CurrentSourceEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle, cls.originals = evidence.verify_current(ROOT)

    def forged(self, value, reason):
        value = seal(value)
        with patch.object(evidence, "_load_bundle", return_value=value):
            with self.assertRaisesRegex(ValueError, reason):
                evidence.verify_current(ROOT)

    def test_current_evidence_is_new_production_and_preserves_originals(self):
        before = {path: hashlib.sha256((ROOT/path).read_bytes()).hexdigest()
                  for path in evidence.BOUND_FILES}
        bundle, originals = evidence.verify_current(ROOT)
        self.assertEqual(bundle["artifacts"], triage.build_stage3_artifacts(ROOT))
        self.assertEqual(bundle["inputs"], evidence.input_fingerprints(ROOT))
        self.assertEqual(bundle["context"], evidence._context(ROOT))
        for name in evidence.ORIGINAL_NAMES:
            self.assertEqual(originals[name], triage._read(ROOT/triage.ROOT_PATH/name))
        self.assertEqual(before, {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
                                  for p in evidence.BOUND_FILES})
        self.assertFalse(bundle["claims"]["native_execution"])
        self.assertFalse(bundle["claims"]["production_ready"])

    def test_old_bundle_cannot_satisfy_another_checkout_run_attempt_or_job(self):
        for key in ("checkout", "tree", "candidate", "run_id", "attempt", "job"):
            with self.subTest(key=key):
                value = copy.deepcopy(self.bundle)
                value["context"][key] = "different"
                self.forged(value, "stale CI/checkout identity")

    def test_input_edit_is_refused_without_automatic_regeneration(self):
        changed = copy.deepcopy(self.bundle["inputs"])
        changed["src/lightyear_factory/providers.py"]["raw_sha256"] = "0"*64
        with patch.object(evidence, "input_fingerprints", return_value=changed):
            with patch.object(evidence, "produce_and_verify") as producer:
                with self.assertRaisesRegex(ValueError, "input drift"):
                    evidence.verify_current(ROOT)
                producer.assert_not_called()

    def test_resealed_artifact_and_hash_changes_still_fail_reproduction(self):
        value = copy.deepcopy(self.bundle)
        name = triage.RECEIPT_PATH.name
        value["artifacts"][name]["statistics"]["model_calls"] = 1
        value["artifacts"][name] = seal(value["artifacts"][name])
        value["artifact_hashes"][name] = content_hash(value["artifacts"][name])
        self.forged(value, "artifact drift")

    def test_resealed_missing_or_extra_artifact_is_refused(self):
        for mode in ("missing", "extra"):
            with self.subTest(mode=mode):
                value = copy.deepcopy(self.bundle)
                if mode == "missing":
                    del value["artifacts"][triage.RECEIPT_PATH.name]
                else:
                    value["artifacts"]["unlisted.json"] = seal(dict(extra=True))
                self.forged(value, "artifact drift")

    def test_resealed_history_change_is_refused(self):
        value = copy.deepcopy(self.bundle)
        value["history"][0] = "0"*64
        self.forged(value, "lineage mismatch")

    def test_resealed_claim_promotion_or_boolean_count_is_refused(self):
        for key, replacement in (("native_execution", True), ("production_ready", True),
                                 ("model_calls", False), ("builder_calls", 1)):
            with self.subTest(key=key):
                value = copy.deepcopy(self.bundle)
                value["claims"][key] = replacement
                self.forged(value, "identity or claims")

    def test_artifact_hash_manifest_must_match_reproduced_outputs(self):
        value = copy.deepcopy(self.bundle)
        value["artifact_hashes"][triage.RECEIPT_PATH.name] = "0"*64
        self.forged(value, "artifact hash mismatch")

    def test_missing_current_bundle_blocks_existing_validator(self):
        with patch.object(evidence, "_load_bundle", side_effect=FileNotFoundError("missing")):
            self.assertIn("stage3-validation-error:FileNotFoundError",
                          triage.validate_stage3_artifacts(ROOT))

    def test_existing_caller_drift_check_still_sees_resealed_tampering(self):
        actual = copy.deepcopy(self.originals)
        name = triage.RECEIPT_PATH.name
        actual[name]["claims"]["audit_complete"] = True
        actual[name] = seal(actual[name])
        self.assertIn("stage3-artifact-drift:"+name,
                      triage.validate_stage3_artifacts(ROOT, artifacts=actual))
        selected = triage._retained_stage3_projection(
            ROOT, actual, triage.build_stage3_artifacts(ROOT))
        self.assertEqual(selected[name], actual[name])

    def test_current_bundle_never_replaces_missing_successor(self):
        successor = ROOT / evidence.HISTORY[1][0]
        exists = Path.exists
        with patch.object(Path, "exists", lambda p: False if p == successor else exists(p)):
            with self.assertRaisesRegex(ValueError, "identity mismatch"):
                evidence.verify_current(ROOT)

    def test_source_identity_guard_checks_historical_objects(self):
        original = evidence._historic_blob
        def changed(root, commit, relative):
            raw = original(root, commit, relative)
            return raw+b"\n# changed\n" if relative == "src/lightyear_factory/providers.py" else raw
        with patch.object(evidence, "_historic_blob", side_effect=changed):
            with self.assertRaisesRegex(ValueError, "source identity mismatch"):
                evidence.verify_current(ROOT)

    def test_duplicate_json_and_parent_paths_are_refused(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            evidence._decode(b'{"x":1,"x":2}')
        for relative in ("../escape", "/absolute", "a/../escape"):
            with self.subTest(relative=relative):
                with self.assertRaisesRegex(ValueError, "relative path"):
                    evidence._file(ROOT, relative)

    def test_ci_only_context_is_required(self):
        with patch.dict(evidence.os.environ, {"GITHUB_ACTIONS": "false"}):
            with self.assertRaisesRegex(ValueError, "CI-only"):
                evidence._context(ROOT)

    def test_new_source_requires_new_ci_record_without_editing_old_record(self):
        # Isolated software fixture exercises production, disk readback and verifier.
        # Only external Git/CI context and the large existing assembler are substituted.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            context = copy.deepcopy(self.bundle["context"])
            inputs = copy.deepcopy(self.bundle["inputs"])
            records = [{"content_sha256": h} for h in self.bundle["history"]]
            artifacts = copy.deepcopy(self.bundle["artifacts"])
            with patch.object(evidence, "_context", side_effect=lambda _: copy.deepcopy(context)), \
                 patch.object(evidence, "_descriptor"), \
                 patch.object(evidence, "verify_history", return_value=(records, self.originals)), \
                 patch.object(evidence, "input_fingerprints", side_effect=lambda _: copy.deepcopy(inputs)), \
                 patch.object(triage, "build_stage3_artifacts", side_effect=lambda _: copy.deepcopy(artifacts)):
                first = evidence.produce_and_verify(root)
                old_path = root / first["path"]
                old_bytes = old_path.read_bytes()
                context["checkout"] = "a"*40
                context["candidate"] = "a"*40
                inputs["src/lightyear_factory/providers.py"]["raw_sha256"] = "b"*64
                with self.assertRaisesRegex(ValueError, "stale CI/checkout identity"):
                    evidence.verify_current(root)
                second = evidence.produce_and_verify(root)
                self.assertNotEqual(first["path"], second["path"])
                self.assertEqual(old_path.read_bytes(), old_bytes)
                self.assertEqual(evidence.verify_current(root)[0]["context"], context)
                with self.assertRaises(FileExistsError):
                    evidence.produce_and_verify(root)

    def test_pointer_digest_and_filename_are_checked_before_payload_acceptance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / evidence.OUTPUT
            output.mkdir(parents=True)
            pointer = output / "current.json"
            pointer.write_text(json.dumps(dict(filename="../escape", sha256="0"*64)))
            with self.assertRaisesRegex(ValueError, "filename"):
                evidence._load_bundle(root)
            name = "ms70-current-source-2026-11-02-"+"a"*40+"-1-1-fixture.json"
            (output/name).write_text("{}")
            pointer.write_text(json.dumps(dict(filename=name, sha256="0"*64)))
            with self.assertRaisesRegex(ValueError, "pointer digest mismatch"):
                evidence._load_bundle(root)


if __name__ == "__main__":
    unittest.main()
