"""CI-only synthetic fixtures; never run against an operator workspace."""
import base64
import hashlib
import io
import json
import sqlite3
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
from journal_head import verified_head
from stage_bundle import REPOSITORY, stage, verify_archive
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


class ReviewHelpers(unittest.TestCase):
    def test_journal_chain_key_tamper_gap_and_missing_database(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            key = Ed25519PrivateKey.generate()  # Synthetic CI authority, never operator material.
            pem = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
            public = root / "public.pem"
            public.write_bytes(pem)
            control = root / "work/control-tower"
            database = control / "scopes/factory/decisions.sqlite3"
            database.parent.mkdir(parents=True)
            key_id = hashlib.sha256(pem).hexdigest()
            (control / "workspace-ownership.json").write_text(json.dumps({"scope": "factory", "public_key_sha256": key_id}))
            with self.assertRaises(sqlite3.OperationalError):
                verified_head(root, public)
            self.assertFalse(database.exists())
            with sqlite3.connect(database) as connection:
                connection.execute("CREATE TABLE events(sequence INTEGER PRIMARY KEY,envelope TEXT)")
            with self.assertRaises(ValueError):
                verified_head(root, public)
            previous = "0" * 64
            events = []
            for sequence in (1, 2):
                event = dict(schema_version="1.0", record_type="control-tower-decision-event",
                             sequence=sequence, previous_sha256=previous, payload={"fixture": True})
                raw = json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
                previous = hashlib.sha256(raw).hexdigest()
                event.update(content_sha256=previous, signature=dict(algorithm="Ed25519", key_id=key_id,
                             value=base64.b64encode(key.sign(raw)).decode()))
                events.append(event)
            with sqlite3.connect(database) as connection:
                connection.executemany("INSERT INTO events VALUES(?,?)", [(e["sequence"], json.dumps(e)) for e in events])
            before = database.read_bytes()
            self.assertEqual(verified_head(root, public), previous)
            self.assertEqual(database.read_bytes(), before)
            public.write_bytes(Ed25519PrivateKey.generate().public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
            with self.assertRaises(ValueError):
                verified_head(root, public)
            public.write_bytes(pem)
            for altered in (dict(events[1], previous_sha256="f" * 64), dict(events[1], payload={"tampered": True}),
                            dict(events[1], signature=dict(events[1]["signature"], value=base64.b64encode(b"x" * 64).decode()))):
                with sqlite3.connect(database) as connection:
                    connection.execute("UPDATE events SET envelope=? WHERE sequence=2", (json.dumps(altered),))
                with self.assertRaises(Exception):
                    verified_head(root, public)
            with sqlite3.connect(database) as connection:
                connection.execute("DELETE FROM events WHERE sequence=1")
            with self.assertRaises(ValueError):
                verified_head(root, public)

    def test_archive_inventory_digests_and_no_extraction_on_refusal(self):
        commit = "a" * 40
        manifest = json.dumps(dict(schema="factory-install-bundle/1", source_commit=commit, keys_created=False,
                                   signed_only_activated=False, files=[dict(path="app/value", bytes=2,
                                   sha256=hashlib.sha256(b"ok").hexdigest())])).encode()
        digest = hashlib.sha256(manifest).hexdigest()
        def archive(entries):
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w") as output:
                output.writestr("manifest.json", manifest)
                for name, data in entries:
                    output.writestr(name, data)
            return buffer.getvalue()
        good = archive([("app/value", b"ok")])
        zip_digest = hashlib.sha256(good).hexdigest()
        self.assertEqual(verify_archive(good, commit, digest, zip_digest)["app/value"], b"ok")
        for entries in ([('app/value', b'no')], [('app/value', b'ok'), ('../escape', b'x')],
                        [('app/value', b'ok'), ('extra', b'x')], [('app/value', b'ok'), ('APP/value', b'ok')]):
            raw = archive(entries)
            with self.assertRaises(ValueError):
                verify_archive(raw, commit, digest, hashlib.sha256(raw).hexdigest())
        for expected_commit, expected_manifest, expected_zip in (("b" * 40, digest, zip_digest),
                (commit, "0" * 64, zip_digest), (commit, digest, "0" * 64)):
            with self.assertRaises(ValueError):
                verify_archive(good, expected_commit, expected_manifest, expected_zip)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "new"
            args = SimpleNamespace(commit=commit, stage=target, run_id=1, artifact_id=2,
                                   manifest_sha256=digest, zip_sha256=zip_digest)
            with patch("stage_bundle.gh", return_value=b'{}'), self.assertRaises(KeyError):
                stage(args)
            self.assertFalse(target.exists())
            run = dict(head_sha=commit, status="completed", conclusion="success", event="pull_request",
                       path=".github/workflows/factory-first-install.yml", repository=dict(full_name=REPOSITORY),
                       head_repository=dict(full_name=REPOSITORY))
            artifact = dict(name="factory-first-install-" + commit, expired=False,
                            workflow_run=dict(id=1, head_sha=commit), size_in_bytes=len(good),
                            digest="sha256:" + zip_digest)
            responses = [json.dumps(run).encode(), json.dumps(artifact).encode(), good]
            args.manifest_sha256 = "0" * 64
            with patch("stage_bundle.gh", side_effect=responses), self.assertRaises(ValueError):
                stage(args)
            self.assertFalse(target.exists())
            args.manifest_sha256 = digest
            with patch("stage_bundle.gh", side_effect=responses), patch("builtins.print"):
                stage(args)
            self.assertEqual((target / "app/value").read_bytes(), b"ok")
            self.assertEqual((target / "manifest.json").read_bytes(), manifest)
            with patch("stage_bundle.gh") as network, self.assertRaises(ValueError):
                stage(args)
            network.assert_not_called()


if __name__ == "__main__":
    unittest.main()
