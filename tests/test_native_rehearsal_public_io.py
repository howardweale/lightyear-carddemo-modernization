"""CI-only public bytes and metadata fixtures; no hardware/private operations."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import native_rehearsal_public_io as io


class PublicIOTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.raw = b"PUBLIC NO-KEY fixture\n"
        self.source = self.root / "public fixture.txt"
        self.source.write_bytes(self.raw)
        self.sha = hashlib.sha256(self.raw).hexdigest()

    def test_same_copy_operation_preserves_spaces_bytes_and_refuses_collision(self):
        destination = self.root / "public return.bin"
        result = io.copy_public(self.source, destination, self.sha, len(self.raw))
        self.assertEqual(self.sha, result["sha256"])
        before = destination.stat()
        with self.assertRaises(FileExistsError):
            io.copy_public(self.source, destination, self.sha, len(self.raw))
        self.assertEqual(self.raw, destination.read_bytes())
        self.assertEqual((before.st_ino, before.st_mtime_ns),
                         (destination.stat().st_ino, destination.stat().st_mtime_ns))

    def test_corruption_wrong_hash_and_wrong_length_create_no_destination(self):
        for raw, digest, size in ((b"X" + self.raw[1:], self.sha, len(self.raw)),
                                  (self.raw, "0" * 64, len(self.raw)),
                                  (self.raw, self.sha, len(self.raw) + 1)):
            self.source.write_bytes(raw)
            destination = self.root / "must remain absent"
            with self.assertRaises(ValueError):
                io.copy_public(self.source, destination, digest, size)
            self.assertFalse(destination.exists())

    def test_alias_and_duplicate_output_refused_without_truncation(self):
        output = self.root / "result.json"
        output.write_bytes(b"retained")
        status = io.main(["compare", "--source", str(self.source), "--sha256", self.sha,
                          "--bytes", str(len(self.raw)), "--output", str(output)])
        self.assertEqual(2, status)
        self.assertEqual(b"retained", output.read_bytes())
        with self.assertRaises(ValueError):
            io.read_public(self.root / ".." / self.root.name / self.source.name)
        if os.name == "posix":
            alias = self.root / "alias"
            alias.symlink_to(self.source)
            with self.assertRaises(ValueError):
                io.read_public(alias)
            broken = self.root / "broken"
            broken.symlink_to(self.root / "absent")
            with self.assertRaises(FileExistsError):
                io.copy_public(self.source, broken, self.sha, len(self.raw))
        else:
            # Windows synthetic reparse metadata control, not real ACL/OS proof.
            meta = self.source.lstat()
            class Reparse:
                st_mode = meta.st_mode
                st_file_attributes = 0x400
            with patch.object(Path, "lstat", return_value=Reparse()):
                with self.assertRaises(ValueError):
                    io.read_public(self.source)

    def test_manifest_is_exact_allowlist_and_rejects_duplicate_traversal_or_changed_file(self):
        manifest = self.root / "manifest.json"
        entry = dict(path=self.source.name, sha256=self.sha, bytes=len(self.raw))
        def invoke(rows):
            raw = json.dumps(dict(schema="native-rehearsal-public-files/1", files=rows)).encode()
            manifest.write_bytes(raw)
            return io.check_manifest(self.root, manifest, hashlib.sha256(raw).hexdigest())
        self.assertEqual(1, len(invoke([entry])["files"]))
        for rows in ([entry, entry], [dict(entry, path="../outside")], [dict(entry, path="/absolute")]):
            with self.assertRaises(ValueError):
                invoke(rows)
        self.source.write_bytes(b"X" + self.raw[1:])
        with self.assertRaises(ValueError):
            invoke([entry])

    def test_baseline_metadata_reads_dist_info_without_importing_sdk(self):
        bundle = self.root / "bundle"
        site = bundle / "site"
        site.mkdir(parents=True)
        executable = bundle / "runtime" / "python"
        executable.parent.mkdir()
        executable.write_bytes(b"public fixture marker, not executable")
        for name, version in io.VERSIONS.items():
            info = site / (name.replace("-", "_") + ".dist-info")
            info.mkdir()
            (info / "METADATA").write_text("Metadata-Version: 2.1\nName: " + name + "\nVersion: " + version + "\n")
        with patch.object(io.sys, "executable", str(executable)), patch.object(io.platform, "python_version", return_value="3.12.16"):
            result = io.runtime_metadata(bundle, site)
            self.assertEqual(io.VERSIONS, result["distributions"])
            self.assertFalse(result["sdk_imported"])
            with patch.object(io.platform, "python_version", return_value="3.13.0"):
                with self.assertRaises(ValueError):
                    io.runtime_metadata(bundle, site)
        # No claim that this metadata fixture verifies a runnable interpreter.

    def journal(self, status="FAIL", cleanup="UNKNOWN", changed_deadline=False):
        metadata = dict(kind="metadata", schema="native-owner-rehearsal/1", native_proof=False)
        intent = dict(kind="intent", case="S7", original_deadline=50, cleanup_deadline=55)
        final = dict(intent, kind="result", status=status, cleanup_status=cleanup, native_proof=False)
        if changed_deadline: final["original_deadline"] = 51
        previous, lines = "0" * 64, []
        for i, event in enumerate((metadata, intent, final), 1):
            raw = json.dumps(dict(sequence=i, previous_sha256=previous, event=event)).encode() + b"\n"
            lines.append(raw)
            previous = hashlib.sha256(raw).hexdigest()
        path = self.root / "events.jsonl"
        path.write_bytes(b"".join(lines))
        return path

    def test_journal_readback_never_upgrades_missing_reap_or_claims_live_verification(self):
        result = io.journal_status(self.journal())
        self.assertEqual("FAIL", result["reported_status"])
        self.assertEqual("UNKNOWN", result["reported_cleanup"])
        self.assertFalse(result["live_processes_checked"])
        self.assertFalse(result["authenticated"])
        with self.assertRaises(ValueError):
            io.journal_status(self.journal(changed_deadline=True))

    def test_truncated_tampered_duplicate_key_and_missing_final_are_not_valid_journals(self):
        path = self.journal()
        original = path.read_bytes()
        for raw in (original[:-1], original.replace(b'"kind": "intent"', b'"kind": "changed"'),
                    b"\n".join(original.splitlines()[:-1]) + b"\n",
                    original.replace(b'"sequence": 1', b'"sequence": 1, "sequence": 1')):
            path.write_bytes(raw)
            with self.assertRaises(ValueError):
                io.journal_status(path)

    def test_self_consistent_chain_is_not_authentication_and_inconsistent_success_refused(self):
        with self.assertRaises(ValueError):
            io.journal_status(self.journal(status="PASS", cleanup="UNKNOWN"))
        # Rewritten final bytes have no following chain link. Never call this
        # authentication or independent cleanup evidence, even when consistent.
        path = self.journal()
        path.write_bytes(path.read_bytes().replace(b'"UNKNOWN"', b'"REAPED"'))
        result = io.journal_status(path)
        self.assertEqual("REAPED", result["reported_cleanup"])
        self.assertFalse(result["authenticated"])
        self.assertFalse(result["live_processes_checked"])
