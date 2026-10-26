"""CI-only, keyless real-file replacement controls and retained-evidence negatives."""
import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lightyear_factory.contracts import ContractError
from tools.ci import p5_workspace_replacement as probe


class WorkspaceReplacementTests(unittest.TestCase):
    def test_real_replacement_preserves_size_time_but_refuses_new_inode(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')
        rows = probe.observe()
        self.assertEqual([r['case'] for r in rows], list(probe.CASES))
        for row in rows:
            self.assertTrue(probe.validate(row))
            self.assertFalse(row['production_controller_receipt'])
        self.assertEqual(rows[1]['identity_before'][2:4], rows[1]['identity_after'][2:4])
        self.assertNotEqual(rows[1]['identity_before'][1], rows[1]['identity_after'][1])
        self.assertEqual(rows[1]['file_scan_sha256'], [])

    def test_evidence_corruption_and_wrong_refusal_do_not_pass(self):
        row = probe.observe()[1]
        variants = [dict(outcome='unrelated-error'), dict(replacements=0),
                    dict(identity_after=row['identity_before']), dict(read_closed_before_final_stat=False),
                    dict(file_scan_sha256=[row['read_sha256']]), dict(production_controller_receipt=True),
                    dict(source_after_sha256='0'*64), dict(after_hex=row['before_hex'])]
        for mutation in variants:
            bad = copy.deepcopy(row); bad.update(mutation)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): probe.validate(bad)

    def test_unrelated_scan_failure_is_not_replacement_evidence(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(probe.IsolatedWorkspace, 'scan_contents', side_effect=ContractError('unrelated')):
            with self.assertRaisesRegex(ValueError, 'p5-workspace-replacement-invalid'):
                probe.observe_case(Path(temp)/'negative', 'path-replacement')

    def test_non_ci_refuses_before_fixture_creation(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'GITHUB_ACTIONS': 'false'}):
            target = Path(temp)/'must-not-exist'
            with self.assertRaisesRegex(ValueError, 'ci-only'): probe.observe_case(target, 'clean')
            self.assertFalse(target.exists())
