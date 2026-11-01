"""Synthetic CI-only exact-main collector isolation; no public download or private input."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.ci.copau_run_boundary import collect_from_main, template_inventory


class MainCollectorTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory(prefix='copau-source-ci-')))
        self.repo = self.root/'repo'
        self.repo.mkdir()
        self.git('init', '--quiet')
        self.git('config', 'core.autocrlf', 'false')
        self.git('config', 'core.hooksPath', str(self.root/'no-hooks'))
        self.git('config', 'commit.gpgsign', 'false')
        self.git('config', 'user.name', 'Synthetic CI')
        self.git('config', 'user.email', 'ci@example.invalid')
        (self.repo/'src').mkdir()
        (self.repo/'tools/ci').mkdir(parents=True)
        self.source = self.repo/'src/marker.py'
        self.source.write_bytes(b"VALUE='main-bytes'\n")
        script = "import argparse,json,os,subprocess\nfrom pathlib import Path\nfrom marker import VALUE\np=argparse.ArgumentParser();p.add_argument('--out');a=p.parse_args()\no=Path(a.out);o.mkdir()\n(o/'boundary.json').write_text(json.dumps(dict(main_commit=os.environ['COPAU_BOUNDARY_MAIN_COMMIT'])),encoding='utf-8')\n(o/'receipt.json').write_text(json.dumps(dict(value=VALUE,head=subprocess.check_output(['git','rev-parse','HEAD']).decode().strip(),pin=os.environ['COPAU_BOUNDARY_MAIN_COMMIT'],pythonpath=os.environ['PYTHONPATH'])),encoding='utf-8')\n"
        self.script = self.repo/'tools/ci/copau_run_boundary.py'
        self.script.write_bytes(script.encode())
        self.git('add', '.')
        self.git('commit', '--quiet', '-m', 'Synthetic main collector')
        self.main = self.git('rev-parse', 'HEAD').strip()
        self.source.write_bytes(b"VALUE='candidate-bytes'\n")
        self.git('add', '.')
        self.git('commit', '--quiet', '-m', 'Synthetic candidate')
        self.candidate = self.git('rev-parse', 'HEAD').strip()

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.repo), *args], stderr=subprocess.PIPE).decode()

    def test_exact_main_code_and_imports_without_changing_candidate(self):
        before = self.git('worktree', 'list', '--porcelain')
        output = self.root/'corpus'
        collect_from_main(self.repo, self.main, output)
        receipt = json.loads((output/'receipt.json').read_bytes())
        self.assertEqual(receipt['value'], 'main-bytes')
        self.assertEqual(receipt['head'], self.main)
        self.assertEqual(receipt['pin'], self.main)
        self.assertNotIn(str(self.repo/'src'), receipt['pythonpath'])
        self.assertEqual(self.git('rev-parse', 'HEAD').strip(), self.candidate)
        self.assertEqual(self.source.read_bytes(), b"VALUE='candidate-bytes'\n")
        self.assertEqual(before, self.git('worktree', 'list', '--porcelain'))

    def test_child_failure_cleans_checkout_and_propagates(self):
        self.script.write_bytes(b'raise SystemExit(7)\n')
        self.git('add', '.')
        self.git('commit', '--quiet', '-m', 'Synthetic failed collector')
        failed = self.git('rev-parse', 'HEAD').strip()
        before = self.git('worktree', 'list', '--porcelain')
        with self.assertRaises(subprocess.CalledProcessError) as caught:
            collect_from_main(self.repo, failed, self.root/'failed')
        self.assertEqual(caught.exception.returncode, 7)
        self.assertEqual(before, self.git('worktree', 'list', '--porcelain'))
        self.assertEqual(self.git('rev-parse', 'HEAD').strip(), failed)

    def test_non_exact_ref_and_existing_output_refused(self):
        with self.assertRaises(ValueError):
            collect_from_main(self.repo, 'HEAD', self.root/'output')
        existing = self.root/'existing'
        existing.mkdir()
        (existing/'sentinel').write_bytes(b'preserve')
        with self.assertRaises(ValueError):
            collect_from_main(self.repo, self.main, existing)
        self.assertEqual((existing/'sentinel').read_bytes(), b'preserve')

    def test_mixed_candidate_template_bytes_still_refused(self):
        with self.assertRaises(ValueError):
            template_inventory(self.repo, self.main, ['src/marker.py'], self.root/'templates')
        self.assertFalse((self.root/'templates/src/marker.py').exists())


if __name__ == '__main__':
    unittest.main()
