"""CI fixtures for K1's initial text-hygiene guard."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools import check_java_text


class JavaTextTests(unittest.TestCase):
    def test_valid_unicode_and_ascii_ranges_pass(self):
        for text in ('/** ranges 903-1009 */', '/** ranges 903\u20131009 */', '// caf\u00e9'):
            check_java_text.check_text(text.encode('utf-8'), 'Example.java')

    def test_mojibake_refuses_with_line_location(self):
        for marker in check_java_text.MARKERS:
            with self.subTest(marker=ascii(marker)), self.assertRaisesRegex(
                    ValueError, r'java-mojibake:Example.java:2'):
                check_java_text.check_text(('class Example {}\n// ' + marker).encode(), 'Example.java')

    def test_invalid_utf8_refuses(self):
        with self.assertRaises(UnicodeDecodeError):
            check_java_text.check_text(b'// \xff', 'Example.java')

    def test_tracked_java_inventory_and_empty_refusal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            with self.assertRaisesRegex(ValueError, 'inventory-empty'):
                check_java_text.check(root)
            path = root / 'factory/carddemo-web/service/src/main/java/Example.java'
            path.parent.mkdir(parents=True); path.write_bytes(b'class Example {}\n')
            subprocess.run(['git', '-C', str(root), 'add', '.'], check=True)
            self.assertEqual(1, check_java_text.check(root))
            path.write_bytes(('// ' + check_java_text.MARKERS[0]).encode())
            with self.assertRaisesRegex(ValueError, 'java-mojibake'):
                check_java_text.check(root)
