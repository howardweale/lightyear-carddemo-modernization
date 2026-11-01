"""Tests for verify_public_evidence.py.

Positive tests run against REAL evidence published in the public repository
howardweale/lightyear-carddemo-modernization (a clone at ../repo, or set
LIGHTYEAR_REPO) and, when present, real GitHub Release downloads (../downloads,
or set LIGHTYEAR_DOWNLOADS).  Negative tests tamper with private COPIES in a
temporary directory; the evidence itself is never modified.

Keys: the only private keys used are DISPOSABLE Ed25519 keys generated in
memory inside a test.  They are never written to disk; only their public
halves are written, into a temporary directory that is deleted afterwards.
"""
import base64
import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
VERIFIER = HERE.parent / "tools" / "verify_public_evidence.py"
REPO = Path(os.environ.get("LIGHTYEAR_REPO", HERE.parent / "repo"))
DOWNLOADS = Path(os.environ.get("LIGHTYEAR_DOWNLOADS", HERE.parent / "downloads"))
sys.path.insert(0, str(HERE.parent / "tools"))
import verify_public_evidence as lv  # noqa: E402  (the verifier under test, not repository code)

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

# Real evidence sets (paths inside the public repository) and the public-key
# fingerprints Lightyear publishes for them.
ORACLE = "docs/receipts/oracle26ai-alloydb-core100-20260917"
ORACLE_RUN = ORACLE + "/core100-45bae6fc54684445a2b1dd5544c6e537"
ORACLE_KEY_FP = "36fdf4766568b1880c1bddef92f450c6a41279d01ff11c0abd6f78e2215c6552"  # README of that evidence set
COSGN00 = "docs/modernization/carddemo-cosgn00-evidence-2026-10-18"
IDEMPIERE_RECEIPT = "docs/calibration/idempiere-analyst-repair/campaign-01/receipt.json"
IDEMPIERE_KEY = "docs/calibration/idempiere-repeatability/authority.public.pem"
IDEMPIERE_KEY_FP = "c2fbae3453e8bcae03e0830a9eb83f310f027ad51929deee967ecee1a41f399f"
TOWER_TEST_PROOF = "docs/business-rules/evidence/tower-test-proof.json"
TOWER_TEST_KEY = "docs/business-rules/evidence/tower-test.public.pem"
TOWER_TEST_KEY_FP = "d16b7ef04b3b0dea268ee5c16437b67f2b44ddc954e0d48373db9fa25fd9ed36"
FACTORY_TOWER_KEY = "docs/factory/posttran-key-change-2026-10-23/authority.public.pem"
FACTORY_TOWER_KEY_FP = "658ba69010237ebc143a1e6d2c519f7d2adb1843993bc171c1d015e7b86b0c8a"  # docs/factory/first-install-accepted-2026-10-23.md


def run(*args):
    """Run the verifier CLI in isolated mode; return (exit_code, parsed_json)."""
    proc = subprocess.run([sys.executable, "-I", str(VERIFIER), *map(str, args), "--json"],
                          capture_output=True, text=True, timeout=600)
    try:
        out = json.loads(proc.stdout) if proc.stdout.strip() else None
    except json.JSONDecodeError:
        out = None
    return proc.returncode, out, proc.stderr


def statuses(out, check=None):
    return [r["status"] for r in out["results"] if check is None or r["check"] == check]


def disposable_keypair(tmp: Path, label="DISPOSABLE-TEST-KEY"):
    """A fresh Ed25519 key for this test only. The private key stays in memory;
    only the public PEM is written (to a temp dir, clearly labelled)."""
    priv = Ed25519PrivateKey.generate()
    pem = priv.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    path = tmp / f"{label}.public.pem"
    path.write_bytes(pem)
    return priv, path, hashlib.sha256(pem).hexdigest()


def reseal(obj, priv, key_id):
    """Re-sign a Lightyear envelope with a disposable key (Tower rule)."""
    body = {k: v for k, v in obj.items() if k not in ("content_sha256", "signature")}
    raw = lv.canonical(body, False)
    obj["content_sha256"] = hashlib.sha256(raw).hexdigest()
    obj["signature"] = {"algorithm": "Ed25519", "key_id": key_id, "value": base64.b64encode(priv.sign(raw)).decode()}
    return obj


def reseal_journal(proof, priv, key_id, decision_index):
    """Rebuild a proof's whole journal under a disposable key."""
    previous = lv.ZERO
    for i, ev in enumerate(proof["journal"]["events"], 1):
        ev["sequence"], ev["previous_sha256"] = i, previous
        reseal(ev, priv, key_id)
        previous = ev["content_sha256"]
    proof["journal"]["journal_head_sha256"] = previous
    proof["decision_sha256"] = proof["journal"]["events"][decision_index]["content_sha256"]
    reseal(proof["journal"], priv, key_id)
    return proof


