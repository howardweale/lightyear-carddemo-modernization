"""Unsigned packet and real overlap refusals in disposable CI state only."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lightyear_control_tower.factory_import import import_request
from tests import test_factory_content_supersessions as fixtures
from tools import intcalc_review_packet as packet

ROOT = Path(__file__).resolve().parents[1]


class IntcalcReviewPacketTests(unittest.TestCase):
    def changed(self, edit, error):
        value = json.loads((ROOT / packet.PACKET).read_bytes())
        edit(value)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'packet.json'
            path.write_text(json.dumps(value), encoding='utf-8')
            original = packet.path_at
            with patch.object(packet, 'path_at', side_effect=lambda root, name:
                              path if name == packet.PACKET else original(root, name)):
                with self.assertRaisesRegex(ValueError, error):
                    packet.validate(ROOT)

    def context(self):
        case = fixtures.ContentSupersessionTests('runTest')
        case.setUp()
        self.addCleanup(case.doCleanups)
        repo, contract, _ = case.repo_contract()
        return case, repo, contract

    def test_real_six_templates_validate_without_signing_readiness(self):
        value, contracts = packet.validate(ROOT)
        self.assertEqual(6, len(contracts))
        self.assertFalse(value['ready_for_signing'])
        self.assertEqual('unknown-not-read', value['live_overlap_status'])
        self.assertEqual(81, len(contracts[1]['details']['items']))
        self.assertTrue(all(c['signing_order']['predecessor_decision_sha256'] is None for c in contracts))

    def test_unsigned_flags_and_live_clearance_cannot_be_forged(self):
        for flag in ('signed', 'ready_for_signing', 'execution_authorized', 'release_authorized'):
            with self.subTest(flag=flag):
                self.changed(lambda v: v.update({flag: True}), 'authority')
        self.changed(lambda v: v.update(live_overlap_status='clear'), 'live-claim')

    def test_missing_duplicate_reordered_and_wrong_selected_template_refused(self):
        self.changed(lambda v: v['requests'].pop(), 'six-requests')
        self.changed(lambda v: v['requests'].__setitem__(1, copy.deepcopy(v['requests'][0])), 'order')
        self.changed(lambda v: v['requests'].reverse(), 'order')
        self.changed(lambda v: v['requests'][1]['contract'].update(
            path='docs/factory/appl-result-signing-2026-10-16/INTCALC/contract.json'), 'template')

    def test_digest_omissions_changed_hashes_and_authority_expansion_refused(self):
        self.changed(lambda v: v['requests'][2]['sources'].pop(), 'evidence-inventory')
        self.changed(lambda v: v['requests'][2]['detail_hashes'].pop(), 'evidence-inventory')
        self.changed(lambda v: v['requests'][1].update(queue_sha256='0'*64), 'queue-hash')
        self.changed(lambda v: v['requests'][0]['contract'].update(sha256='0'*64), 'template')
        self.changed(lambda v: v['requests'][0].update(authorization='execute'), 'authority')

    def test_external_current_trust_required_even_for_read_only_overlap_check(self):
        case, repo, contract = self.context()
        with self.assertRaisesRegex(ValueError, 'trusted-journal-required'):
            packet.check_current_overlaps([contract], repository=repo, root=case.base/'empty',
                journal=None, public_key=None, trusted_head=None)

    def test_live_partial_overlap_refused_and_disjoint_allowed_without_writes(self):
        case, repo, contract = self.context()
        target = case.base/'review-queue'
        import_request(repo, target, contract, **case.trust())
        before = {p.relative_to(target).as_posix(): p.read_bytes() for p in target.rglob('*') if p.is_file()}
        successor = copy.deepcopy(contract)
        successor['details']['items'] = ['mutant-2', 'new']
        with self.assertRaisesRegex(ValueError, 'live-overlap'):
            packet.check_current_overlaps([successor], repository=repo, root=target, **case.trust())
        successor['details']['items'] = ['disjoint']
        packet.check_current_overlaps([successor], repository=repo, root=target, **case.trust())
        self.assertEqual(before, {p.relative_to(target).as_posix(): p.read_bytes()
                                 for p in target.rglob('*') if p.is_file()})

    def test_decided_overlap_refused_using_actual_disposable_signed_journal(self):
        case, repo, contract = self.context()
        case.fixture.decide(contract)
        successor = copy.deepcopy(contract)
        successor['details']['items'] = ['mutant-1']
        target = case.base/'unwritten'
        before = case.trust()['journal']
        with self.assertRaisesRegex(ValueError, 'already-decided'):
            packet.check_current_overlaps([successor], repository=repo, root=target, **case.trust())
        self.assertFalse(target.exists())
        self.assertEqual(before['journal_head_sha256'], case.trust()['journal']['journal_head_sha256'])
