"""CI refusal fixtures for navigation and exact historical bytes."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools.ci.check_repository_map import ARCHIVE, DOCUMENTS, check


class RepositoryMapTests(unittest.TestCase):
    def fixture(self, root):
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
