"""Intake/receipt contracts only; these tests do not claim native DB execution."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools.ci import tsql_readiness_ten as h

ROOT = Path(__file__).resolve().parents[1]


class PublicTenReadinessTests(unittest.TestCase):
    def selection(self):
        return json.loads((ROOT/'docs/tsql-readiness/selection.json').read_bytes())

    def test_all_ten_hash_bound_public_inputs_and_twins_are_present(self):
        rows = h.intake(ROOT, self.selection())
        self.assertEqual(tuple(r['id'] for r in rows), h.IDS)
        self.assertEqual(len(rows), 10)
        self.assertTrue(all({'source', 'correct', 'wrong', 'source-setup', 'target-setup', 'wrong-setup'} <= set(r['assets']) for r in rows))

    def test_unknown_missing_duplicate_or_changed_corpus_selection_refuses(self):
        for kind in ('missing', 'duplicate', 'unknown', 'hash', 'path'):
            selection = self.selection()
            if kind == 'missing': selection['ids'].pop()
            if kind == 'duplicate': selection['ids'][-1] = selection['ids'][0]
            if kind == 'unknown': selection['ids'][-1] = 'not-public'
            if kind == 'hash': selection['corpus']['sha256'] = '0'*64
            if kind == 'path': selection['corpus']['path'] = 'work/mainframe/arrivals/not-read.json'
            with self.subTest(kind=kind), patch.object(h, 'asset') as reader:
                with self.assertRaisesRegex(ValueError, 'ten-pair-selection'):
                    h.intake(ROOT, selection)
                reader.assert_not_called()

    def test_asset_drift_and_escape_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); path = root/'data-modernization/tsql-procedures/public.sql'
            path.parent.mkdir(parents=True); path.write_bytes(b'SELECT 1;\n')
            descriptor = dict(path=path.relative_to(root).as_posix(), sha256=h.sha(path.read_bytes()))
            self.assertEqual(h.asset(root, descriptor), 'SELECT 1;\n')
            path.write_bytes(b'SELECT 2;\n')
            with self.assertRaisesRegex(ValueError, 'public-asset-hash'): h.asset(root, descriptor)
            descriptor['path'] = 'data-modernization/tsql-procedures/../../outside.sql'
            with self.assertRaisesRegex(ValueError, 'public-asset-path'): h.asset(root, descriptor)

    def test_receipt_never_accepts_missing_case_wrong_twin_match_or_cleanup_failure(self):
        expected = [('correct','boundary-01',1), ('wrong','boundary-01',1)]
        rows = [dict(variant=v, case_id=c, repeat=r, status='compared', cleanup_complete=True,
                     verdict='equivalent' if v=='correct' else 'divergent') for v,c,r in expected]
        self.assertEqual(h.verdict(rows, expected), 'equivalent-on-declared-public-cases')
        self.assertEqual(h.verdict(rows[:-1], expected), 'insufficient-evidence')
        self.assertEqual(h.verdict(rows+rows[:1], expected), 'insufficient-evidence')
        bad = copy.deepcopy(rows); bad[1]['verdict'] = 'equivalent'
        self.assertEqual(h.verdict(bad, expected), 'insufficient-evidence')
        bad = copy.deepcopy(rows); bad[0]['verdict'] = 'divergent'
        self.assertEqual(h.verdict(bad, expected), 'divergent')
        bad = copy.deepcopy(rows); bad[0]['cleanup_complete'] = False
        self.assertEqual(h.verdict(bad, expected), 'execution-error')
        bad = copy.deepcopy(rows); bad[0]['verdict'] = 'insufficient-evidence'
        self.assertEqual(h.verdict(bad, expected), 'insufficient-evidence')

    def test_non_ci_refuses_before_native_import_or_output_creation(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict('os.environ', {'GITHUB_ACTIONS':'false'}):
            output = Path(folder)/'not-created'
            with self.assertRaisesRegex(ValueError, 'tsql-readiness-ci-only'):
                h.run_suite(ROOT, output, None, None, None, self.selection())
            self.assertFalse(output.exists())
