"""Self-contained tests for tools/verify_public_evidence.py.

Every fixture is generated inside a temporary directory by the test itself:
no repository evidence, Release download or network access is needed, so
nothing is skipped.  Positive controls build well-formed evidence; negative
tests tamper with it and must FAIL; hardening tests feed hostile input
(symlinks, restricted paths, malformed JSON, archive bombs, duplicate archive
members, empty scans) and check the exact outcome and exit code.

Keys: the only private keys are DISPOSABLE Ed25519 keys generated in memory
per test.  They are never written to disk; only public halves are written, to
a temporary directory deleted afterwards.  Signatures made here prove the
verifier's mechanics only; they establish no trust in any Lightyear key.
"""
import base64
import contextlib
import copy
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
VERIFIER = HERE.parent / "tools" / "verify_public_evidence.py"
sys.path.insert(0, str(VERIFIER.parent))
import verify_public_evidence as lv  # noqa: E402  (the verifier under test, not repository code)

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

SCOPE = "release-review"
HUMAN = {"id": "reviewer-1", "kind": "human", "name": "Reviewer One"}
ADMIN = {"id": "local-authority-administrator", "kind": "service", "name": "Local authority administration"}
SID = "5d0c3b7e-0000-4000-8000-000000000001"
BOUND = {"receipt": "11" * 32, "request": "22" * 32}


# --------------------------------------------------------------------------
# Runners
# --------------------------------------------------------------------------
def run(*args, block_crypto=False, json_out=True):
    """Run the CLI in a fresh isolated interpreter; return (exit, json, stderr)."""
    argv = [*map(str, args)] + (["--json"] if json_out else [])
    if block_crypto:
        code = ("import sys, runpy; sys.modules['cryptography'] = None; "
                f"sys.argv = [{str(VERIFIER)!r}] + {argv!r}; runpy.run_path({str(VERIFIER)!r}, run_name='__main__')")
        cmd = [sys.executable, "-I", "-c", code]
    else:
        cmd = [sys.executable, "-I", str(VERIFIER), *argv]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    try:
        out = json.loads(proc.stdout) if proc.stdout.strip() and json_out else None
    except json.JSONDecodeError:
        out = None
    return proc.returncode, out, proc.stderr


def run_inproc(*args):
    """Run main() in this process (for monkeypatching and fast fuzzing)."""
    buf, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
        try:
            code = lv.main([*map(str, args), "--json"])
        except SystemExit as exc:
            code = exc.code
    out = json.loads(buf.getvalue()) if buf.getvalue().strip() else None
    return code, out, err.getvalue()


def statuses(out, check=None):
    return [r["status"] for r in out["results"] if check is None or r["check"] == check]


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


# --------------------------------------------------------------------------
# Fixture builders
# --------------------------------------------------------------------------
def disposable_keypair(tmp: Path, label="DISPOSABLE-TEST-KEY"):
    priv = Ed25519PrivateKey.generate()
    pem = priv.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    path = tmp / f"{label}.public.pem"
    path.write_bytes(pem)
    return priv, path, sha(pem)


def seal(obj, priv, key_id):
    """Sign a Lightyear envelope (Tower rule: canonical UTF-8 without the seal)."""
    body = {k: v for k, v in obj.items() if k not in ("content_sha256", "signature")}
    raw = lv.canonical(body, False)
    obj["content_sha256"] = sha(raw)
    obj["signature"] = {"algorithm": "Ed25519", "key_id": key_id, "value": base64.b64encode(priv.sign(raw)).decode()}
    return obj


def digest_only(obj):
    body = {k: v for k, v in obj.items() if k != "content_sha256"}
    obj["content_sha256"] = sha(lv.canonical(body, False))
    return obj


def event(kind, actor, session_id, at, payload):
    return {"record_type": "control-tower-decision-event", "schema_version": "1.0", "kind": kind,
            "actor": copy.deepcopy(actor), "session_id": session_id, "occurred_at": at, "payload": payload}


def base_events():
    decision = {"schema": "tower-decision/1", "kind": "release-approval", "kind_version": 1, "scope": SCOPE,
                "actor": copy.deepcopy(HUMAN), "session_id": SID, "channel": "control-tower",
                "roles_held": ["approver"], "bound": dict(BOUND), "outcome": "approve", "decision_slot": None,
                "reason": "Reviewed the bound receipt and request", "authentication": "individual-local-credential"}
    return [
        event("roles_assigned", ADMIN, None, "2026-11-01T10:00:00+00:00",
              {"actor_id": "reviewer-1", "roles": ["approver"], "scope": SCOPE, "reason": "Assigned by owner"}),
        event("session_started", HUMAN, SID, "2026-11-01T10:01:00+00:00",
              {"authentication": "individual-local-credential", "expires_at": "2026-11-01T11:01:00+00:00", "scope": SCOPE}),
        event("tower_decision", HUMAN, SID, "2026-11-01T10:05:00+00:00", decision),
    ]


def make_proof(priv, kid, mutate=None, decision_index=None):
    """A complete tower-decision-proof/1 bundle signed with a disposable key.
    `mutate(events)` edits the unsigned events before they are sealed."""
    events = base_events()
    if mutate:
        mutate(events)
    previous = lv.ZERO
    for i, ev in enumerate(events, 1):
        ev["sequence"], ev["previous_sha256"] = i, previous
        seal(ev, priv, kid)
        previous = ev["content_sha256"]
    if decision_index is None:
        decision_index = next(i for i, e in enumerate(events) if e["kind"] == "tower_decision")
    export = {"record_type": "tower-journal-export/1", "scope": SCOPE, "exported_at": "2026-11-01T10:06:00+00:00",
              "events": events, "journal_head_sha256": previous,
              "signature_type": "Service countersignature of authenticated operator intent"}
    seal(export, priv, kid)
    return {"schema": "tower-decision-proof/1", "decision_sha256": events[decision_index]["content_sha256"], "journal": export}


def reseal_whole(proof, priv, kid):
    """Re-sign an already-built proof after editing it (keeps the decision index)."""
    events = proof["journal"]["events"]
    old = proof["decision_sha256"]
    idx = next(i for i, e in enumerate(events) if e.get("content_sha256") == old)
    previous = lv.ZERO
    for i, ev in enumerate(events, 1):
        ev["sequence"], ev["previous_sha256"] = i, previous
        seal(ev, priv, kid)
        previous = ev["content_sha256"]
    proof["journal"]["journal_head_sha256"] = previous
    seal(proof["journal"], priv, kid)
    proof["decision_sha256"] = events[idx]["content_sha256"]
    return proof


def write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1))
    return path


def sums(entries):
    return "".join(f"{h}  {n}\n" for n, h in entries)


class Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="lyv-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def evidence(self, name="evidence"):
        """A small evidence directory with a SHA256SUMS covering every file."""
        d = self.tmp / name
        (d / "sub").mkdir(parents=True)
        files = {"a.txt": b"alpha\n", "sub/b.bin": bytes(range(256))}
        for n, raw in files.items():
            (d / n).write_bytes(raw)
        (d / "SHA256SUMS").write_text(sums((n, sha(raw)) for n, raw in files.items()))
        return d

    def proof_file(self, mutate=None, name="proof.json"):
        priv, pub, fp = disposable_keypair(self.tmp)
        return write_json(self.tmp / name, make_proof(priv, fp, mutate)), pub, fp, priv

    def assertClean(self, err):
        self.assertNotIn("Traceback", err)


# --------------------------------------------------------------------------
# Positive controls
# --------------------------------------------------------------------------
class Positive(Tmp):
    def test_sha256sums_manifest(self):
        d = self.evidence()
        code, out, err = run("manifest", d, "--manifest", d / "SHA256SUMS", "--strict")
        self.assertEqual(code, 0, out)
        self.assertEqual(statuses(out, "manifest-sha256"), ["PASS", "PASS"])
        self.assertEqual(out["summary"]["verified"], 2)
        self.assertEqual(out["summary"]["anchored"], 2)

    def test_discovered_manifest_is_only_consistency(self):
        """A manifest found next to the files could have been rewritten with them."""
        d = self.evidence()
        code, out, _ = run("manifest", d)
        self.assertEqual(code, 3)
        self.assertEqual(out["verdict"], "UNANCHORED")

    def test_json_files_manifest(self):
        d = self.tmp / "ev"
        d.mkdir()
        (d / "x.json").write_text('{"k": 1}')
        write_json(d / "manifest.json", {"files": {"x.json": sha(b'{"k": 1}')}})
        code, out, _ = run("manifest", d, "--manifest", d / "manifest.json", "--strict")
        self.assertEqual(code, 0, out)

    def test_zip_and_tar_members_without_extraction(self):
        d = self.tmp / "rel"
        d.mkdir()
        member = b"member bytes\n"
        with zipfile.ZipFile(d / "bundle.zip", "w") as z:
            z.writestr("inner/x.txt", member)
        with tarfile.open(d / "capsule.tar.gz", "w:gz") as t:
            info = tarfile.TarInfo("home/y.txt")
            info.size = len(member)
            t.addfile(info, io.BytesIO(member))
        (d / "SHA256SUMS").write_text(sums([
            ("bundle.zip", sha((d / "bundle.zip").read_bytes())),
            ("capsule.tar.gz", sha((d / "capsule.tar.gz").read_bytes())),
            ("inner/x.txt", sha(member)), ("home/y.txt", sha(member))]))
        code, out, _ = run("manifest", d, "--manifest", d / "SHA256SUMS", "--strict")
        self.assertEqual(code, 0, out)
        self.assertEqual(statuses(out, "manifest-sha256"), ["PASS"] * 4)
        self.assertFalse((d / "inner").exists() or (d / "home").exists(), "nothing may be extracted")

    def test_signed_receipt_chain_bindings_and_references(self):
        priv, pub, fp = disposable_keypair(self.tmp)
        d = self.tmp / "run"
        d.mkdir()
        (d / "out.txt").write_bytes(b"result\n")
        auth = seal({"schema": "authorization/1", "scope": SCOPE}, priv, fp)
        write_json(d / "authorization.json", auth)
        events, prev = [], lv.ZERO
        for i in range(1, 4):
            e = digest_only({"sequence": i, "previous_sha256": prev, "type": "step"})
            events.append(e)
            prev = e["content_sha256"]
        write_json(d / "journal.json", {"events": events})
        summary = seal({"schema": "public-operational-receipt/1", "authorization_sha256": auth["content_sha256"],
                        "journal_head_sha256": prev, "outputs": [{"path": "out.txt", "sha256": sha(b"result\n")}]}, priv, fp)
        write_json(d / "summary.json", summary)
        code, out, _ = run("receipt", d / "authorization.json", d / "summary.json", d / "journal.json",
                           "--trust-key", f"{pub}={fp}", "--strict")
        self.assertEqual(code, 0, out)
        self.assertEqual(statuses(out, "signature"), ["PASS", "PASS"])
        self.assertEqual(statuses(out, "chain"), ["PASS"])
        self.assertEqual(statuses(out, "binding"), ["PASS", "PASS"])
        self.assertEqual(statuses(out, "references"), ["PASS"])

    def test_decision_proof_with_expected_head(self):
        p, pub, fp, _ = self.proof_file()
        head = json.loads(p.read_text())["journal"]["journal_head_sha256"]
        code, out, _ = run("decision", p, "--public-key", pub, "--key-sha256", fp, "--expected-head", head,
                           "--expect-bound", f"receipt={'11' * 32}", "--strict")
        self.assertEqual(code, 0, out)
        for check in ("event-signatures", "chain", "journal-head", "journal-head-expected", "decision-sha256", "decision-semantics"):
            self.assertEqual(statuses(out, check), ["PASS"], check)
        self.assertNotIn("synthetic-fixture", [r["check"] for r in out["results"]])

    def test_spki_fingerprint_accepted(self):
        p, pub, _, _ = self.proof_file()
        code, out, _ = run("keyinfo", pub)
        self.assertEqual(code, 0)
        spki = out["results"][0]["detail"].split("SPKI-DER sha256 ")[1].split(";")[0]
        code, out, _ = run("decision", p, "--public-key", pub, "--key-sha256", spki)
        self.assertEqual(code, 0, out)

    def test_all_walks_everything(self):
        d = self.evidence()
        priv, pub, fp = disposable_keypair(d)
        write_json(d / "proof.json", make_proof(priv, fp))
        write_json(d / "receipt.json", seal({"schema": "public-operational-receipt/1", "n": 1}, priv, fp))
        a = sha((d / "a.txt").read_bytes())
        (d / "README.md").write_text(f"[a](a.txt#sha256={a}) and [via sub](sub/../a.txt#sha256={a})\n")
        code, out, _ = run("all", d, "--trust-key", f"{pub}={fp}", "--strict")
        self.assertEqual(code, 0, out)
        self.assertEqual(statuses(out, "md-link"), ["PASS", "PASS"])
        self.assertEqual(statuses(out, "decision-semantics"), ["PASS"])

    def test_version(self):
        proc = subprocess.run([sys.executable, "-I", str(VERIFIER), "--version"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        self.assertIn(lv.VERSION, proc.stdout)


# --------------------------------------------------------------------------
# Tampering: every change must FAIL
# --------------------------------------------------------------------------
class Tampering(Tmp):
    def test_flip_one_byte(self):
        d = self.evidence()
        raw = bytearray((d / "sub/b.bin").read_bytes())
        raw[7] ^= 1
        (d / "sub/b.bin").write_bytes(bytes(raw))
        code, out, _ = run("manifest", d)
        self.assertEqual(code, 1)
        self.assertEqual(statuses(out, "manifest-sha256"), ["PASS", "FAIL"])

    def test_drop_a_listed_file(self):
        d = self.evidence()
        (d / "a.txt").unlink()
        code, out, _ = run("manifest", d)
        self.assertEqual(code, 1)
        self.assertEqual(statuses(out, "manifest-missing"), ["FAIL"])

    def test_add_an_unlisted_file(self):
        d = self.evidence()
        (d / "sub" / "injected.json").write_text("{}")
        code, out, _ = run("manifest", d)
        self.assertEqual(code, 1)
        self.assertEqual(statuses(out, "manifest-extra"), ["FAIL"])

    def test_allow_extra_is_a_warning(self):
        d = self.evidence()
        (d / "README.md").write_text("x")
        m = d / "SHA256SUMS"
        self.assertEqual(run("manifest", d, "--manifest", m, "--allow-extra", "README.md")[0], 0)
        self.assertEqual(run("manifest", d, "--manifest", m, "--allow-extra", "README.md", "--strict")[0], 3)

    def test_unsafe_manifest_path(self):
        d = self.tmp / "ev"
        d.mkdir()
        (d / "a.txt").write_text("a")
        (d / "SHA256SUMS").write_text(sums([("../a.txt", sha(b"a"))]))
        code, out, _ = run("manifest", d, "--allow-extra", "a.txt")
        self.assertEqual(code, 1)
        self.assertEqual(statuses(out, "manifest-path"), ["FAIL"])

    def test_duplicate_manifest_entry(self):
        d = self.evidence()
        with open(d / "SHA256SUMS", "a") as fh:
            fh.write(f"{'00' * 32}  a.txt\n")
        code, out, _ = run("manifest", d)
        self.assertEqual(code, 1)
        self.assertIn("FAIL", statuses(out, "manifest-format"))

    def test_tampered_zip_member(self):
        d = self.tmp / "rel"
        d.mkdir()
        with zipfile.ZipFile(d / "bundle.zip", "w") as z:
            z.writestr("inner/x.txt", b"evil\n")
        (d / "SHA256SUMS").write_text(sums([("inner/x.txt", sha(b"good\n"))]))
        code, out, _ = run("manifest", d, "--allow-extra", "*.zip")
        self.assertEqual(code, 1)
        self.assertEqual(statuses(out, "manifest-sha256"), ["FAIL"])

    def test_signed_value_edited(self):
        priv, pub, fp = disposable_keypair(self.tmp)
        doc = seal({"schema": "public-operational-receipt/1", "mismatched": 0}, priv, fp)
        doc["mismatched"] = 1
        code, out, _ = run("receipt", write_json(self.tmp / "r.json", doc), "--trust-key", f"{pub}={fp}")
        self.assertEqual(code, 1)
        self.assertEqual(statuses(out, "self-digest"), ["FAIL"])
        self.assertEqual(statuses(out, "signature"), ["FAIL"])

    def test_signature_byte_flipped(self):
        priv, pub, fp = disposable_keypair(self.tmp)
        doc = seal({"schema": "public-operational-receipt/1"}, priv, fp)
        sig = bytearray(base64.b64decode(doc["signature"]["value"]))
        sig[0] ^= 1
        doc["signature"]["value"] = base64.b64encode(bytes(sig)).decode()
        code, out, _ = run("receipt", write_json(self.tmp / "r.json", doc), "--trust-key", f"{pub}={fp}")
        self.assertEqual(code, 1)
        self.assertEqual(statuses(out, "signature"), ["FAIL"])

    def test_unpinned_signature_is_skip_not_pass(self):
        priv, _, fp = disposable_keypair(self.tmp)
        doc = seal({"schema": "public-operational-receipt/1"}, priv, fp)
        code, out, _ = run("receipt", write_json(self.tmp / "r.json", doc))
        self.assertEqual(code, 3)
        self.assertEqual(out["verdict"], "UNANCHORED")
        self.assertEqual(statuses(out, "signature"), ["SKIP"])

    def _chain(self, n=6):
        events, prev = [], lv.ZERO
        for i in range(1, n + 1):
            e = digest_only({"sequence": i, "previous_sha256": prev, "type": "step"})
            events.append(e)
            prev = e["content_sha256"]
        return {"events": events}

    def test_reorder_and_drop_chain_links(self):
        doc = self._chain()
        doc["events"][2], doc["events"][3] = doc["events"][3], doc["events"][2]
        code, out, _ = run("receipt", write_json(self.tmp / "j1.json", doc))
        self.assertEqual(code, 1)
        self.assertEqual(statuses(out, "chain"), ["FAIL"])
        doc = self._chain()
        del doc["events"][2]
        code, out, _ = run("receipt", write_json(self.tmp / "j2.json", doc))
        self.assertEqual(code, 1)
        self.assertEqual(statuses(out, "chain"), ["FAIL"])

    def test_duplicate_json_key_rejected(self):
        p = self.tmp / "dup.json"
        p.write_text('{"status": "ok", "status": "forged"}')
        code, out, _ = run("receipt", p)
        self.assertEqual(code, 1)
        self.assertEqual(statuses(out, "json"), ["FAIL"])

    def test_reference_mismatch(self):
        d = self.tmp / "r"
        d.mkdir()
        (d / "out.txt").write_bytes(b"changed\n")
        write_json(d / "receipt.json", {"outputs": [{"path": "out.txt", "sha256": sha(b"original\n")}]})
        code, out, _ = run("receipt", d / "receipt.json")
        self.assertEqual(code, 1)
        self.assertEqual(statuses(out, "references"), ["FAIL"])

    # ---- decision proofs -------------------------------------------------
    def test_wrong_key(self):
        p, _, _, _ = self.proof_file()
        _, other_pub, other_fp = disposable_keypair(self.tmp, "OTHER-DISPOSABLE-KEY")
        code, out, _ = run("decision", p, "--public-key", other_pub, "--key-sha256", other_fp)
        self.assertEqual(code, 1)
        self.assertIn("FAIL", statuses(out, "signature"))
        self.assertNotIn("PASS", statuses(out, "event-signatures"))

    def test_fingerprint_mismatch_and_prefix_refused(self):
        p, pub, fp, _ = self.proof_file()
        code, _, err = run("decision", p, "--public-key", pub, "--key-sha256", "ab" * 32)
        self.assertEqual(code, 2)
        self.assertIn("does NOT match the fingerprint", err)
        code, _, _ = run("decision", p, "--public-key", pub, "--key-sha256", fp[:8])
        self.assertEqual(code, 2)

    def test_tampered_outcome(self):
        p, pub, fp, _ = self.proof_file()
        proof = json.loads(p.read_text())
        proof["journal"]["events"][2]["payload"]["outcome"] = "reject"
        code, out, _ = run("decision", write_json(p, proof), "--public-key", pub, "--key-sha256", fp)
        self.assertEqual(code, 1)
        self.assertIn("FAIL", statuses(out, "self-digest"))

    def test_reordered_journal(self):
        p, pub, fp, _ = self.proof_file()
        proof = json.loads(p.read_text())
        ev = proof["journal"]["events"]
        ev[0], ev[1] = ev[1], ev[0]
        code, out, _ = run("decision", write_json(p, proof), "--public-key", pub, "--key-sha256", fp)
        self.assertEqual(code, 1)
        self.assertEqual(statuses(out, "chain"), ["FAIL"])

    def test_stale_head_and_wrong_decision(self):
        p, pub, fp, _ = self.proof_file()
        code, out, _ = run("decision", p, "--public-key", pub, "--key-sha256", fp, "--expected-head", "ab" * 32)
        self.assertEqual(code, 1)
        self.assertEqual(statuses(out, "journal-head-expected"), ["FAIL"])
        code, out, _ = run("decision", p, "--public-key", pub, "--key-sha256", fp, "--decision-sha256", "cd" * 32)
        self.assertEqual(code, 1)
        code, out, _ = run("decision", p, "--public-key", pub, "--key-sha256", fp, "--expect-bound", f"receipt={'33' * 32}")
        self.assertEqual(code, 1)

    def test_superseded_decision(self):
        def add_later(events):
            later = copy.deepcopy(events[2])
            later["payload"]["outcome"] = "reject"
            later["occurred_at"] = "2026-11-01T10:07:00+00:00"
            events.append(later)
        priv, pub, fp = disposable_keypair(self.tmp)
        p = write_json(self.tmp / "proof.json", make_proof(priv, fp, add_later, decision_index=2))
        code, out, _ = run("decision", p, "--public-key", pub, "--key-sha256", fp)
        self.assertEqual(code, 1)
        self.assertIn("superseded", json.dumps(out))

    def test_private_key_file_refused(self):
        fake = self.tmp / "not-a-real-key.pem"
        fake.write_text("-----BEGIN PRIVATE KEY-----\nTk9UIEEgUkVBTCBLRVk=\n-----END PRIVATE KEY-----\n")
        code, _, err = run("keyinfo", fake)
        self.assertEqual(code, 2)
        self.assertIn("PRIVATE", err)


# --------------------------------------------------------------------------
# Hardening: findings disclosed in PR #491
# --------------------------------------------------------------------------
class ExtraFileFullHash(Tmp):
    """Finding: an unlisted file was accepted on a 16-hex-character prefix match."""

    def test_byte_identical_copy_accepted(self):
        d = self.evidence()
        shutil.copy(d / "a.txt", d / "copy-of-a.txt")
        code, out, _ = run("manifest", d, "--manifest", d / "SHA256SUMS")
        self.assertEqual(code, 0, out)
        self.assertEqual(statuses(out, "manifest-extra"), ["PASS"])

    def test_prefix_collision_is_rejected(self):
        d = self.evidence()
        (d / "extra.bin").write_bytes(b"different bytes")
        real = lv.sha256_file
        listed = sha((d / "a.txt").read_bytes())

        def fake(path):  # simulate a file sharing the first 64 bits of a verified hash
            digest, n = real(path)
            return (listed[:16] + "f" * 48, n) if Path(path).name == "extra.bin" else (digest, n)

        with mock.patch.object(lv, "sha256_file", fake):
            code, out, _ = run_inproc("manifest", d)
        self.assertEqual(code, 1)
        extra = [r for r in out["results"] if r["check"] == "manifest-extra"]
        self.assertEqual([(r["subject"], r["status"]) for r in extra], [("extra.bin", "FAIL")])


class DeciderIdentity(Tmp):
    """Finding: actor/channel validation was a deny-list and accepted missing values."""

    def decide(self, mutate):
        p, pub, fp, _ = self.proof_file(mutate)
        return run("decision", p, "--public-key", pub, "--key-sha256", fp)

    @staticmethod
    def on_decider(fn):
        def mutate(events):
            for ev in events[1:]:
                fn(ev)
                if isinstance(ev["payload"].get("actor"), dict):
                    fn({"actor": ev["payload"]["actor"], "payload": ev["payload"]})
        return mutate

    def assertSemanticsFail(self, mutate, needle):
        code, out, err = self.decide(mutate)
        self.assertClean(err)
        self.assertEqual(code, 1, out)
        sem = [r for r in out["results"] if r["check"] == "decision-semantics"]
        self.assertEqual([r["status"] for r in sem], ["FAIL"])
        self.assertIn(needle, sem[0]["detail"])

    def test_agent_and_service_refused(self):
        for kind in ("agent", "service"):
            with self.subTest(kind=kind):
                self.assertSemanticsFail(self.on_decider(lambda e, k=kind: e["actor"].__setitem__("kind", k)), "decider kind")

    def test_unknown_or_missing_kind_refused(self):
        self.assertSemanticsFail(self.on_decider(lambda e: e["actor"].__setitem__("kind", "robot")), "decider kind")
        self.assertSemanticsFail(self.on_decider(lambda e: e["actor"].pop("kind")), "decider kind")

    def test_customer_kind_accepted(self):
        code, out, _ = self.decide(self.on_decider(lambda e: e["actor"].__setitem__("kind", "customer")))
        self.assertEqual(code, 0, out)

    def test_missing_actor_id_refused(self):
        self.assertSemanticsFail(self.on_decider(lambda e: e["actor"].__setitem__("id", "")), "actor.id")

    def test_channel_must_be_control_tower(self):
        self.assertSemanticsFail(lambda ev: ev[2]["payload"].pop("channel"), "channel")
        self.assertSemanticsFail(lambda ev: ev[2]["payload"].__setitem__("channel", "api"), "channel")

    def test_roles_required(self):
        self.assertSemanticsFail(lambda ev: ev[2]["payload"].__setitem__("roles_held", []), "roles_held")

    def test_session_must_be_opened_first(self):
        self.assertSemanticsFail(lambda ev: ev.pop(1), "not opened exactly once")

    def test_session_opened_by_someone_else(self):
        other = {"id": "reviewer-2", "kind": "human", "name": "Reviewer Two"}
        self.assertSemanticsFail(lambda ev: ev[1].__setitem__("actor", dict(other)), "different identity")

    def test_decision_after_session_expiry(self):
        self.assertSemanticsFail(lambda ev: ev[2].__setitem__("occurred_at", "2026-11-01T12:00:00+00:00"), "outside its session")

    def test_synthetic_fixture_flagged(self):
        p, pub, fp, _ = self.proof_file(lambda ev: ev[2]["payload"].__setitem__("reason", "TEST FIXTURE only"))
        code, out, _ = run("decision", p, "--public-key", pub, "--key-sha256", fp)
        self.assertEqual(code, 0, out)
        self.assertEqual(statuses(out, "synthetic-fixture"), ["WARN"])
        self.assertEqual(run("decision", p, "--public-key", pub, "--key-sha256", fp, "--strict")[0], 3)


@unittest.skipIf(os.name == "nt", "symlink creation needs privileges on Windows")
class SymlinksAndRestrictedPaths(Tmp):
    """Finding: symlinks were followed in some places, and the restricted-path
    guard was applied inconsistently."""

    def test_listed_file_that_is_a_symlink_fails(self):
        d = self.evidence()
        (self.tmp / "outside.txt").write_bytes(b"alpha\n")
        (d / "a.txt").unlink()
        (d / "a.txt").symlink_to(self.tmp / "outside.txt")
        code, out, _ = run("manifest", d)
        self.assertEqual(code, 1)
        self.assertEqual(statuses(out, "manifest-symlink"), ["FAIL"])

    def test_symlinked_directory_in_path_fails(self):
        d = self.evidence()
        shutil.move(str(d / "sub"), str(self.tmp / "real-sub"))
        (d / "sub").symlink_to(self.tmp / "real-sub", target_is_directory=True)
        code, out, _ = run("manifest", d)
        self.assertEqual(code, 1)
        self.assertIn("FAIL", statuses(out, "manifest-symlink"))

    def test_unlisted_symlink_is_an_extra(self):
        d = self.evidence()
        (d / "link").symlink_to(d / "a.txt")
        code, out, _ = run("manifest", d)
        self.assertEqual(code, 1)
        self.assertEqual(statuses(out, "manifest-extra"), ["FAIL"])

    def test_all_does_not_follow_symlinks(self):
        d = self.evidence()
        (self.tmp / "hostile.json").write_text("{ not json")
        (d / "link.json").symlink_to(self.tmp / "hostile.json")
        code, out, _ = run("all", d)
        self.assertNotEqual(out["verdict"], "FAIL", out)
        self.assertEqual(statuses(out, "symlink"), ["SKIP"])
        self.assertNotIn("json", [r["check"] for r in out["results"]])

    def test_named_symlink_refused(self):
        p, _, _, _ = self.proof_file()
        (self.tmp / "link.json").symlink_to(p)
        code, _, err = run("receipt", self.tmp / "link.json")
        self.assertEqual(code, 2)
        self.assertIn("symbolic link", err)

    def test_md_link_through_symlink_skipped(self):
        d = self.evidence()
        (d / "ln.txt").symlink_to(d / "a.txt")
        (d / "README.md").write_text(f"[x](ln.txt#sha256={sha(b'alpha')})\n")
        code, out, _ = run("all", d)
        self.assertEqual(statuses(out, "md-link"), ["SKIP"])

    def _with_arrivals(self, parts=("work", "mainframe", "arrivals"), name="root"):
        root = self.evidence(name)
        arr = root.joinpath(*parts)
        arr.mkdir(parents=True)
        (arr / "secret.json").write_text("CONFIDENTIAL - not json")
        return root, arr

    def test_arrivals_never_read_by_all(self):
        for i, parts in enumerate((("work", "mainframe", "arrivals"), ("Work", "MAINFRAME", "Arrivals"),
                                   ("work", "mainframe", "arrivals. "))):
            with self.subTest(parts=parts):
                root, _ = self._with_arrivals(parts, f"root{i}")
                code, out, _ = run("all", root)
                self.assertNotEqual(out["verdict"], "FAIL", out)
                self.assertNotIn("arrivals", json.dumps(out).lower())

    def test_arrivals_refused_when_named(self):
        root, arr = self._with_arrivals()
        self.assertEqual(run("receipt", arr / "secret.json")[0], 2)
        self.assertEqual(run("all", arr)[0], 2)
        self.assertEqual(run("manifest", arr)[0], 2)

    def test_symlink_into_arrivals_not_followed(self):
        root, arr = self._with_arrivals()
        ev = self.evidence("pub")
        (ev / "x.json").symlink_to(arr / "secret.json")
        code, out, _ = run("all", ev)
        self.assertEqual(statuses(out, "symlink"), ["SKIP"])
        self.assertNotIn("CONFIDENTIAL", json.dumps(out))

    def test_manifest_listing_arrivals_fails(self):
        root, _ = self._with_arrivals()
        (root / "SHA256SUMS").write_text(sums([("work/mainframe/arrivals/secret.json", "00" * 32)]))
        code, out, _ = run("manifest", root, "--manifest", root / "SHA256SUMS", "--allow-extra", "*")
        self.assertEqual(code, 1)
        self.assertEqual(statuses(out, "manifest-restricted"), ["FAIL"])


class MalformedInput(Tmp):
    """Finding: malformed input could escape as a traceback instead of a clear
    FAIL (exit 1) or input error (exit 2)."""

    def assertFailNoTraceback(self, *args):
        code, out, err = run(*args)
        self.assertClean(err)
        self.assertEqual(code, 1, (out, err))
        return out

    def test_non_object_and_odd_json(self):
        for i, text in enumerate(('[1, 2, 3]', '"just a string"', '{"signature": {"algorithm": "Ed25519", "key_id": [1]}}',
                                  '{"events": [{"content_sha256": "x", "previous_sha256": null, "sequence": [1]}]}')):
            with self.subTest(text=text):
                code, out, err = run("receipt", write_json(self.tmp / f"odd{i}.json", json.loads(text)))
                self.assertClean(err)
                self.assertIn(code, (1, 3), (out, err))

    def test_deeply_nested_json(self):
        p = self.tmp / "deep.json"
        p.write_text("[" * 100000 + "]" * 100000)
        out = self.assertFailNoTraceback("receipt", p)
        self.assertEqual(statuses(out, "json"), ["FAIL"])
        p.write_text("[" * 300 + "]" * 300)
        out = self.assertFailNoTraceback("receipt", p)
        self.assertEqual(statuses(out, "json"), ["FAIL"])

    def test_invalid_utf8_and_nan(self):
        (self.tmp / "bad.json").write_bytes(b'{"a": "\xff"}')
        self.assertFailNoTraceback("receipt", self.tmp / "bad.json")
        (self.tmp / "nan.json").write_text('{"a": NaN}')
        self.assertFailNoTraceback("receipt", self.tmp / "nan.json")

    def test_malformed_proofs(self):
        priv, pub, fp = disposable_keypair(self.tmp)
        dsha = "aa" * 32
        bad = [
            {"schema": "tower-decision-proof/1", "decision_sha256": dsha, "journal": {"events": [
                {"kind": "tower_decision", "content_sha256": dsha, "sequence": "x", "payload": []}]}},
            {"schema": "tower-decision-proof/1", "decision_sha256": dsha, "journal": {"events": "nope"}},
            {"schema": "tower-decision-proof/1", "decision_sha256": dsha, "journal": {"events": [1, None, "x"],
                                                                                        "signature": "x"}},
            {"schema": "tower-decision-proof/1", "decision_sha256": dsha, "journal": []},
        ]
        for i, proof in enumerate(bad):
            with self.subTest(i=i):
                self.assertFailNoTraceback("decision", write_json(self.tmp / f"bad{i}.json", proof),
                                           "--public-key", pub, "--key-sha256", fp)

    def test_every_type_swap_in_a_proof_fails(self):
        """Adversarial sweep: replace each value in a valid proof with each other
        JSON type.  Every variant must FAIL (exit 1): never PASS, never crash."""
        priv, pub, fp = disposable_keypair(self.tmp)
        good = make_proof(priv, fp)
        paths = []

        def collect(o, path):
            if path:
                paths.append(path)
            if isinstance(o, dict):
                for k, v in o.items():
                    collect(v, path + [k])
            elif isinstance(o, list):
                for i, v in enumerate(o):
                    collect(v, path + [i])
        collect(good, [])
        replacements = [None, True, 7, "x", [], {}]
        p = self.tmp / "fuzz.json"
        tried = 0
        for path in paths:
            for rep in replacements:
                bad = copy.deepcopy(good)
                parent = bad
                for k in path[:-1]:
                    parent = parent[k]
                if type(parent[path[-1]]) is type(rep):
                    continue
                parent[path[-1]] = rep
                p.write_text(json.dumps(bad))
                code, out, err = run_inproc("decision", p, "--public-key", pub, "--key-sha256", fp)
                tried += 1
                self.assertEqual(code, 1, (path, rep, err, out and out["summary"]))
        self.assertGreater(tried, 300)

    def test_input_errors_exit_2(self):
        d = self.evidence()
        p, pub, fp, _ = self.proof_file()
        for args in (("receipt", self.tmp / "missing.json"),
                     ("manifest", self.tmp / "no-such-dir"),
                     ("all", self.tmp / "no-such-dir"),
                     ("manifest", d, "--manifest", self.tmp / "missing-sums"),
                     ("decision", p, "--public-key", pub, "--key-sha256", fp, "--expect-bound", "no-equals-sign"),
                     ("receipt", p, "--trust-key", "no-equals-sign"),
                     ("manifest", d, "--max-json-mb", "0")):
            with self.subTest(args=args[:2]):
                code, _, err = run(*args)
                self.assertClean(err)
                self.assertEqual(code, 2, err)


class ResourceLimits(Tmp):
    """Finding: JSON and archive reads were unbounded, and duplicate archive
    members were not detected."""

    def test_oversized_json_named_explicitly_fails(self):
        p = self.tmp / "big.json"
        p.write_text(json.dumps({"pad": "x" * (2 << 20)}))
        code, out, err = run("receipt", p, "--max-json-mb", "1")
        self.assertClean(err)
        self.assertEqual(code, 1)
        self.assertEqual(statuses(out, "limits"), ["FAIL"])

    def test_oversized_json_in_walk_is_skipped(self):
        d = self.evidence()
        (d / "big.json").write_text(json.dumps({"pad": "x" * (2 << 20)}))
        code, out, _ = run("all", d, "--max-json-mb", "1")
        self.assertNotEqual(out["verdict"], "FAIL", out)
        self.assertEqual(statuses(out, "limits"), ["SKIP"])

    def test_archive_member_count_limit(self):
        d = self.tmp / "rel"
        d.mkdir()
        with zipfile.ZipFile(d / "many.zip", "w") as z:
            for i in range(20):
                z.writestr(f"f{i}.txt", b"x")
        (d / "SHA256SUMS").write_text(sums([("f0.txt", sha(b"x"))]))
        code, out, _ = run("manifest", d, "--manifest", d / "SHA256SUMS", "--allow-extra", "*.zip", "--max-archive-members", "10")
        self.assertEqual(code, 1)
        missing = [r for r in out["results"] if r["check"] == "manifest-missing"]
        self.assertIn("refused", missing[0]["detail"])

    def test_decompression_bomb_refused_before_expansion(self):
        d = self.tmp / "rel"
        d.mkdir()
        zeros = b"\0" * (3 << 20)
        with zipfile.ZipFile(d / "bomb.zip", "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("zeros.bin", zeros)
        self.assertLess((d / "bomb.zip").stat().st_size, 64 << 10)
        (d / "SHA256SUMS").write_text(sums([("zeros.bin", sha(zeros))]))
        code, out, _ = run("manifest", d, "--manifest", d / "SHA256SUMS", "--allow-extra", "*.zip", "--max-archive-mb", "1")
        self.assertEqual(code, 1)
        self.assertIn("declares more than", json.dumps(out))
        self.assertEqual(run("manifest", d, "--manifest", d / "SHA256SUMS", "--allow-extra", "*.zip")[0], 0)

    def test_duplicate_zip_member(self):
        d = self.tmp / "rel"
        d.mkdir()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with zipfile.ZipFile(d / "dup.zip", "w") as z:
                z.writestr("x.txt", b"good")
                z.writestr("x.txt", b"evil")
        (d / "SHA256SUMS").write_text(sums([("x.txt", sha(b"good"))]))
        code, out, _ = run("manifest", d, "--allow-extra", "*.zip")
        self.assertEqual(code, 1)
        self.assertEqual(statuses(out, "archive-duplicate"), ["FAIL"])

    def test_appended_duplicate_tar_member(self):
        d = self.tmp / "rel"
        d.mkdir()
        with tarfile.open(d / "cap.tar", "w") as t:
            for data in (b"good", b"evil"):  # classic append-to-replace attack
                info = tarfile.TarInfo("home/x.txt")
                info.size = len(data)
                t.addfile(info, io.BytesIO(data))
        (d / "SHA256SUMS").write_text(sums([("home/x.txt", sha(b"good"))]))
        code, out, _ = run("manifest", d, "--allow-extra", "*.tar")
        self.assertEqual(code, 1)
        self.assertEqual(statuses(out, "archive-duplicate"), ["FAIL"])

    def test_corrupt_archive_is_not_silently_ignored(self):
        d = self.tmp / "rel"
        d.mkdir()
        (d / "broken.zip").write_bytes(b"PK\x03\x04 not really a zip")
        (d / "SHA256SUMS").write_text(sums([("x.txt", sha(b"x"))]))
        code, out, _ = run("manifest", d, "--manifest", d / "SHA256SUMS", "--allow-extra", "*.zip")
        self.assertEqual(code, 1)
        self.assertIn("broken.zip refused", json.dumps(out))
        code, out, _ = run("manifest", d, "--allow-extra", "*.zip")  # auto-discovered: SKIP that names the refusal
        self.assertEqual(code, 3)
        self.assertIn("broken.zip refused", json.dumps(out))


class CoverageVerdicts(Tmp):
    """Finding: a PASS verdict could have zero successful checks."""

    def test_empty_directory_is_incomplete(self):
        d = self.tmp / "empty"
        d.mkdir()
        code, out, _ = run("all", d)
        self.assertEqual(code, 3)
        self.assertEqual(out["verdict"], "INCOMPLETE")
        self.assertEqual(out["summary"]["verified"], 0)

    def test_nothing_recognisable_is_incomplete(self):
        d = self.tmp / "docs"
        d.mkdir()
        (d / "README.md").write_text("no evidence links here\n")
        write_json(d / "plain.json", {"hello": "world"})
        self.assertEqual(run("all", d)[0], 3)

    def test_receipt_with_nothing_to_verify_is_incomplete(self):
        code, out, _ = run("receipt", write_json(self.tmp / "plain.json", {"hello": "world"}))
        self.assertEqual(code, 3)
        self.assertEqual(statuses(out, "json"), ["PASS"])  # parsing alone is not verification

    def test_manifest_describing_elsewhere_is_incomplete(self):
        d = self.tmp / "ev"
        d.mkdir()
        (d / "SHA256SUMS").write_text(sums([("release-asset.zip", "00" * 32)]))
        self.assertEqual(run("manifest", d)[0], 3)

    def test_private_key_in_evidence_fails(self):
        d = self.evidence()
        (d / "leaked.pem").write_text("-----BEGIN PRIVATE KEY-----\nTk9UIEEgUkVBTCBLRVk=\n-----END PRIVATE KEY-----\n")
        code, out, _ = run("all", d)
        self.assertEqual(code, 1)
        self.assertEqual(statuses(out, "private-key"), ["FAIL"])


class OptionalCryptography(Tmp):
    """Finding: cryptography was required at startup even for manifest-only work."""

    def test_manifest_runs_without_cryptography(self):
        d = self.evidence()
        code, out, err = run("manifest", d, "--manifest", d / "SHA256SUMS", block_crypto=True)
        self.assertEqual(code, 0, (out, err))

    def test_all_reports_signatures_as_skipped(self):
        d = self.evidence()
        priv, _, fp = disposable_keypair(self.tmp)
        write_json(d / "receipt.json", seal({"schema": "public-operational-receipt/1"}, priv, fp))
        code, out, err = run("all", d, block_crypto=True)
        self.assertClean(err)
        self.assertEqual(code, 3, out)
        self.assertEqual(out["verdict"], "UNANCHORED")
        self.assertTrue(any("cryptography" in n for n in out["notes"]))
        self.assertIn("SKIP", statuses(out, "receipt"))

    def test_signature_commands_need_it(self):
        p, pub, fp, _ = self.proof_file()
        for args in (("decision", p, "--public-key", pub, "--key-sha256", fp), ("keyinfo", pub),
                     ("receipt", p, "--trust-key", f"{pub}={fp}")):
            with self.subTest(cmd=args[0]):
                code, _, err = run(*args, block_crypto=True)
                self.assertEqual(code, 2)
                self.assertIn("cryptography", err)
                self.assertClean(err)


class IndependentReviewFindings(Tmp):
    """Attacks found by an independent adversarial review of v1.1.0's first draft."""

    def test_self_digest_alone_is_not_a_pass(self):
        priv, pub, fp = disposable_keypair(self.tmp)
        forged = digest_only({"schema": "public-operational-receipt/1", "approved": True})
        code, out, _ = run("receipt", write_json(self.tmp / "f.json", forged), "--trust-key", f"{pub}={fp}", "--strict")
        self.assertEqual(code, 3)
        self.assertEqual(out["verdict"], "UNANCHORED")

    def test_signature_with_algorithm_removed_fails(self):
        priv, pub, fp = disposable_keypair(self.tmp)
        doc = seal({"schema": "public-operational-receipt/1", "approved": False}, priv, fp)
        doc["approved"] = True
        del doc["signature"]["algorithm"]
        digest_only(doc)
        code, out, _ = run("receipt", write_json(self.tmp / "t.json", doc), "--trust-key", f"{pub}={fp}")
        self.assertEqual(code, 1)
        self.assertIn("FAIL", statuses(out, "signature"))

    def test_all_does_not_accept_an_unauthenticated_proof(self):
        d = self.evidence()
        attacker, _, afp = disposable_keypair(self.tmp, "ATTACKER")
        write_json(d / "proof.json", make_proof(attacker, afp))
        code, out, _ = run("all", d)
        self.assertNotIn("PASS", statuses(out, "decision-semantics"))
        self.assertNotEqual(code, 0)
        _, real_pub, real_fp = disposable_keypair(self.tmp, "REAL")
        code, out, _ = run("all", d, "--trust-key", f"{real_pub}={real_fp}")
        self.assertEqual(code, 1)
        self.assertEqual(statuses(out, "decision-key"), ["FAIL"])

    def test_sibling_claimed_digest_is_not_trusted(self):
        d = self.tmp / "run"
        d.mkdir()
        h = "ab" * 32
        write_json(d / "authorization.json", {"content_sha256": h, "authorized_by": "EDITED"})
        write_json(d / "run.json", {"authorization_sha256": h})
        code, out, _ = run("receipt", d / "run.json")
        self.assertEqual(code, 1)
        self.assertEqual(statuses(out, "binding"), ["FAIL"])

    def test_uppercase_digests_cannot_skip_the_check(self):
        events, prev = [], lv.ZERO
        for i in range(1, 4):
            e = {"sequence": i, "previous_sha256": prev, "type": "edited", "content_sha256": f"{i:X}" * 64}
            events.append(e)
            prev = e["content_sha256"]
        code, out, _ = run("receipt", write_json(self.tmp / "j.json", {"events": events}), "--strict")
        self.assertEqual(code, 1)
        self.assertIn("FAIL", statuses(out, "self-digest"))

    def test_tar_name_aliases_are_duplicates(self):
        for alias in ("./a.txt", "/a.txt", "x/../a.txt"):
            with self.subTest(alias=alias):
                d = self.tmp / f"t{len(alias)}"
                d.mkdir()
                with tarfile.open(d / "cap.tar", "w") as t:
                    for name, data in (("a.txt", b"good"), (alias, b"evil")):
                        info = tarfile.TarInfo(name)
                        info.size = len(data)
                        t.addfile(info, io.BytesIO(data))
                (d / "SHA256SUMS").write_text(sums([("a.txt", sha(b"good"))]))
                code, out, _ = run("manifest", d, "--manifest", d / "SHA256SUMS", "--allow-extra", "*.tar")
                self.assertEqual(code, 1)
                self.assertEqual(statuses(out, "archive-duplicate"), ["FAIL"])

    def test_session_rules(self):
        def no_expiry(ev):
            ev[1]["payload"].pop("expires_at")

        def ended(ev):
            ev.insert(2, event("session_ended", HUMAN, SID, "2026-11-01T10:02:00+00:00", {}))

        def before_start(ev):
            ev[2]["occurred_at"] = "2026-11-01T09:00:00+00:00"

        def ungranted_role(ev):
            ev[2]["payload"]["roles_held"] = ["approver", "release-owner"]

        def grant_replaced(ev):  # Tower's rule: the latest grant is the one in force
            ev.insert(1, event("roles_assigned", ADMIN, None, "2026-11-01T10:00:30+00:00",
                               {"actor_id": "reviewer-1", "roles": ["viewer"], "scope": SCOPE, "reason": "Reduced"}))

        for mutate, needle in ((no_expiry, "expires_at"), (ended, "already ended"), (before_start, "outside its session"),
                               (ungranted_role, "latest grant"), (grant_replaced, "latest grant")):
            with self.subTest(case=mutate.__name__):
                p, pub, fp, _ = self.proof_file(mutate, name=f"{mutate.__name__}.json")
                code, out, _ = run("decision", p, "--public-key", pub, "--key-sha256", fp)
                self.assertEqual(code, 1, out)
                sem = [r for r in out["results"] if r["check"] == "decision-semantics"]
                self.assertIn(needle, sem[0]["detail"])

    def test_oversized_pax_header_refused(self):
        d = self.tmp / "rel"
        d.mkdir()
        with tarfile.open(d / "pax.tar", "w", format=tarfile.PAX_FORMAT) as t:
            info = tarfile.TarInfo("a.txt")
            info.size = 4
            info.pax_headers = {"comment": "x" * (2 << 20)}
            t.addfile(info, io.BytesIO(b"good"))
        (d / "SHA256SUMS").write_text(sums([("a.txt", sha(b"good"))]))
        code, out, err = run("manifest", d, "--manifest", d / "SHA256SUMS", "--allow-extra", "*.tar")
        self.assertClean(err)
        self.assertEqual(code, 1)
        self.assertIn("extended header", json.dumps(out))

    def test_member_decompressed_once_per_run(self):
        d = self.tmp / "rel"
        d.mkdir()
        with zipfile.ZipFile(d / "bundle.zip", "w") as z:
            z.writestr("x.txt", b"data")
        # 31 names that all resolve to the same member (directly, or via the archive-name rule)
        names = [("x.txt", sha(b"data"))] + [(f"p{i}/bundle/x.txt", sha(b"data")) for i in range(30)]
        (d / "SHA256SUMS").write_text(sums(names))
        calls = []
        real = lv._open_member

        def counting(*a):
            calls.append(a[1])
            return real(*a)

        with mock.patch.object(lv, "_open_member", counting):
            code, out, _ = run_inproc("manifest", d, "--manifest", d / "SHA256SUMS", "--allow-extra", "*.zip")
        self.assertEqual(code, 0, out)
        self.assertEqual(len(calls), 1)

    def test_long_nested_keys_keep_labels_short(self):
        doc = {"content_sha256": "00" * 32}
        for i in range(200):
            doc = {("k" * 2000) + str(i): doc}
        code, out, err = run("receipt", write_json(self.tmp / "n.json", doc))
        self.assertClean(err)
        self.assertLess(max(len(r["subject"]) for r in out["results"]), 400)

    def test_digest_at_every_level_is_bounded(self):
        doc = {"pad": "x" * 20000, "content_sha256": "00" * 32}
        for _ in range(150):
            doc = {"child": doc, "pad": "y" * 20000, "content_sha256": "00" * 32}
        code, out, err = run("receipt", write_json(self.tmp / "deep.json", doc))
        self.assertClean(err)
        self.assertEqual(code, 1)
        self.assertEqual(statuses(out, "limits"), ["FAIL"])

    def test_lone_surrogate_in_text_mode(self):
        p = self.tmp / "s.json"
        p.write_text('{"schema": "\\ud800", "content_sha256": "' + "00" * 32 + '"}')
        code, _, err = run("receipt", p, json_out=False)
        self.assertClean(err)
        self.assertIn(code, (1, 3))

    @unittest.skipIf(os.name == "nt", "POSIX links")
    def test_links_refused(self):
        root = self.evidence("root")
        arr = root / "work" / "mainframe" / "arrivals"
        arr.mkdir(parents=True)
        (arr / "secret.json").write_text('{"note": "CONFIDENTIAL"}')
        pub = self.evidence("pub")
        os.link(arr / "secret.json", pub / "alias.json")
        code, out, _ = run("all", pub)
        self.assertEqual(statuses(out, "hardlink"), ["SKIP"])
        self.assertNotIn("CONFIDENTIAL", json.dumps(out))
        self.assertEqual(run("receipt", pub / "alias.json")[0], 2)
        (self.tmp / "dirlink").symlink_to(pub, target_is_directory=True)
        self.assertEqual(run("manifest", self.tmp / "dirlink")[0], 2)

    def test_injected_file_quoting_trusted_manifest_fails(self):
        d = self.evidence()
        h = sha((d / "SHA256SUMS").read_bytes())
        write_json(d / "board-approval.json", {"approved": True, "manifest_sha256": h})
        code, out, _ = run("manifest", d, "--manifest", d / "SHA256SUMS")
        self.assertEqual(code, 1)
        self.assertEqual(statuses(out, "manifest-extra"), ["FAIL"])

    def test_unsupported_zip_method_does_not_abort_the_run(self):
        d = self.evidence()
        with zipfile.ZipFile(d / "odd.zip", "w") as z:
            z.writestr("m.txt", b"member")
        raw = bytearray((d / "odd.zip").read_bytes())
        raw[8:10] = (99).to_bytes(2, "little")
        c = raw.index(b"PK\x01\x02")
        raw[c + 10:c + 12] = (99).to_bytes(2, "little")
        (d / "odd.zip").write_bytes(bytes(raw))
        (d / "MEMBERS.sha256").write_text(sums([("m.txt", sha(b"member"))]))
        code, out, err = run("all", d)
        self.assertClean(err)
        self.assertEqual(code, 1, err)
        self.assertIn("PASS", statuses(out, "manifest"))  # the other manifest was still checked


class SourceProperties(unittest.TestCase):
    def test_no_network_or_subprocess_imports(self):
        import ast
        tree = ast.parse(VERIFIER.read_text())
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names |= {a.name for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                names.add(node.module or "")
        banned = {"subprocess", "socket", "ssl", "http", "http.client", "urllib.request", "ftplib", "smtplib", "ctypes"}
        self.assertFalse(names & banned, names & banned)
        self.assertNotIn("followlinks=True", VERIFIER.read_text())


if __name__ == "__main__":
    unittest.main(verbosity=2)