def needs(path: Path):
    return unittest.skipUnless(path.exists(), f"evidence not available: {path}")


# --------------------------------------------------------------------------
# Positive tests: real published evidence
# --------------------------------------------------------------------------
@needs(REPO / ORACLE)
class RealOracleAlloyDbEvidence(unittest.TestCase):
    def test_committed_manifest_matches_files(self):
        code, out, _ = run("manifest", REPO / ORACLE, "--allow-extra", "README.md")
        self.assertEqual(code, 0, out)
        self.assertEqual(statuses(out, "manifest-sha256").count("PASS"), 5)

    def test_signed_receipts_journal_and_bindings(self):
        key = f"{REPO / ORACLE / 'public-key.pem'}={ORACLE_KEY_FP}"
        code, out, _ = run("receipt", *(REPO / ORACLE_RUN / f for f in ("authorization.json", "summary.json", "journal.json")),
                           "--trust-key", key)
        self.assertEqual(code, 0, out)
        chain = [r for r in out["results"] if r["check"] == "chain"]
        self.assertEqual([c["status"] for c in chain], ["PASS"])
        self.assertIn("339 links", chain[0]["detail"])
        self.assertGreaterEqual(statuses(out, "signature").count("PASS"), 341)
        self.assertEqual(statuses(out, "binding"), ["PASS", "PASS"])


@needs(REPO / COSGN00)
class RealCardDemoSliceEvidence(unittest.TestCase):
    def test_sha256_json_manifest(self):
        code, out, _ = run("manifest", REPO / COSGN00)
        self.assertEqual(code, 0, out)
        self.assertEqual(statuses(out, "manifest-sha256").count("PASS"), 16)

    def test_receipt_artifacts_inside_retained_zips(self):
        code, out, _ = run("receipt", REPO / COSGN00 / "receipt.json")
        self.assertEqual(code, 0, out)
        ref = [r for r in out["results"] if r["check"] == "references" and r["status"] == "PASS"][0]
        self.assertTrue(ref["detail"].startswith("155/155"), ref)


@needs(REPO / IDEMPIERE_RECEIPT)
class RealIdempiereSignedReceipt(unittest.TestCase):
    def test_signed_campaign_receipt(self):
        code, out, _ = run("receipt", REPO / IDEMPIERE_RECEIPT, "--trust-key", f"{REPO / IDEMPIERE_KEY}={IDEMPIERE_KEY_FP}")
        self.assertEqual(code, 0, out)
        self.assertEqual(statuses(out, "signature"), ["PASS"] * 5)


@needs(REPO / TOWER_TEST_PROOF)
class RealTowerProofBundle(unittest.TestCase):
    def test_committed_tower_test_proof(self):
        code, out, _ = run("decision", REPO / TOWER_TEST_PROOF, "--public-key", REPO / TOWER_TEST_KEY,
                           "--key-sha256", TOWER_TEST_KEY_FP)
        self.assertEqual(code, 0, out)
        for check in ("event-signatures", "chain", "journal-head", "decision-sha256", "decision-semantics"):
            self.assertEqual(statuses(out, check), ["PASS"], check)

    def test_correct_expected_head(self):
        head = json.loads((REPO / TOWER_TEST_PROOF).read_text())["journal"]["journal_head_sha256"]
        code, out, _ = run("decision", REPO / TOWER_TEST_PROOF, "--public-key", REPO / TOWER_TEST_KEY,
                           "--key-sha256", TOWER_TEST_KEY_FP, "--expected-head", head)
        self.assertEqual(code, 0, out)

    def test_published_factory_tower_key_fingerprint(self):
        code, out, _ = run("keyinfo", REPO / FACTORY_TOWER_KEY)
        self.assertEqual(code, 0)
        self.assertIn(FACTORY_TOWER_KEY_FP, out["results"][0]["detail"])


