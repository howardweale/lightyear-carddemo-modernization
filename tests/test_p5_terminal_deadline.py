"""CI-only acceptance must refuse an elapsed deadline after the successful gate."""
import json
import os
from pathlib import Path
import tempfile
import unittest

from tools.ci.p5_terminal_deadline import observe


class TerminalDeadlineTests(unittest.TestCase):
    def test_clean_gate_and_terminal_deadline_have_distinct_outcomes(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')
        with tempfile.TemporaryDirectory() as temp:
            clean = observe(Path(temp)/'clean', False)
            expired = observe(Path(temp)/'expired', True)
        self.assertEqual(json.loads(clean['receipt_utf8'])['status'], 'passed')
        self.assertIsNone(clean['error'])
        self.assertEqual(expired['gate_reports'][0]['status'], 'passed')
        self.assertEqual(expired['scripted_roles'], ['planner'])
        self.assertEqual(expired['clock_delta'], expired['wall_seconds']+1)
        # Current source can publish success here. Keep the expected refusal strict.
        self.assertEqual(json.loads(expired['receipt_utf8'])['status'], 'blocked')
        self.assertEqual(expired['error'], 'Factory exceeded max_elapsed_seconds')
