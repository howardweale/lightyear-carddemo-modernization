"""CI refusal fixtures for navigation and exact historical bytes."""
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch
from tools.ci.check_repository_map import ARCHIVE, DOCUMENTS, EXAMPLES, check


class RepositoryMapTests(unittest.TestCase):
    def fixture(self, root):
        policy = root / EXAMPLES
        policy.parent.mkdir(parents=True, exist_ok=True)
        policy.write_text(json.dumps(dict(schema="repository-map-path-examples/1", examples=[])))
        for name in DOCUMENTS:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('# Guide\n\n[external](https://example.invalid/)\n', encoding='utf-8')
        path = root / ARCHIVE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'original\r\nhistorical bytes\r\n')
        return path.read_bytes()

    def test_missing_link_archive_mutation_and_line_limit_are_rejected(self):
        for case in ('missing', 'escape', 'archive', 'length', 'reject'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                original = self.fixture(root)
                with patch('tools.ci.check_repository_map.subprocess.check_output', return_value=original):
                    self.assertEqual(4, check(root)['documents'])
                    if case == 'missing':
                        (root / 'README.md').write_text('[bad](missing.txt)')
                    elif case == 'escape':
                        (root / 'README.md').write_text('[bad](../outside.txt)')
                    elif case == 'archive':
                        (root / ARCHIVE).write_bytes(original.replace(b'\r\n', b'\n'))
                    elif case == 'length':
                        (root / 'README.md').write_text('line\n' * 151)
                    else:
                        (root / 'CHANGELOG.md.rej').write_text('@@ stray @@')
                    with self.assertRaises(ValueError):
                        check(root)


    def test_named_paths_in_prose_code_and_line_references(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original = self.fixture(root)
            (root / 'tools').mkdir(exist_ok=True)
            (root / 'tools/check.py').write_text('pass\n')
            (root / 'settings.toml').write_text('[settings]\n')
            with patch('tools.ci.check_repository_map.subprocess.check_output', return_value=original):
                for reference in ('tools/check.py', '`tools/check.py:12`', '~~~sh\npython tools/check.py\n~~~',
                                  'settings.toml', '`tools/*.py`', r'`tools\check.py`'):
                    with self.subTest(reference=reference):
                        (root / 'README.md').write_text(reference)
                        self.assertGreater(check(root)['named_paths'], 0)
                (root / 'docs/index.md').write_text('Root path tools/check.py; relative ../settings.toml.')
                self.assertGreater(check(root)['named_paths'], 0)
                # The root cannot be hidden from the scanner by misspelling it.
                for reference in ('tools/missing.py', '`missing.toml`', 'python toools/check.py',
                                  'tools/*.java', '`../outside.py`', '/outside.py', r'C:\outside.py',
                                  'tools/../../outside.py', 'tools/[z]*.py', '`missing/extensionless`', 'misspelled/',
                                  r'`\\server\share\missing.py`'):
                    with self.subTest(reference=reference):
                        (root / 'README.md').write_text(reference)
                        with self.assertRaisesRegex(ValueError, 'named path'):
                            check(root)

    def test_external_urls_anchors_and_non_path_prose_are_not_local_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original = self.fixture(root)
            (root / EXAMPLES).write_text(json.dumps(dict(schema='repository-map-path-examples/1', examples=[
                dict(document='README.md', token=token, reason='Synthetic non-path prose label')
                for token in ('public/synthetic/native', 'z/OS')])))
            (root / 'README.md').write_text(
                'https://example.invalid/missing.py\n[remote](https://example.invalid/a.json)\n'
                '[section](#missing.py)\npublic/synthetic/native scope; z/OS; version 3.13.\n')
            with patch('tools.ci.check_repository_map.subprocess.check_output', return_value=original):
                self.assertEqual(2, check(root)['named_paths'])

    def test_named_path_cannot_escape_through_symlink(self):
        with tempfile.TemporaryDirectory() as temp:
            outer = Path(temp)
            root = outer / 'repo'
            root.mkdir()
            original = self.fixture(root)
            (outer / 'secret.py').write_text('private fixture')
            try:
                (root / 'escape').symlink_to(outer, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest('symlinks unavailable; Linux navigation CI exercises this refusal')
            with patch('tools.ci.check_repository_map.subprocess.check_output', return_value=original):
                for reference in ('escape/secret.py', 'escape/*.py'):
                    (root / 'README.md').write_text(reference)
                    with self.assertRaisesRegex(ValueError, 'named path'):
                        check(root)

    def test_bare_unknown_roots_extensions_and_extensionless_paths_are_checked(self):
        for reference in ('unknown-root/missing', 'unknown-root/missing.proto',
                          'missing.proto', '`missing.proto`'):
            with self.subTest(reference=reference), tempfile.TemporaryDirectory() as temp:
                root = Path(temp); original = self.fixture(root)
                (root / 'README.md').write_text(reference)
                with patch('tools.ci.check_repository_map.subprocess.check_output', return_value=original):
                    with self.assertRaisesRegex(ValueError, 'named path'):
                        check(root)
                    target = root / reference.strip('`')
                    target.parent.mkdir(parents=True, exist_ok=True); target.touch()
                    self.assertGreater(check(root)['named_paths'], 0)

    def test_examples_are_exact_document_scoped_and_cannot_exempt_links(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); original = self.fixture(root)
            example = dict(document='README.md', token='example/output.proto', reason='Intentional output example')
            (root / EXAMPLES).write_text(json.dumps(dict(schema='repository-map-path-examples/1', examples=[example])))
            with patch('tools.ci.check_repository_map.subprocess.check_output', return_value=original):
                (root / 'README.md').write_text('example/output.proto')
                self.assertEqual(1, check(root)['named_paths'])
                for document, text in [('ARCHITECTURE.md', 'example/output.proto'),
                                       ('README.md', 'example/other.proto'),
                                       ('README.md', '[example](example/output.proto)')]:
                    with self.subTest(document=document, text=text):
                        (root / document).write_text(text)
                        with self.assertRaises(ValueError): check(root)
                        (root / document).write_text('# Guide')

    def test_missing_reason_duplicate_wildcard_and_escape_allowances_refused(self):
        variants = [dict(document='README.md', token='example/output.proto', reason=''),
                    dict(document='README.md', token='example/*', reason='Too broad'),
                    dict(document='README.md', token='../escape', reason='Unsafe'),
                    dict(document='outside.md', token='example/output.proto', reason='Wrong document')]
        for row in variants:
            with self.subTest(row=row), tempfile.TemporaryDirectory() as temp:
                root = Path(temp); self.fixture(root)
                (root / EXAMPLES).write_text(json.dumps(dict(schema='repository-map-path-examples/1', examples=[row])))
                with self.assertRaisesRegex(ValueError, 'named-path-example'): check(root)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); self.fixture(root)
            row = dict(document='README.md', token='example/output.proto', reason='Intentional example')
            (root / EXAMPLES).write_text(json.dumps(dict(schema='repository-map-path-examples/1', examples=[row, row])))
            with self.assertRaisesRegex(ValueError, 'duplicate'): check(root)