@needs(DOWNLOADS / "artifact-preservation-12052624443")
class RealReleaseDownloads(unittest.TestCase):
    def test_sha256sums_and_archive_members(self):
        code, out, _ = run("manifest", DOWNLOADS / "artifact-preservation-12052624443")
        self.assertEqual(code, 0, out)
        self.assertNotIn("FAIL", statuses(out))

    @needs(DOWNLOADS / "f8-worker-run41211058010-attempt1")
    def test_retention_manifest_and_tar_members(self):
        d = DOWNLOADS / "f8-worker-run41211058010-attempt1"
        code, out, _ = run("manifest", d, "--manifest", d / "retention-manifest.json", "--manifest", d / "capsule-files.json",
                           "--allow-extra", "workspace-manifest.json")
        self.assertEqual(code, 0, out)
        self.assertEqual(statuses(out, "manifest-sha256").count("PASS"), 5 + 380)

    @needs(DOWNLOADS / "verify-graph-run41115300918-attempt1")
    def test_ci_fixture_proof_structure_without_key(self):
        code, out, _ = run("all", DOWNLOADS / "verify-graph-run41115300918-attempt1")
        self.assertEqual(code, 0, out)
        self.assertIn("SKIP", statuses(out, "signature"))  # key not published: must not claim a signature PASS
        self.assertEqual(statuses(out, "chain"), ["PASS"])


