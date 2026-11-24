"""Linux CI regression for the real durable ledger fill and duplicate checks."""
from pathlib import Path
import tempfile
import time
import unittest

from tools.v1_mac_worker import ledger_probe


class LedgerProbeTests(unittest.TestCase):
    def test_fills_both_caps_with_storage_probe(self):
        # The durable ports reject writable ancestors, including the system tmp directory.
        with tempfile.TemporaryDirectory(dir=Path.home().resolve()) as temp:
            run = Path(temp)
            parent = run / "ledger"
            parent.mkdir(mode=0o700)
            operation = "a" * 64
            receipt = ledger_probe(run, operation, time.monotonic() + 300)

            leaves = list((parent / ("public-repair-" + operation)).iterdir())
            self.assertTrue(any(path.name == "record-storage-probe.json" for path in leaves))
            self.assertEqual(len(leaves), 512)
            self.assertEqual(sum(path.stat().st_size for path in leaves), 67_108_864)
            self.assertEqual(receipt["file_count"], 512)
            self.assertEqual(receipt["bytes"], 67_108_864)
            self.assertEqual(receipt["duplicate_refusal"]["refusal_code"], "durable-exclusive")
