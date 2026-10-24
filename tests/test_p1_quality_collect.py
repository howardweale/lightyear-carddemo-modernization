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

    def test_failure_diagnostics_are_bounded_and_never_copy_streams(self):
        import json
        from pathlib import Path
        import tempfile
        from unittest.mock import patch
        from tools.ci.p1_quality_collect import collect
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'src').mkdir()
            (root / 'src/a.py').write_text('value = 1\n', encoding='utf-8')
            output = root / 'output'
            captured = [(0, b'src/a.py\0', b''), (0, b'[]', b''),
                        (2, b'SYNTHETIC-SECRET-OUTPUT', b'SYNTHETIC-SECRET-ERROR'),
                        (0, b'', b''), (0, b'a' * 40 + b'\n', b'')]
            with patch.dict('os.environ', {'GITHUB_ACTIONS': 'true'}), patch(
                'tools.ci.p1_quality_collect.version', side_effect=lambda name: {'ruff': '0.17.2', 'mypy': '2.4.0'}[name]), patch(
                'tools.ci.p1_quality_collect.capture', side_effect=captured):
                self.assertFalse(collect(root, output))
            raw = (output / 'summary.json').read_text(encoding='utf-8')
            self.assertNotIn('SYNTHETIC-SECRET', raw)
            diagnostic = json.loads(raw)['results'][1]['diagnostic']
            self.assertEqual('parse', diagnostic['stage'])
            self.assertEqual(2, diagnostic['exit_code'])
            self.assertEqual('format-output-schema', diagnostic['refusal_code'])
            self.assertEqual(64, len(diagnostic['stderr_sha256']))
