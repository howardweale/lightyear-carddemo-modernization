"""CI-only tests for unsigned projection accounting and actual Tower import."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from lightyear_mainframe.equivalence_automation import sealed, digest
from lightyear_mainframe.equivalence_projection import project
from lightyear_control_tower.factory_import import import_request
from lightyear_control_tower.factory_policy import FactoryInbox
from lightyear_control_tower.kinds import factory_registry

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'docs/factory/equivalence-evidence-2026-10-15'
NEW = ROOT / 'docs/factory/equivalence-scale-2026-10-16'


class ProjectionTests(unittest.TestCase):
    def fixture(self, program='INTCALC'):
        ledger = json.loads((BASE / program / 'resolutions.json').read_text())
        request = json.loads((NEW / (program + '-class-request.json')).read_text())
        return ledger, request, request['class_proof']['matcher_sha256']

    def test_baseline_projection_uses_union_and_preserves_history(self):
        reports = []
        for p in ('INTCALC', 'POSTTRAN'):
            ledger, request, matcher = self.fixture(p)
            before = copy.deepcopy(ledger)
            report = project(ledger, [request], matcher)
            self.assertEqual(report, project(ledger, [request, request], matcher))
            self.assertEqual(before, ledger)
            self.assertFalse(report['signatures_verified'])
            reports.append(report)
        self.assertEqual([113, 114], [r['denominator'] for r in reports])
        self.assertEqual([4, 4], [r['resolved_now'] for r in reports])
        self.assertEqual([85, 100], [r['resolved_after_pending_signatures'] for r in reports])

    def test_unobservable_stays_unresolved_and_in_denominator(self):
        ledger, req, matcher = self.fixture()
        mid = req['contract']['details']['items'][0]
        row = next(r for r in ledger['rows'] if r['id'] == mid)
        row['status'] = 'unobservable'
        ledger = sealed({k:v for k,v in ledger.items() if k != 'content_sha256'})
        out = project(ledger, [req], matcher)
        self.assertEqual(113, out['denominator'])
        self.assertEqual(84, out['resolved_after_pending_signatures'])

    def test_scope_head_member_and_matcher_tampering_refused(self):
        ledger, req, matcher = self.fixture()
        for field, value in (('head', 'a'*40), ('matcher_sha256', 'b'*64), ('claim_scope', 'zos-facing')):
            bad = copy.deepcopy(req)
            cp = bad['class_proof']; cp[field] = value
            cp.pop('content_sha256'); bad['class_proof'] = sealed(cp)
            bad['contract']['details']['class_proof_sha256'] = bad['class_proof']['content_sha256']
            with self.assertRaises(ValueError): project(ledger, [bad], matcher)
        with self.assertRaisesRegex(ValueError, 'disabled'):
            project(ledger, [req], matcher, disabled_classes=['legacy-APPL-RESULT/1'])

    def test_executed_kill_cannot_receive_class_projection(self):
        ledger, req, matcher = self.fixture()
        next(r for r in ledger['rows'] if r['id'] == req['contract']['details']['items'][0])['status'] = 'killed'
        ledger = sealed({k:v for k,v in ledger.items() if k != 'content_sha256'})
        with self.assertRaisesRegex(ValueError, 'executed-kill'): project(ledger, [req], matcher)

    def test_tower_import_exact_committed_bytes_and_all_members(self):
        for p, count in (('INTCALC', 81), ('POSTTRAN', 96)):
            _, req, _ = self.fixture(p)
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                with self.assertRaisesRegex(ValueError,'factory-request-superseded'):
                    import_request(ROOT, root, req['contract'])
                wrapper=json.loads((ROOT/f'docs/factory/equivalence-scale-supersession-2026-10-17/{p}-class-request.json').read_bytes())
                self.assertEqual(req['contract'],wrapper['superseded_contract'])
                with self.assertRaisesRegex(ValueError,'factory-request-superseded'):
                    import_request(ROOT,root,wrapper)
                self.assertEqual([],list(root.iterdir()))
                contract=json.loads((ROOT/f'docs/factory/appl-result-signing-2026-10-16/{p}/contract.json').read_bytes())
                if p=='INTCALC':
                    with self.assertRaisesRegex(ValueError,'superseded-content'):
                        import_request(ROOT,root,contract)
                    self.assertEqual([],list(root.iterdir()))
                else:
                    from tests import test_decision_console_factory as fixtures
                    fixture=fixtures.FactoryTests('runTest');fixture.setUp()
                    try:
                        journal=fixture.service.export_session(fixture.token)
                        item=import_request(ROOT,root,contract,journal=journal,public_key=fixture.service.public_key,
                            trusted_head=journal['journal_head_sha256'])
                        self.assertEqual(wrapper['replacement_request_id'],item['id'])
                        verified=FactoryInbox(root,'factory',factory_registry()).item(item['id'])
                        self.assertEqual(item['id'],verified['id'])
                        from lightyear_control_tower.decisions import digest as contract_digest
                        self.assertEqual('factory-'+contract_digest(contract),item['id'])
                    finally:fixture.doCleanups()
                self.assertEqual(count,len(req['contract']['details']['items']))
                audit = json.loads((NEW / (p + '-class-audit.json')).read_text())
                self.assertEqual(30, len({r['id'] for r in audit['sample']}))
                self.assertEqual(count, len(audit['members']))
                self.assertTrue(all(r['original'] and r['replacement'] for r in audit['sample']))


if __name__ == '__main__': unittest.main()

class SigningGeneratorTests(unittest.TestCase):
    def test_prepare_roundtrip_matches_published_bytes_without_extra_contract(self):
        import subprocess
        from tools.prepare_equivalence_signing import prepare,DEST,FRESH_COMMIT
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)
            prepare(ROOT,'043c4ef3ac0c46753ea283bd8dfc1e00410256ad',output_root=output)
            before={p.relative_to(output).as_posix():p.read_bytes() for p in output.rglob('*') if p.is_file()}
            self.assertFalse(any(name.endswith('-tower-contract.json') for name in before))
            self.assertEqual(7,len(before))
            for path,raw in before.items():
                self.assertEqual(subprocess.check_output(['git','show',FRESH_COMMIT+':'+path],cwd=ROOT),raw,path)
            prepare(ROOT,'043c4ef3ac0c46753ea283bd8dfc1e00410256ad',output_root=output)
            self.assertEqual(before,{p.relative_to(output).as_posix():p.read_bytes() for p in output.rglob('*') if p.is_file()})
