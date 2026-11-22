import hashlib
import tempfile
import unittest
from pathlib import Path

from tools.ci.cloudbank_maven_cache import pom_digest, prepare_work, stage_seed


class CloudBankCacheTests(unittest.TestCase):
    def test_hashes_nested_pom_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "pom.xml").write_bytes(b"root")
            (root / "module").mkdir()
            child = root / "module/pom.xml"
            child.write_bytes(b"one\n")
            first = pom_digest([root])
            child.write_bytes(b"one\r\n")
            self.assertNotEqual(first, pom_digest([root]))

    def test_partial_restore_unused_and_exact_restore_adopted(self):
        for exact in (True, False):
            with self.subTest(exact=exact), tempfile.TemporaryDirectory() as temp:
                directory = Path(temp)
                (directory / "seed").mkdir()
                (directory / "seed/artifact").touch()
                prepare_work(directory, exact)
                self.assertEqual((directory / "work/artifact").exists(), exact)
                self.assertEqual((directory / "unused-restore/artifact").exists(), not exact)

    def test_only_verified_central_releases_are_saved(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            release = directory / "work/org/example/lib/1.0"
            release.mkdir(parents=True)
            markers = []
            for name, origin in (("good.pom", "central"), ("bad.jar", "central"),
                                 ("local.jar", ""), ("other.jar", "other"),
                                 ("mixed.jar", "central"), ("mixed.jar", "")):
                (release / name).write_bytes(b"bytes")
                digest = hashlib.sha1(b"bytes").hexdigest() if name != "bad.jar" else "0" * 40
                (release / (name + ".sha1")).write_text(digest)
                markers.append(f"{name}>{origin}=\n")
            (release / "_remote.repositories").write_text("".join(markers))
            (release / "lib.lastUpdated").touch()
            snapshot = release.parent / "1-SNAPSHOT"
            snapshot.mkdir()
            for path in release.iterdir():
                (snapshot / path.name).write_bytes(path.read_bytes())
            self.assertEqual(stage_seed(directory), 1)
            payload = directory / "seed/org/example/lib/1.0"
            self.assertEqual({p.name for p in payload.iterdir()},
                             {"good.pom", "good.pom.sha1", "_remote.repositories"})
            self.assertEqual((payload / "_remote.repositories").read_text(), "good.pom>central=\n")
            self.assertFalse((payload.parent / "1-SNAPSHOT").exists())
