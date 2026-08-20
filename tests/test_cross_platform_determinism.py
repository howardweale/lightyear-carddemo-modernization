from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from lightyear_common.io import source_hashes, write_text
from lightyear_knowledge_graph.evidence_pack import evidence_pack_hash
from lightyear_knowledge_graph.model import graph_hash


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class CrossPlatformDeterminismTests(unittest.TestCase):
    def test_logical_source_hash_is_stable_across_line_endings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            lf = Path(directory) / "lf.cbl"
            crlf = Path(directory) / "crlf.cbl"
            lf.write_bytes(b"IDENTIFICATION DIVISION.\nPROGRAM-ID. TEST.\n")
            crlf.write_bytes(b"IDENTIFICATION DIVISION.\r\nPROGRAM-ID. TEST.\r\n")

            lf_logical, lf_transport = source_hashes(lf)
            crlf_logical, crlf_transport = source_hashes(crlf)

            self.assertEqual(lf_logical, crlf_logical)
            self.assertNotEqual(lf_transport, crlf_transport)

    def test_transport_observations_do_not_change_semantic_receipt_identity(self) -> None:
        graph = {
            "schema_version": "1.1",
            "nodes": [{"properties": {"transport_content_sha256": "a" * 64}}],
        }
        first = graph_hash({**graph, "content_sha256": "ignored"})
        graph["nodes"][0]["properties"]["transport_content_sha256"] = "b" * 64
        self.assertEqual(first, graph_hash({**graph, "content_sha256": "ignored"}))

        pack = {"capsules": [{"transport_file_sha256": "a" * 64}]}
        first = evidence_pack_hash(pack)
        pack["capsules"][0]["transport_file_sha256"] = "b" * 64
        self.assertEqual(first, evidence_pack_hash(pack))

    def test_deterministic_writer_always_emits_lf(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipt.json"
            write_text(path, "first\nsecond\n")
            self.assertEqual(path.read_bytes(), b"first\nsecond\n")

    def test_every_powershell_entrypoint_uses_shared_runtime(self) -> None:
        entrypoints = sorted(PROJECT_ROOT.glob("*.ps1"))
        self.assertGreater(len(entrypoints), 5)
        for path in entrypoints:
            if path.name == "python-runtime.ps1":
                continue
            content = path.read_text(encoding="utf-8")
            self.assertIn("python-runtime.ps1", content, path.name)
            self.assertNotIn("py -3.11", content, path.name)

    @unittest.skipIf(os.name == "nt", "POSIX executable bits are not meaningful on Windows")
    def test_shell_entrypoints_are_executable(self) -> None:
        scripts = sorted(PROJECT_ROOT.glob("*.sh"))
        self.assertGreater(len(scripts), 5)
        missing = [path.name for path in scripts if not os.access(path, os.X_OK)]
        self.assertEqual([], missing)


if __name__ == "__main__":
    unittest.main()
