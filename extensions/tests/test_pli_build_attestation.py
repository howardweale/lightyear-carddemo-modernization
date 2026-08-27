from __future__ import annotations

import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lightyear_common.asymmetric import rsa_pkcs1v15_sha256_sign
from lightyear_common.io import write_json

from lightyear_extensions.contracts import canonical_hash
from lightyear_extensions.pli_attestation import ARTIFACT_FILES, build_attestation, validate_attestation


ROOT = Path(__file__).resolve().parents[2]
CANONICAL = ROOT / "extensions/pli/attestation"


class PliBuildAttestationTests(unittest.TestCase):
    def copy_artifacts(self, destination: Path) -> None:
        for path in CANONICAL.iterdir():
            if path.is_file():
                shutil.copy2(path, destination / path.name)

    def test_committed_attestation_is_deterministic_and_valid(self) -> None:
        receipt = json.loads((CANONICAL / "build.receipt.json").read_text(encoding="utf-8"))
        self.assertEqual([], validate_attestation(ROOT, CANONICAL))
        with tempfile.TemporaryDirectory() as directory:
            generated = Path(directory)
            rebuilt = build_attestation(ROOT, generated, receipt["source_commit"])
            self.assertEqual(receipt, rebuilt)
            generated_names = set(ARTIFACT_FILES.values()) | {"build.attestation.json", "build.receipt.json"}
            for name in sorted(generated_names):
                self.assertEqual((CANONICAL / name).read_bytes(), (generated / name).read_bytes())

    def test_compiled_jar_tamper_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            copied = Path(directory)
            self.copy_artifacts(copied)
            with (copied / ARTIFACT_FILES["candidate_jar_sha256"]).open("ab") as stream:
                stream.write(b"tamper")
            self.assertTrue(validate_attestation(ROOT, copied))

    def test_dependency_and_junit_tamper_are_rejected(self) -> None:
        for filename in (
            ARTIFACT_FILES["dependency_inventory_sha256"],
            ARTIFACT_FILES["junit_xml_sha256"],
        ):
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as directory:
                copied = Path(directory)
                self.copy_artifacts(copied)
                path = copied / filename
                path.write_bytes(path.read_bytes() + b"\nchanged")
                self.assertTrue(validate_attestation(ROOT, copied))

    def test_dependency_inventory_uses_portable_toolchain_contract(self) -> None:
        inventory = json.loads(
            (CANONICAL / ARTIFACT_FILES["dependency_inventory_sha256"]).read_text(encoding="utf-8")
        )
        self.assertEqual(
            {
                "compiler": "jdk.compiler module",
                "language_release": "17",
                "runtime_contract": "Java SE 17",
            },
            inventory["toolchain"],
        )

    def test_substituted_commit_is_rejected_even_when_receipt_is_rehashed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            copied = Path(directory)
            self.copy_artifacts(copied)
            key = json.loads((CANONICAL / "keys/development-test-key.json").read_text(encoding="utf-8"))
            attestation_path = copied / "build.attestation.json"
            attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
            attestation["statement"]["predicate"]["buildDefinition"]["externalParameters"]["sourceCommit"] = "0" * 40
            attestation["signature"]["value"] = rsa_pkcs1v15_sha256_sign(
                attestation["statement"], key["public_modulus_hex"], key["private_exponent_hex"]
            )
            attestation["content_sha256"] = canonical_hash(attestation, {"content_sha256"})
            write_json(attestation_path, attestation)
            receipt_path = copied / "build.receipt.json"
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            receipt["source_commit"] = "0" * 40
            receipt["bindings"]["build_attestation_sha256"] = attestation["content_sha256"]
            receipt["content_sha256"] = canonical_hash(receipt, {"content_sha256"})
            write_json(receipt_path, receipt)
            self.assertIn("PL/I build source commit binding is invalid", validate_attestation(ROOT, copied))

    def test_content_binding_survives_unreachable_pre_evidence_commit(self) -> None:
        with patch("lightyear_extensions.pli_attestation._commit_exists", return_value=False):
            self.assertEqual([], validate_attestation(ROOT, CANONICAL))

    def test_foreign_workflow_replay_is_rejected_even_with_development_signature(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            copied = Path(directory)
            self.copy_artifacts(copied)
            key = json.loads((CANONICAL / "keys/development-test-key.json").read_text(encoding="utf-8"))
            attestation_path = copied / "build.attestation.json"
            attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
            attestation["statement"]["predicate"]["buildDefinition"]["externalParameters"]["workflow"] = "foreign/repository/.github/workflows/release.yml"
            attestation["signature"]["value"] = rsa_pkcs1v15_sha256_sign(
                attestation["statement"], key["public_modulus_hex"], key["private_exponent_hex"]
            )
            attestation["content_sha256"] = canonical_hash(attestation, {"content_sha256"})
            write_json(attestation_path, attestation)
            receipt_path = copied / "build.receipt.json"
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            receipt["bindings"]["build_attestation_sha256"] = attestation["content_sha256"]
            receipt["content_sha256"] = canonical_hash(receipt, {"content_sha256"})
            write_json(receipt_path, receipt)
            self.assertIn("PL/I build attestation targets a foreign workflow", validate_attestation(ROOT, copied))

    def test_development_key_cannot_be_promoted_to_release(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            copied = Path(directory)
            self.copy_artifacts(copied)
            receipt_path = copied / "build.receipt.json"
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            receipt["release_attestation"] = True
            receipt["production_ready"] = True
            receipt["content_sha256"] = canonical_hash(receipt, {"content_sha256"})
            write_json(receipt_path, receipt)
            self.assertIn("PL/I build receipt truth boundary is invalid", validate_attestation(ROOT, copied))


if __name__ == "__main__":
    unittest.main()