# --------------------------------------------------------------------------
# Negative tests: tampered copies must FAIL
# --------------------------------------------------------------------------
class Tampering(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="lyv-test-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def copy_tree(self, rel):
        dst = self.tmp / Path(rel).name
        shutil.copytree(REPO / rel, dst)
        return dst

    # ---- manifests ------------------------------------------------------
    @needs(REPO / ORACLE)
    def test_flip_one_byte_in_listed_file(self):
        d = self.copy_tree(ORACLE)
        f = d / "operational-readback.json"
        raw = bytearray(f.read_bytes())
        raw[len(raw) // 2] ^= 0x01
        f.write_bytes(bytes(raw))
        code, out, _ = run("manifest", d, "--allow-extra", "README.md")
        self.assertEqual(code, 1)
        self.assertIn("FAIL", statuses(out, "manifest-sha256"))

    @needs(REPO / ORACLE)
    def test_drop_a_listed_file(self):
        d = self.copy_tree(ORACLE)
        (d / "public-key.pem").unlink()
        code, out, _ = run("manifest", d, "--allow-extra", "README.md")
        self.assertEqual(code, 1)
        self.assertIn("FAIL", statuses(out, "manifest-missing"))

    @needs(REPO / ORACLE)
    def test_add_an_unlisted_file(self):
        d = self.copy_tree(ORACLE)
        (d / "core100-45bae6fc54684445a2b1dd5544c6e537" / "injected.json").write_text("{}")
        code, out, _ = run("manifest", d, "--allow-extra", "README.md")
        self.assertEqual(code, 1)
        self.assertIn("FAIL", statuses(out, "manifest-extra"))

    @needs(DOWNLOADS / "f8-worker-run41211058010-attempt1")
    def test_tampered_tar_member_detected_without_extraction(self):
        import io
        import tarfile
        d = self.tmp / "f8"
        shutil.copytree(DOWNLOADS / "f8-worker-run41211058010-attempt1", d)
        src, dst = d / "capsule.tar.gz", d / "capsule.rebuilt.tar.gz"
        with tarfile.open(src) as tin, tarfile.open(dst, "w:gz") as tout:
            for m in tin.getmembers():
                data = tin.extractfile(m).read() if m.isfile() else None
                if m.name == "home/.keep":
                    data = b"x"
                    m.size = 1
                tout.addfile(m, io.BytesIO(data) if data is not None else None)
        dst.replace(src)
        code, out, _ = run("manifest", d, "--manifest", d / "capsule-files.json", "--allow-extra", "*")
        self.assertEqual(code, 1)
        fails = [r for r in out["results"] if r["status"] == "FAIL"]
        self.assertEqual([r["subject"] for r in fails], ["capsule-files.json :: home/.keep"])

    # ---- receipts and chains -------------------------------------------
    def _oracle_copy(self):
        d = self.copy_tree(ORACLE)
        return d / "core100-45bae6fc54684445a2b1dd5544c6e537", f"{d / 'public-key.pem'}={ORACLE_KEY_FP}"

    @needs(REPO / ORACLE)
    def test_edit_a_signed_value(self):
        run_dir, key = self._oracle_copy()
        doc = json.loads((run_dir / "summary.json").read_text())
        doc["mismatched"] = 0 if doc.get("mismatched") else 1
        (run_dir / "summary.json").write_text(json.dumps(doc, indent=2))
        code, out, _ = run("receipt", run_dir / "summary.json", "--trust-key", key)
        self.assertEqual(code, 1)
        self.assertIn("FAIL", statuses(out, "self-digest"))
        self.assertIn("FAIL", statuses(out, "signature"))

    @needs(REPO / ORACLE)
    def test_flip_one_signature_byte(self):
        run_dir, key = self._oracle_copy()
        doc = json.loads((run_dir / "authorization.json").read_text())
        sig = bytearray(base64.b64decode(doc["signature"]["value"]))
        sig[0] ^= 0x01
        doc["signature"]["value"] = base64.b64encode(bytes(sig)).decode()
        (run_dir / "authorization.json").write_text(json.dumps(doc))
        code, out, _ = run("receipt", run_dir / "authorization.json", "--trust-key", key)
        self.assertEqual(code, 1)
        self.assertEqual(statuses(out, "signature"), ["FAIL"])

    @needs(REPO / ORACLE)
    def test_reorder_chain(self):
        run_dir, key = self._oracle_copy()
        doc = json.loads((run_dir / "journal.json").read_text())
        ev = doc["events"]
        ev[5], ev[6] = ev[6], ev[5]
        (run_dir / "journal.json").write_text(json.dumps(doc))
        code, out, _ = run("receipt", run_dir / "journal.json", "--trust-key", key)
        self.assertEqual(code, 1)
        self.assertIn("FAIL", statuses(out, "chain"))

    @needs(REPO / ORACLE)
    def test_drop_chain_link(self):
        run_dir, key = self._oracle_copy()
        doc = json.loads((run_dir / "journal.json").read_text())
        del doc["events"][10]
        (run_dir / "journal.json").write_text(json.dumps(doc))
        code, out, _ = run("receipt", run_dir / "journal.json", run_dir / "summary.json", "--trust-key", key)
        self.assertEqual(code, 1)
        self.assertIn("FAIL", statuses(out, "chain"))

    @needs(REPO / ORACLE)
    def test_duplicate_json_key_rejected(self):
        run_dir, key = self._oracle_copy()
        f = run_dir / "summary.json"
        f.write_text(f.read_text().replace('{', '{"status": "forged",', 1))
        code, out, _ = run("receipt", f, "--trust-key", key)
        self.assertEqual(code, 1)
        self.assertEqual(statuses(out, "json"), ["FAIL"])

    @needs(REPO / COSGN00)
    def test_receipt_artifact_inside_zip_tampered(self):
        import zipfile
        d = self.copy_tree(COSGN00)
        z = d / "carddemo-proof-api.zip"
        tmpz = d / "rebuilt.zip"
        with zipfile.ZipFile(z) as zin, zipfile.ZipFile(tmpz, "w") as zout:
            for info in zin.infolist():
                data = zin.read(info)
                if info.filename == "carddemo-web-bindings/bindings.json":
                    data = data.replace(b"{", b"{ ", 1)
                zout.writestr(info, data)
        tmpz.replace(z)
        code, out, _ = run("receipt", d / "receipt.json")
        self.assertEqual(code, 1)
        self.assertIn("FAIL", statuses(out, "references"))

    # ---- Tower decision proofs -----------------------------------------
    def _proof(self):
        return json.loads((REPO / TOWER_TEST_PROOF).read_text())

    def _write(self, obj, name="proof.json"):
        p = self.tmp / name
        p.write_text(json.dumps(obj))
        return p

    @needs(REPO / TOWER_TEST_PROOF)
    def test_wrong_key_signature(self):
        _, pub, fp = disposable_keypair(self.tmp)
        code, out, _ = run("decision", REPO / TOWER_TEST_PROOF, "--public-key", pub, "--key-sha256", fp)
        self.assertEqual(code, 1)
        self.assertIn("FAIL", statuses(out, "signature"))
        self.assertNotIn("PASS", statuses(out, "event-signatures"))

    @needs(REPO / TOWER_TEST_PROOF)
    def test_fingerprint_mismatch_refused(self):
        code, _, err = run("decision", REPO / TOWER_TEST_PROOF, "--public-key", REPO / TOWER_TEST_KEY,
                           "--key-sha256", FACTORY_TOWER_KEY_FP)
        self.assertEqual(code, 2)
        self.assertIn("does NOT match the fingerprint", err)

    @needs(REPO / TOWER_TEST_PROOF)
    def test_prefix_fingerprint_refused(self):
        code, _, err = run("decision", REPO / TOWER_TEST_PROOF, "--public-key", REPO / TOWER_TEST_KEY,
                           "--key-sha256", TOWER_TEST_KEY_FP[:8])
        self.assertEqual(code, 2)

    @needs(REPO / TOWER_TEST_PROOF)
    def test_forged_bundle_signed_by_other_key(self):
        priv, _, fp = disposable_keypair(self.tmp)
        proof = reseal_journal(self._proof(), priv, fp, 3)
        code, out, _ = run("decision", self._write(proof), "--public-key", REPO / TOWER_TEST_KEY, "--key-sha256", TOWER_TEST_KEY_FP)
        self.assertEqual(code, 1)
        self.assertIn("FAIL", statuses(out, "signature"))

    @needs(REPO / TOWER_TEST_PROOF)
    def test_tampered_outcome(self):
        proof = self._proof()
        proof["journal"]["events"][3]["payload"]["outcome"] = "retire"
        code, out, _ = run("decision", self._write(proof), "--public-key", REPO / TOWER_TEST_KEY, "--key-sha256", TOWER_TEST_KEY_FP)
        self.assertEqual(code, 1)
        self.assertIn("FAIL", statuses(out, "self-digest"))

    @needs(REPO / TOWER_TEST_PROOF)
    def test_reordered_journal(self):
        proof = self._proof()
        ev = proof["journal"]["events"]
        ev[1], ev[2] = ev[2], ev[1]
        code, out, _ = run("decision", self._write(proof), "--public-key", REPO / TOWER_TEST_KEY, "--key-sha256", TOWER_TEST_KEY_FP)
        self.assertEqual(code, 1)
        self.assertIn("FAIL", statuses(out, "chain"))

    @needs(REPO / TOWER_TEST_PROOF)
    def test_stale_head(self):
        code, out, _ = run("decision", REPO / TOWER_TEST_PROOF, "--public-key", REPO / TOWER_TEST_KEY,
                           "--key-sha256", TOWER_TEST_KEY_FP, "--expected-head", "ab" * 32)
        self.assertEqual(code, 1)
        self.assertEqual(statuses(out, "journal-head-expected"), ["FAIL"])

    @needs(REPO / TOWER_TEST_PROOF)
    def test_wrong_decision_requested(self):
        code, out, _ = run("decision", REPO / TOWER_TEST_PROOF, "--public-key", REPO / TOWER_TEST_KEY,
                           "--key-sha256", TOWER_TEST_KEY_FP, "--decision-sha256", "cd" * 32)
        self.assertEqual(code, 1)

    @needs(REPO / TOWER_TEST_PROOF)
    def test_disposable_key_roundtrip_and_non_human_decider(self):
        priv, pub, fp = disposable_keypair(self.tmp)
        # Positive control: an untouched re-signed journal verifies under its own pinned key.
        good = reseal_journal(self._proof(), priv, fp, 3)
        code, out, _ = run("decision", self._write(good, "good.json"), "--public-key", pub, "--key-sha256", fp)
        self.assertEqual(code, 0, out)
        # The same journal, validly signed, but the decider is an agent: must FAIL on semantics.
        bad = copy.deepcopy(self._proof())
        for ev in bad["journal"]["events"][1:]:
            ev["actor"]["kind"] = "agent"
            if isinstance(ev["payload"].get("actor"), dict):
                ev["payload"]["actor"]["kind"] = "agent"
        bad = reseal_journal(bad, priv, fp, 3)
        code, out, _ = run("decision", self._write(bad, "bad.json"), "--public-key", pub, "--key-sha256", fp)
        self.assertEqual(code, 1)
        self.assertEqual(statuses(out, "decision-semantics"), ["FAIL"])

    @needs(REPO / TOWER_TEST_PROOF)
    def test_superseded_decision(self):
        priv, pub, fp = disposable_keypair(self.tmp)
        proof = self._proof()
        later = copy.deepcopy(proof["journal"]["events"][3])
        later["payload"]["outcome"] = "retire"
        proof["journal"]["events"].append(later)
        proof = reseal_journal(proof, priv, fp, 3)
        code, out, _ = run("decision", self._write(proof), "--public-key", pub, "--key-sha256", fp)
        self.assertEqual(code, 1)
        self.assertIn("superseded", json.dumps(out))

    def test_private_key_file_refused(self):
        fake = self.tmp / "not-a-real-key.pem"
        fake.write_text("-----BEGIN PRIVATE KEY-----\nTk9UIEEgUkVBTCBLRVk=\n-----END PRIVATE KEY-----\n")
        code, _, err = run("keyinfo", fake)
        self.assertEqual(code, 2)
        self.assertIn("PRIVATE", err)

    def test_unsafe_manifest_path(self):
        d = self.tmp / "evidence"
        d.mkdir()
        (d / "a.txt").write_text("a")
        (d / "SHA256SUMS").write_text(f"{hashlib.sha256(b'a').hexdigest()}  ../a.txt\n")
        code, out, _ = run("manifest", d, "--allow-extra", "a.txt")
        self.assertEqual(code, 1)
        self.assertIn("FAIL", statuses(out, "manifest-path"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
