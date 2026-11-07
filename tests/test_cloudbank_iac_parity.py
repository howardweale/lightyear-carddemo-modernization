"""CI-only negative controls for bootstrap/resource/pin drift."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from tools import check_cloudbank_iac_parity as parity


class CloudBankIacParityTests(unittest.TestCase):
    def fixture(self, folder):
        root = Path(folder)
        for area in (parity.MODULE, "infra/cloud-runner/gcp"):
            shutil.copytree(parity.ROOT / area, root / area)
        target = root / parity.GKE
        target.mkdir(parents=True)
        for name in ("bootstrap.sh", "common.sh"):
            shutil.copyfile(parity.ROOT / parity.GKE / name, target / name)
        return root

    def test_current_resource_sets_and_pins_match(self):
        self.assertEqual(parity.check()["live_drills"], "NOT RUN")

    def test_added_or_missing_resource_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.fixture(folder)
            path = root / parity.MODULE / "main.tf.json"
            value = json.loads(path.read_text())
            del value["resource"]["google_sql_database_instance"]
            path.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, "resource-set-mismatch"):
                parity.check(root)

    def test_bootstrap_flag_change_requires_reconciliation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.fixture(folder)
            path = root / parity.GKE / "bootstrap.sh"
            path.write_bytes(path.read_bytes().replace(b"POSTGRES_16", b"POSTGRES_17"))
            with self.assertRaisesRegex(ValueError, "bootstrap-changed"):
                parity.check(root)

    def test_unknown_imperative_resource_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "unmapped-bootstrap"):
            parity.mutations("gcloud compute instances create surprise\n")

    def test_missing_service_instance_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.fixture(folder)
            path = root / parity.MODULE / "main.tf.json"
            value = json.loads(path.read_text())
            value["locals"]["services"].pop()
            path.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, "service-instance"):
                parity.check(root)
