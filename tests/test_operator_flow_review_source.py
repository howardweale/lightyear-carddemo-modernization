"""CI-only original file/checkout observations. No API or verifier substitute."""
import os,subprocess,tempfile,unittest
from pathlib import Path
from contextlib import contextmanager
from unittest.mock import patch
from operator_flow_checkout_fixture import clean_checkout_test
from tools.ci.operator_flow_review_source import _source_bytes,check_review_source,LIMIT
# Ensure the original direct review module is loaded, as in the real entry.
from tools.ci import operator_flow_publication_review
from lightyear_factory import contracts,model_admission
from lightyear_execution import contracts as execution_contracts,tower_drill_admission,tower_drill_reservation
from tools.ci.operator_flow_consumer import git


class ReviewSourceBoundaries(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.file=self.root/'source.py'
        self.raw=b'"""Public inert source bytes."""\n';self.file.write_bytes(self.raw)
    def test_original_regular_file_is_unchanged(self):
        self.assertEqual(_source_bytes(self.file),self.raw)
        self.assertEqual(self.file.read_bytes(),self.raw)
    def test_changed_bytes_are_observed_not_cached(self):
        self.assertEqual(_source_bytes(self.file),self.raw)
        self.file.write_bytes(self.raw+b'# changed\n')
        self.assertEqual(_source_bytes(self.file),self.raw+b'# changed\n')
    def test_real_midread_size_and_same_size_changes_refuse(self):
        original=Path.open
        for replacement in (self.raw+b'# longer\n',b'X'+self.raw[1:]):
            self.file.write_bytes(self.raw)
            @contextmanager
            def changing_open(path,*args,**kwargs):
                with original(path,*args,**kwargs) as stream:
                    if path!=self.file or args!=('rb',):
                        yield stream;return
                    class Reader:
                        def fileno(inner):return stream.fileno()
                        def read(inner,limit):
                            raw=stream.read(limit)
                            before=os.stat(path)
                            with original(path,'wb') as writer:writer.write(replacement)
                            os.utime(path,ns=(before.st_atime_ns,before.st_mtime_ns+2000000000))
                            return raw
                    yield Reader()
            with self.subTest(size=len(replacement)),patch.object(Path,'open',changing_open):
                with self.assertRaisesRegex(ValueError,'review-source-changed'):_source_bytes(self.file)
            self.assertEqual(self.file.read_bytes(),replacement)
    def test_real_path_replacement_after_close_refuses(self):
        original=Path.open
        replacement=self.root/'replacement.py';replacement.write_bytes(self.raw)
        stamp=self.file.stat();os.utime(replacement,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
        @contextmanager
        def replacing_open(path,*args,**kwargs):
            with original(path,*args,**kwargs) as stream:yield stream
            if path==self.file and args==('rb',):os.replace(replacement,path)
        with patch.object(Path,'open',replacing_open):
            with self.assertRaisesRegex(ValueError,'review-source-changed'):_source_bytes(self.file)
        self.assertEqual(self.file.read_bytes(),self.raw)
    @clean_checkout_test
    def test_dirty_exact_checkout_still_refuses_without_cleanup(self):
        root=Path(os.environ['GITHUB_WORKSPACE']).resolve(strict=True)
        head=git(root,'rev-parse','HEAD').decode().strip()
        marker=root/'operator-source-dirty-fixture.txt'
        with marker.open('xb') as stream:stream.write(b'public dirty fixture\n')
        try:
            with self.assertRaisesRegex(ValueError,'consumer-clean-source'):check_review_source(root,head)
            self.assertEqual(marker.read_bytes(),b'public dirty fixture\n')
        finally:marker.unlink()
    def test_empty_and_oversize_files_refuse(self):
        for raw in (b'',b'x'*(LIMIT+1)):
            self.file.write_bytes(raw)
            with self.subTest(size=len(raw)),self.assertRaisesRegex(ValueError,'review-source-file'):
                _source_bytes(self.file)
    def test_hardlinked_source_refuses(self):
        link=self.root/'linked.py';os.link(self.file,link)
        with self.assertRaisesRegex(ValueError,'review-source-file'):_source_bytes(self.file)
        with self.assertRaisesRegex(ValueError,'review-source-file'):_source_bytes(link)
    def test_directory_and_relative_paths_refuse(self):
        with self.assertRaisesRegex(ValueError,'review-source-file'):_source_bytes(self.root)
        with self.assertRaisesRegex(ValueError,'review-source-absolute'):_source_bytes(Path('source.py'))
    @clean_checkout_test
    def test_actual_ci_checkout_modules_match_current_commit(self):
        root=Path(os.environ['GITHUB_WORKSPACE']).resolve(strict=True)
        head=git(root,'rev-parse','HEAD').decode().strip()
        first=check_review_source(root,head)
        self.assertEqual(len(first),13)
        self.assertEqual(first,check_review_source(root,head))
        self.assertTrue(all(len(value)==64 for value in first.values()))
    @clean_checkout_test
    def test_wrong_exact_commit_refuses_before_module_review(self):
        root=Path(os.environ['GITHUB_WORKSPACE']).resolve(strict=True)
        with self.assertRaisesRegex(ValueError,'review-source-exact-E'):check_review_source(root,'0'*40)
    def test_other_clean_git_root_refuses_actual_loaded_origins(self):
        other=self.root/'other';other.mkdir();hooks=self.root/'empty-hooks';hooks.mkdir()
        subprocess.run(['git','init','--quiet',str(other)],check=True,capture_output=True)
        subprocess.run(['git','-C',str(other),'-c','user.name=Public fixture',
            '-c','user.email=fixture@example.invalid','-c','commit.gpgsign=false',
            '-c','core.hooksPath='+str(hooks),'commit','--allow-empty','--no-gpg-sign',
            '-m','Public empty source boundary fixture'],check=True,capture_output=True)
        head=git(other,'rev-parse','HEAD').decode().strip()
        with self.assertRaisesRegex(ValueError,'review-source-module-origin'):
            check_review_source(other,head)
