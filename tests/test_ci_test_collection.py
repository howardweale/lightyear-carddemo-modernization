from pathlib import Path
import tempfile
import unittest
from tools.check_ci_test_collection import check,inventory


class CollectionGuardTests(unittest.TestCase):
    def fixture(self,run):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);root=Path(temp.name)
        (root/'tests').mkdir();(root/'tests/test_a.py').write_text('raise AssertionError("must never import")\n')
        (root/'tests/test_b.py').write_text('raise AssertionError("must never import")\n')
        (root/'.github/workflows').mkdir(parents=True)
        (root/'.github/workflows/test.yml').write_text('jobs:\n  test:\n    steps:\n      - run: |\n'+''.join('          '+line+'\n' for line in run.splitlines()))
        return root

    def test_only_executed_collection_counts(self):
        for run in ('# python -m unittest test_a test_b','echo python -m unittest test_a test_b',
                    'python -m unittest test_a.OneTest.test_only','python -m unittest test_a'):
            with self.subTest(run=run),self.assertRaisesRegex(ValueError,'CI-test-not-collected'):
                check(self.fixture(run))

    def test_explicit_modules_and_discovery_patterns(self):
        self.assertEqual(2,len(check(self.fixture('python -m unittest test_a test_b -v'))))
        self.assertEqual(2,len(check(self.fixture("python -m unittest discover -s tests -p 'test_*.py'"))))
        with self.assertRaisesRegex(ValueError,'test_b.py'):
            check(self.fixture("python -m unittest discover -s tests -p 'test_a.py'"))

    def test_repository_wrapper_and_disabled_step(self):
        root=self.fixture('./verify.sh')
        (root/'verify.sh').write_text('"$LIGHTYEAR_PYTHON_BIN" -m unittest discover -s "$project_dir/tests" -v\n')
        self.assertEqual(2,len(check(root)))
        workflow=root/'.github/workflows/test.yml'
        workflow.write_text(workflow.read_text().replace('- run: |','- if: false\n        run: |'))
        self.assertFalse(any(inventory(root).values()))


    def test_execution_reporter_and_comment_are_distinguished(self):
        root=self.fixture('./verify.sh')
        (root/'verify.sh').write_text('"$LIGHTYEAR_PYTHON_BIN" -B "$project_dir/tools/ci_test_execution.py"\n')
        self.assertEqual(2,len(check(root)))
        for run in ('# python tools/ci_test_execution.py', 'echo python tools/ci_test_execution.py',
                    'python tools/ci_test_execution.py --root elsewhere'):
            with self.subTest(run=run),self.assertRaisesRegex(ValueError,'CI-test-not-collected'):
                check(self.fixture(run))
