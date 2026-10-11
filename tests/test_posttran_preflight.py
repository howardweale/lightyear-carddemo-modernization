import copy
import tempfile
import unittest
from pathlib import Path

from lightyear_factory.posttran_second_opinion import prepare
from lightyear_factory.posttran_preflight import verify_approval, check_client, stage_packet
from lightyear_mainframe.zos_bindings import ROOT


class PreflightTests(unittest.TestCase):
    def test_approval_cannot_authorize_changed_plan_or_phase2(self):
        plan = prepare()
        receipt = dict(plan_sha256=plan['content_sha256'], approved_phase=1,
                       approved_limits=plan['phases']['1'], human_answer='Approve Phase 1 budget')
        self.assertFalse(verify_approval(plan, receipt)['phase2_authorized'])
        for changed in ({**receipt, 'approved_phase': 2},
                        {**receipt, 'plan_sha256': 'other'},
                        {**receipt, 'approved_limits': {}}):
            with self.assertRaises(ValueError): verify_approval(plan, changed)
        modified = copy.deepcopy(plan)
        modified['client']['sha256'] = 'replacement'
        with self.assertRaisesRegex(ValueError, 'plan-seal'): verify_approval(modified, receipt)

    def test_same_version_claim_cannot_replace_pinned_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'client'
            path.write_bytes(b'codex-cli 0.155.0-alpha.9.2')
            with self.assertRaisesRegex(ValueError, 'pinned-client-hash-mismatch'):
                check_client(prepare(), path)

    def test_packet_contains_exact_public_allowlist_and_no_judge_material(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / 'packet'
            plan = prepare()
            manifest = stage_packet(ROOT, plan, target)
            files = {p.relative_to(target).as_posix() for p in target.rglob('*') if p.is_file()}
            self.assertEqual(files, set(manifest))
            self.assertFalse(any('/after/' in p or 'review' in p or '.git' in p for p in files))
            with self.assertRaisesRegex(ValueError, 'already-exists'): stage_packet(ROOT, plan, target)
            plan['inputs']['docs/factory/posttran-human-review-sheet.json'] = 'forbidden'
            with self.assertRaises(ValueError): stage_packet(ROOT, plan, Path(td) / 'leak')
