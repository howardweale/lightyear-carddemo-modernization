"""Parser fixtures; real planted-tool acceptance runs belong to CI integration."""
import unittest
from tools.ci.p1_quality_collect import decode_json_lines, format_report
from tools.ci.p1_reports import ReportRefused


class P1QualityParserTests(unittest.TestCase):
    def test_mypy_json_lines_and_invalid_output(self):
        self.assertEqual(decode_json_lines(b'{"line":1}\n{"line":2}\n'), [{"line": 1}, {"line": 2}])
        with self.assertRaisesRegex(ReportRefused, "mypy-output-schema"):
            decode_json_lines(b'Traceback with SYNTHETIC-SECRET')

    def test_format_counts_and_unknown_paths(self):
        result = format_report(b'Would reformat: src/a.py\n1 file would be reformatted, 2 files already formatted\n',
                               "/checkout", {"src/a.py", "src/b.py", "src/c.py"})
        self.assertEqual(len(result["findings"]), 1)
        for raw in (b'Would reformat: ../SECRET\n', b'Unexpected SYNTHETIC-SECRET error\n',
                    b'Would reformat: src/a.py\nWould reformat: src/a.py\n', b'',
                    b'3 files already formatted\n'):
            with self.assertRaises(ReportRefused):
                format_report(raw, "/checkout", {"src/a.py"})
