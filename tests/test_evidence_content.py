import io
from pathlib import Path
import tempfile
import unittest
import warnings
import zipfile
from lightyear_evidence.content import content_view
from lightyear_evidence.read_cache import VerificationReadCache

def archive(rows):
    out=io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore",UserWarning)
        with zipfile.ZipFile(out,"w") as z:
            for name,raw in rows:z.writestr(name,raw)
    return out.getvalue()

class ContentTests(unittest.TestCase):
    def view(self,source,kind="jar",**kw):
        return content_view(source,kind=kind,policy="public-sql-package/1",**kw)
    def test_stable_identity_and_mutated_bytes(self):
        a=self.view(archive([("a",b"one"),("b",b"two")]))
        b=self.view(archive([("b",b"two"),("a",b"one")]))
        self.assertEqual(a,b)
        self.assertNotEqual(a["entries"],self.view(archive([("a",b"changed"),("b",b"two")]))["entries"])
    def test_omitted_entries_are_explicit_and_required_entries_refused(self):
        raw=archive([("a",b"one"),("logs/run.txt",b"temporary")])
        view=self.view(raw,"folder-archive",exclusions={"logs":"runtime log"})
        self.assertEqual({"logs":"runtime log"},view["omitted"])
        self.assertEqual({"a"},set(view["entries"]))
        with self.assertRaises(ValueError):self.view(raw,required_entries=("missing",))
        # JAR entries may not be filtered by folder exclusions.
        self.assertIn("logs/run.txt",self.view(raw,exclusions={"logs":"runtime log"})["entries"])
    def test_duplicates_and_traversal_refused(self):
        for rows in ([('a',b'1'),('a',b'2')],[('../escape',b'x')],[('/absolute',b'x')]):
            with self.assertRaises(ValueError):self.view(archive(rows))
        raw=archive([("a/escape",b"x")]).replace(b"a/escape",b"a\\escape")
        with self.assertRaises(ValueError):self.view(raw)
    def test_tree_archive_same_named_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/"a").write_bytes(b"one")
            self.assertEqual(self.view(p,"folder")["entries"],self.view(archive([("a",b"one")]))["entries"])
    def test_cache_reuse_and_fresh_pass(self):
        calls=[];current=[archive([("a",b"one")])]
        def load():calls.append(1);return current[0]
        with VerificationReadCache() as cache:
            self.assertEqual(b"one",cache.member(("package",),load,["a"]))
            current[0]=archive([("a",b"two")])
            self.assertEqual(b"one",cache.member(("package",),load,["a"]))
        self.assertEqual(1,len(calls))
        with self.assertRaises(ValueError):cache.read(("package",),load)
        with VerificationReadCache() as fresh:self.assertEqual(b"two",fresh.member(("package",),load,["a"]))
        self.assertEqual(2,len(calls))
    def test_cached_archive_duplicate_member_refused(self):
        with VerificationReadCache() as cache:
            with self.assertRaises(ValueError):cache.member(("package",),lambda:archive([("a",b"1"),("a",b"2")]),["a"])
