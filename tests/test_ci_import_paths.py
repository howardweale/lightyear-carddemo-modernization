import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.check_ci_import_paths import ImportGraph, audit, compare, includes, main


def workflow(paths, command='python -B -m unittest test_entry'):
    return ("name: fixture\non:\n  pull_request:\n    paths: " + json.dumps(paths)
            + "\n  push:\n    branches: [main]\n    paths: " + json.dumps(paths)
            + "\njobs:\n  proof:\n    steps:\n      - run: " + json.dumps(command) + "\n")


class ImportCoverageTests(unittest.TestCase):
    def fixture(self):
        return {
            '.github/workflows/check.yml': workflow(['tests/**']),
            'tests/test_entry.py': 'from package import api\n',
            'src/package/__init__.py': '',
            'src/package/api.py': 'from . import helper\n',
            'src/package/helper.py': 'ANSWER = 42\n',
        }

    def test_transitive_relative_package_dependencies_both_events(self):
        result = audit(self.fixture())
        for event in ('pull_request', 'push'):
            for path in ('src/package/__init__.py', 'src/package/api.py', 'src/package/helper.py'):
                self.assertIn(('.github/workflows/check.yml', event, path), result['gaps'])
        self.assertEqual(len(result['gaps']), 6)

    def test_new_import_refused_and_filter_repair_resolves_debt(self):
        before = self.fixture()
        baseline = audit(before)
        after = dict(before, **{'src/package/api.py': 'from . import helper, added\n',
                               'src/package/added.py': 'VALUE = 3\n'})
        failed = compare(baseline, audit(after))
        self.assertFalse(failed['passed'])
        self.assertEqual({item[2] for item in failed['new_gaps']}, {'src/package/added.py'})
        self.assertEqual(len(failed['inherited_gaps']), 6)
        after['.github/workflows/check.yml'] = workflow(['tests/**', 'src/**'])
        passed = compare(baseline, audit(after))
        self.assertTrue(passed['passed'])
        self.assertEqual(len(passed['resolved_gaps']), 6)
        self.assertEqual(passed['inherited_gaps'], [])

    def test_existing_dependency_becomes_newly_uncovered(self):
        files = self.fixture()
        files['.github/workflows/check.yml'] = workflow(['src/**', 'tests/**'])
        baseline = audit(files)
        files['.github/workflows/check.yml'] = workflow(['tests/**'])
        result = compare(baseline, audit(files))
        self.assertFalse(result['passed'])
        self.assertEqual(len(result['new_gaps']), 6)

    def test_new_filtered_workflow_has_no_inherited_allowance(self):
        files = self.fixture()
        baseline = audit({})
        result = compare(baseline, audit(files))
        self.assertFalse(result['passed'])
        self.assertEqual(result['inherited_gaps'], [])

    def test_patterns_negation_reinclusion_ignore_and_root_glob(self):
        self.assertTrue(includes({'paths': ['**/*.py']}, 'root.py'))
        self.assertFalse(includes({'paths': ['src/**', '!src/private/**']}, 'src/private/key.py'))
        self.assertTrue(includes({'paths': ['src/**', '!src/private/**', 'src/private/public.py']},
                                 'src/private/public.py'))
        self.assertFalse(includes({'paths-ignore': ['**/*.md']}, 'docs/a.md'))
        self.assertTrue(includes({'paths-ignore': ['**/*.md']}, 'src/a.py'))
        self.assertFalse(includes({'paths': ['src/*.py']}, 'src/deep/a.py'))
        self.assertTrue(includes({'paths': ['src/?.py']}, 'src/a.py'))

    def test_cycles_same_directory_imports_and_literal_dynamic_imports(self):
        files = {
            'tools/entry.py': "import helper\nimport importlib\nimportlib.import_module('other.api')\n",
            'tools/helper.py': 'import entry\n',
            'src/other/__init__.py': '',
            'src/other/api.py': 'PASS = True\n',
        }
        graph = ImportGraph(files)
        closure, opaque = graph.closure({'tools/entry.py'})
        self.assertEqual(closure, set(files))
        self.assertFalse(opaque)

    def test_new_nonliteral_dynamic_import_refused_and_reported(self):
        files = self.fixture()
        baseline = audit(files)
        files['src/package/api.py'] += 'import importlib\nimportlib.import_module(name)\n'
        result = compare(baseline, audit(files))
        self.assertFalse(result['passed'])
        self.assertEqual(len(result['new_opaque']), 2)
        self.assertTrue(all(item[2] == 'src/package/api.py' for item in result['new_opaque']))
        # Existing unresolved imports remain visible, never called complete coverage.
        current = audit(files)
        inherited = compare(current, current)
        self.assertTrue(inherited['passed'])
        self.assertEqual(len(inherited['inherited_opaque']), 2)

    def test_wrapper_discovery_and_dotted_method_selectors(self):
        files = {
            'verify.sh': 'python -B -m unittest discover -s tests -p "test_entry*.py"\n',
            'tests/test_entry.py': 'import dependency\n',
            'tests/test_entry_extra.py': '',
            'tests/test_unrelated.py': '',
            'src/dependency.py': '',
        }
        graph = ImportGraph(files)
        roots, unresolved = graph.entrypoints(['./verify.sh'])
        closure, _ = graph.closure(roots)
        self.assertEqual(closure, set(files) - {'tests/test_unrelated.py'})
        roots, _ = graph.entrypoints(['python -B -m unittest test_entry.Case.test_one'])
        self.assertIn('tests/test_entry.py', roots)
        self.assertFalse(unresolved)

    def test_discovery_respects_other_roots_and_multiple_commands(self):
        files = {'tools/suite/test_one.py': '', 'tests/test_alpha.py': '',
                 'tests/test_beta.py': '', 'tests/test_excluded.py': ''}
        graph = ImportGraph(files)
        roots, _ = graph.entrypoints(['python -m unittest discover -s tools/suite'])
        self.assertEqual(roots, {'tools/suite/test_one.py'})
        roots, _ = graph.entrypoints([
            'python -m unittest discover -s tests -p test_alpha.py\n'
            'python -m unittest discover -s tests -p test_beta.py'])
        self.assertEqual(roots, {'tests/test_alpha.py', 'tests/test_beta.py'})

    def test_unfiltered_workflows_are_not_reported_as_path_gaps(self):
        files = self.fixture()
        files['.github/workflows/check.yml'] = (
            'on: [pull_request, push]\njobs:\n  proof:\n    steps:\n'
            '      - run: python -B -m unittest test_entry\n')
        self.assertEqual(audit(files)['gaps'], [])
        self.assertEqual(audit(files)['opaque'], [])

    def test_syntax_errors_and_missing_owned_modules_refuse(self):
        files = self.fixture()
        files['src/package/api.py'] = 'def broken(:\n'
        with self.assertRaises(SyntaxError):
            audit(files)
        files['src/package/api.py'] = ''
        files['.github/workflows/check.yml'] = workflow(['tests/**'], 'python -m tools.missing')
        result = compare(audit({}), audit(files))
        self.assertFalse(result['passed'])
        self.assertTrue(result['new_opaque'])

    def test_real_git_snapshot_does_not_import_or_execute_inspected_sources(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            def git(*args):
                return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.PIPE).decode().strip()
            git('init')
            git('config', 'user.name', 'Fixture')
            git('config', 'user.email', 'fixture@example.invalid')
            for path, content in self.fixture().items():
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content)
            # Any import would execute this. Inspection must only parse it.
            (root / 'src/package/helper.py').write_text("raise RuntimeError('must not execute')\n")
            git('add', '.')
            git('-c', 'commit.gpgsign=false', 'commit', '-m', 'base')
            base = git('rev-parse', 'HEAD')
            (root / 'src/package/added.py').write_text("raise RuntimeError('also inert')\n")
            (root / 'src/package/api.py').write_text('from . import helper, added\n')
            git('add', '.')
            git('-c', 'commit.gpgsign=false', 'commit', '-m', 'new dependency')
            head = git('rev-parse', 'HEAD')
            out = root / 'report.json'
            self.assertEqual(main(['--root', str(root), '--base', base, '--head', head,
                                   '--out', str(out)]), 1)
            report = json.loads(out.read_text())
            self.assertEqual((report['base'], report['head']), (base, head))
            self.assertEqual({row[2] for row in report['new_gaps']}, {'src/package/added.py'})
            self.assertFalse(report['passed'])
            # Dirty files cannot change a report bound to committed Git objects.
            (root / 'src/package/api.py').write_text('not valid Python here')
            self.assertEqual(main(['--root', str(root), '--base', base, '--head', base,
                                   '--out', str(out)]), 0)
            self.assertEqual(json.loads(out.read_text())['head'], base)


if __name__ == '__main__':
    unittest.main()
