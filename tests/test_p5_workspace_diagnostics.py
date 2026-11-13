"""Diagnostics preserve an unmet expectation, never substitute a passing result."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from lightyear_factory.contracts import ContractError
from tools.ci import p5_workspace_replacement as probe


class WorkspaceDiagnosticTests(unittest.TestCase):
    def test_failed_observation_is_retained_without_relaxing_validator(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(probe.IsolatedWorkspace, 'scan_contents', side_effect=ContractError('unrelated')):
            with self.assertRaisesRegex(ValueError, 'p5-workspace-replacement-invalid') as caught:
                probe.observe_case(Path(temp)/'case', 'clean')
        detail = caught.exception.observation
        self.assertEqual(detail, json.loads(str(caught.exception).split(': ', 1)[1]))
        self.assertEqual(detail['observation']['outcome'], 'unrelated')
        self.assertFalse(detail['opened'])
        self.assertEqual(detail['handle_identities'], [])
        with self.assertRaisesRegex(ValueError, 'p5-workspace-replacement-invalid'):
            probe.validate(detail['observation'])

    def test_lexical_alias_keeps_real_scan_and_replacement_hooks_bound(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); (root/'intermediate').mkdir()
            rows=[]
            for case in probe.CASES:
                alias=root/'intermediate'/'..'/case
                self.assertNotEqual(str(alias),str(alias.resolve()))
                rows.append(probe.observe_case(alias,case))
        self.assertEqual([r['case'] for r in rows],list(probe.CASES))
        self.assertEqual(rows[0]['outcome'],'passed')
        self.assertEqual(rows[1]['outcome'],'workspace-isolation-refused')
        for row in rows:
            self.assertTrue(probe.validate(row))
            self.assertTrue(row['read_closed_before_final_stat'])
            self.assertFalse(row['production_controller_receipt'])
        self.assertEqual(rows[1]['replacements'],1)
        self.assertNotEqual(rows[1]['identity_before'][1],rows[1]['identity_after'][1])
        self.assertEqual(rows[1]['identity_before'][2:4],rows[1]['identity_after'][2:4])
        self.assertEqual(rows[1]['file_scan_sha256'],[])
