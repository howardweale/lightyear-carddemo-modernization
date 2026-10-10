import hashlib
from unittest.mock import patch
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
        for rows in ([('a',b'1'),('a',b'2')],[('../escape',b'x')],[('/absolute',b'x')],[('C:/escape',b'x')],[('entry:stream',b'x')]):
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
        key=("package",hashlib.sha256(current[0]).hexdigest())
        with VerificationReadCache() as cache:
            self.assertEqual(b"one",cache.member(key,load,["a"]))
            current[0]=archive([("a",b"two")])
            self.assertEqual(b"one",cache.member(key,load,["a"]))
        self.assertEqual(1,len(calls))
        with self.assertRaises(ValueError):cache.read(key,load)
        with VerificationReadCache() as fresh:self.assertEqual(b"two",fresh.member(("package",hashlib.sha256(current[0]).hexdigest()),load,["a"]))
        self.assertEqual(2,len(calls))
    def test_cached_archive_duplicate_member_refused(self):
        body=archive([("a",b"1"),("a",b"2")])
        with VerificationReadCache() as cache:
            with self.assertRaisesRegex(ValueError,'archive-member-ambiguous'):
                cache.member(("package",hashlib.sha256(body).hexdigest()),lambda:body,["a"])

    def test_wrong_loader_bytes_never_poison_digest_cache(self):
        key=('package',hashlib.sha256(b'right').hexdigest())
        with VerificationReadCache() as cache:
            for wrong in (b'wrong',b'wrong-again'):
                with self.assertRaisesRegex(ValueError,'verification-content-digest-mismatch'):
                    cache.read(key,lambda:wrong)
            self.assertEqual(b'right',cache.read(key,lambda:b'right'))
            with self.assertRaisesRegex(ValueError,'verification-digest-key-required'):
                cache.read(('package',),lambda:b'right')

    def test_archive_limits_refuse_before_member_decompression(self):
        nested=archive([('payload',b'x'*100)])
        body=archive([('nested.jar',nested),('other',b'y')])
        key=('package',hashlib.sha256(body).hexdigest())
        cases=[({'max_archive_bytes':1},'archive'),({'max_entries':1},'entry'),
               ({'max_total_bytes':1},'total'),({'max_member_bytes':1},'member')]
        for limits,reason in cases:
            with self.subTest(reason=reason), VerificationReadCache(**limits) as cache, \
                    patch.object(zipfile.ZipFile,'open',side_effect=AssertionError('must not decompress')):
                with self.assertRaisesRegex(ValueError,'verification-'+reason+'-bound'):
                    cache.member(key,lambda:body,['nested.jar','payload'])
        with VerificationReadCache(max_depth=1) as cache:
            with self.assertRaisesRegex(ValueError,'verification-depth-bound'):
                cache.member(key,lambda:body,['nested.jar','payload'])
        with VerificationReadCache() as cache:
            self.assertEqual(b'x'*100,cache.member(key,lambda:body,['nested.jar','payload']))

    def test_content_archive_caps_precede_hashing_and_path_read(self):
        body=archive([('one',b'a'),('two',b'b')])
        with patch('lightyear_evidence.content.stream_hash',side_effect=AssertionError('must not hash')):
            with self.assertRaisesRegex(ValueError,'bundle-view-entry-bound'):
                self.view(body,max_entries=1)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'too-large.zip';path.write_bytes(body)
            with patch.object(Path,'read_bytes',side_effect=AssertionError('must not read')):
                with self.assertRaisesRegex(ValueError,'bundle-view-archive-bound'):
                    self.view(path,limit=1)
