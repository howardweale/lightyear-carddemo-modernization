import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tools.check_cloud_image_bundle import check


class BundleTests(unittest.TestCase):
    def test_complete_exact_bundle_and_tamper_checks(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            names = ["jdk21.tar.gz", "docker-static.tgz", "requirements.lock",
                     "debs/python-venv.deb", "wheels/test.whl"]
            files = {}
            for name in names:
                p = root / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(name.encode())
                files[name] = hashlib.sha256(name.encode()).hexdigest()
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"schema": "lightyear.image-bundle.v1", "files": files}))
            digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
            self.assertEqual(check(root, digest)["files"], 5)
            (root / "jdk21.tar.gz").write_bytes(b"tampered")
            with self.assertRaises(ValueError):
                check(root, digest)
            (root / "jdk21.tar.gz").write_bytes(b"jdk21.tar.gz")
            (root / "extra.key").write_bytes(b"unlisted")
            with self.assertRaises(ValueError):
                check(root, digest)
            (root / "extra.key").unlink()
            with self.assertRaises(ValueError):
                check(root, "0" * 64)

    def test_missing_runtime_dependencies_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / "manifest.json"
            p.write_text(json.dumps({"schema": "lightyear.image-bundle.v1", "files": {}}))
            with self.assertRaises(ValueError):
                check(Path(folder), hashlib.sha256(p.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
