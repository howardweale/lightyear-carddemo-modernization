"""CI-only Git diff fixtures for the additive evidence policy."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from tools.check_evidence_files import check, inventory


class EvidencePolicyTests(unittest.TestCase):
    def row(self,path,size=10,blob='a'*40):return dict(path=path,bytes=size,blob=blob)

    def test_new_large_zip_and_mutation_report_refused(self):
        for row in (self.row('new.bin',6_000_000),self.row('proof.zip'),self.row('nested/MUTATIONS.XML')):
            with self.assertRaises(ValueError):check([row],{})
        check([self.row('manifest.json'),self.row('docs/milestones/archive.zip')],{})
        with self.assertRaises(ValueError):check([self.row('docs/milestones/large.zip',6_000_000)],{})

    def test_grandfather_requires_exact_path_blob_and_size(self):
        row=self.row('old/proof.zip');saved={row['path']:(row['blob'],row['bytes'])}
        check([row],saved)
        for changed in [dict(row,blob='b'*40),dict(row,bytes=11),dict(row,path='copy/proof.zip')]:
            with self.assertRaises(ValueError):check([changed],saved)

    def test_metadata_is_under_fifty_kilobytes(self):
        for name in ['docs/modernization/carddemo-proof-summary-test.json',
                     'docs/factory/evidence-retention-2026-10-19-carddemo-run1.json']:
            check([self.row(name,49999)],{})
            with self.assertRaises(ValueError):check([self.row(name,50000)],{})

    def test_real_fixture_pr_diff_preserves_unchanged_old_files(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            def git(*args):
                return subprocess.check_output(['git','-c','user.name=fixture','-c','user.email=fixture@example.invalid',
                                                '-c','commit.gpgsign=false',*args],cwd=root,stderr=subprocess.DEVNULL).decode().strip()
            git('init');(root/'old.zip').write_bytes(b'x'*6_000_000);git('add','.');git('commit','-m','historical')
            base=git('rev-parse','HEAD');(root/'six-megabyte.bin').write_bytes(b'y'*6_000_000)
            (root/'new.zip').write_bytes(b'PK');git('add','.');git('commit','-m','fixture PR');head=git('rev-parse','HEAD')
            original=os.getcwd()
            try:
                os.chdir(root);rows=inventory(base,head)
            finally:os.chdir(original)
            self.assertEqual({'six-megabyte.bin','new.zip'},{r['path'] for r in rows})
            for row in rows:
                with self.assertRaises(ValueError):check([row],{})
