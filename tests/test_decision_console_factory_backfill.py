"""Complete historical import and signed-only activation, using disposable CI keys."""
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import uuid
from unittest.mock import patch

from lightyear_control_tower.console import ConsoleService, provision
from lightyear_control_tower.decisions import canonical
from lightyear_control_tower.factory_history import original_date
from lightyear_control_tower.factory_import import historical_contract, import_request
from lightyear_control_tower.factory_policy import write_request
from lightyear_factory.tower_authority import configured_authority


class RefreshedBackfillTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.repo = self.base / 'repo'
        self.repo.mkdir()
        self.git('init')
        self.documents = {
            'howard-decisions-2026-10-11.json': {'decided_on': '2026-10-11', 'condition': 'pending'},
            'howard-decisions-2026-10-11b.json': {'decided_at': '2026-10-11T14:00:00-07:00'},
            'equivalence-operator-acceptance-2026-10-12.json': {'schema': 'factory-scoped-operator-review/1', 'decided_on': '2026-10-12', 'effective': False},
            'intcalc-duplicate-category-approval-2026-10-12.json': {'schema': 'factory-scoped-domain-approval/1', 'approved_on': '2026-10-12', 'effective': False},
            'posttran-phase1-rerun-authorization-2026-10-12.json': {'schema': 'posttran-phase1-compile-authorization/1', 'authorized_on': '2026-10-12', 'phase2_authorized': False},
            'b06-afternoon-preparation-2026-10-13.json': {'assets': {'artifact_type': 'b06-engineering-assets/1', 'created_at_utc': '2026-10-13T16:11:03+00:00'}, 'native_runs': 0},
            'merge-hold-lift-2026-10-14.json': {'schema': 'factory-human-chat-record/1', 'decided_on': '2026-10-14'},
        }
        folder = self.repo / 'docs/factory'
        folder.mkdir(parents=True)
        for name, record in self.documents.items():
            (folder / name).write_bytes(canonical(record))
        (folder / 'unrelated-2026-10-14.json').write_bytes(b'{}')
        self.git('add', '.')
        self.git('-c', 'user.name=CI fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-m', 'Fixture public history')
        self.head = self.git('rev-parse', 'HEAD').strip()
        self.contract = historical_contract(self.repo, self.head)
        self.root = self.base / 'data'
        self.root.mkdir()

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.repo, text=True, stderr=subprocess.DEVNULL)

    def test_complete_import_sign_and_activate_preserves_conditions(self):
        request = import_request(self.repo, self.root, self.contract)
        self.assertEqual(set(self.documents), {Path(s['path']).name for s in self.contract['sources']})
        for row in self.contract['details']['records']:
            self.assertEqual(self.documents[Path(row['path']).name], row['record'])
        authority = self.base / 'authority/authority.json'
        credential = provision(authority, 'factory', 'howard', 'Howard').read_text().strip()
        service = ConsoleService(self.root, authority)
        self.addCleanup(service.close)
        service.grant_roles('howard', ['operator', 'qualification-approver', 'campaign-authorizer', 'business-owner'], reason='Disposable CI fixture', workloads=['factory:factory'])
        token = service.login(credential)['token']
        item = service.review(token, request['id'])
        event = service.decide(token, dict(item_id=item['id'], bound=item['bound'], outcome='accept', reason='Historical import only; preserve every condition', request_id=str(uuid.uuid4()), previous_decision_sha256=None))
        proof = service.proof(token, event['content_sha256'])
        config = dict(schema='factory-consumer-trust/1', public_key=str(authority.with_suffix('.public.pem')), trusted_head=proof['journal']['journal_head_sha256'], backfill_proof=proof, backfill_contract=self.contract)
        trust = self.base / 'consumer.json'
        trust.write_bytes(canonical(config))
        with patch.dict(os.environ, LIGHTYEAR_FACTORY_AUTHORITY=str(trust)):
            self.assertTrue(configured_authority().signed_only)
            broken = copy.deepcopy(config)
            broken['backfill_proof']['decision_sha256'] = '0' * 64
            trust.write_bytes(canonical(broken))
            with self.assertRaises(ValueError):
                configured_authority()
        # Signing the historical inventory cannot turn pending decisions effective.
        self.assertFalse(next(r['record'] for r in self.contract['details']['records'] if 'duplicate-category' in r['path'])['effective'])
        self.assertFalse(next(r['record'] for r in self.contract['details']['records'] if 'rerun-authorization' in r['path'])['phase2_authorized'])

    def test_omitted_altered_and_mixed_commit_inventory_refused_before_import(self):
        omitted = copy.deepcopy(self.contract)
        omitted['sources'].pop(); omitted['details']['records'].pop()
        altered = copy.deepcopy(self.contract)
        altered['details']['records'][0]['record']['changed'] = True
        wrong_date = copy.deepcopy(self.contract)
        wrong_date['details']['records'][0]['original_date'] = '2026-10-14'
        mixed = copy.deepcopy(self.contract)
        mixed['sources'][0]['commit'] = 'b' * 40
        for value in (omitted, altered, wrong_date, mixed):
            with self.subTest(value=value), self.assertRaises(ValueError):
                import_request(self.repo, self.root, value)
            self.assertEqual([], list(self.root.iterdir()))

    def test_runtime_rejects_changed_date_and_source_after_import(self):
        import_request(self.repo, self.root, self.contract)
        altered = copy.deepcopy(self.contract)
        altered['details']['records'][0]['original_date'] = '2026-10-14'
        with self.assertRaisesRegex(ValueError, 'backfill-original-record'):
            write_request(self.root, altered)
        source = self.root / self.contract['sources'][0]['path']
        source.write_bytes(b'{}')
        with self.assertRaisesRegex(ValueError, 'factory-source-hash'):
            write_request(self.root, self.contract)

    def test_missing_date_is_not_inferred_from_filename(self):
        for record in ({}, {'schema':'factory-scoped-domain-approval/1'}, {'decided_on':'2026-99-99'}):
            with self.assertRaises(ValueError):
                original_date('docs/factory/intcalc-duplicate-category-approval-2026-10-12.json', record)


if __name__ == '__main__':
    unittest.main()
