"""CI fixtures show measurements respond to changed source, not typed totals."""
import unittest
from tools.ci.repo_metrics import analyze


class RepositoryMetricsTests(unittest.TestCase):
    def test_import_and_size_changes_change_measurements(self):
        known = {'lightyear_judge', 'lightyear_common', 'lightyear_factory'}
        path = 'src/lightyear_judge/example.py'
        base = b'from .contracts import Value\nfrom lightyear_common import value\n'
        before, short = analyze(path, base, known)
        after, long = analyze(path, base + b'import lightyear_factory\n'
                              + b'def long_function():\n' + b'    pass\n' * 151, known)
        self.assertEqual(['lightyear_common'], [row['to'] for row in before])
        self.assertEqual(['lightyear_common', 'lightyear_factory'], [row['to'] for row in after])
        self.assertEqual([], short)
        self.assertEqual(152, long[0]['lines'])
