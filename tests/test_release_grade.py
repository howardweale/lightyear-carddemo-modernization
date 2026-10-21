"""Synthetic CI-only release facts; never production trust or retained evidence."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from lightyear_factory.release_grade import NAMES, checklist, reasons, paragraph


def release_fixture(root):
    root = Path(root)
    def write(name, value):
        path = 'docs/factory/fixture-release-'+name+'.json'
        target = root/path
        target.parent.mkdir(parents=True, exist_ok=True)
        raw = (json.dumps(value, sort_keys=True)+'\n').encode()
        target.write_bytes(raw)
        return {'path': path, 'sha256': sha256(raw).hexdigest()}
    head = 'a'*40
    url = 'https://github.com/howardweale/lightyear-carddemo-modernization/releases/download/evidence-2026-10-18-fixture/receipt.json'
    asset = dict(url=url, bytes=3, sha256=sha256(b'abc').hexdigest())
    manifest = write('manifest', dict(schema='public-evidence-retention/1',
        repository='howardweale/lightyear-carddemo-modernization', scope='public CardDemo only',
        source_head=head, source_run=123, assets=[asset]))
    verification = write('verification', dict(schema='public-evidence-retention-verification/1',
        manifest_sha256=manifest['sha256'], assets=[dict(asset, verified=True)]))
    required = [dict(name=name, app_id=15368) for name in ('required-ci', 'documentation-and-lint')]
    campaign = write('campaign', dict(schema='release-grade-campaign/1',
        repository='howardweale/lightyear-carddemo-modernization', head=head, run_id=123,
        event='push', branch='main', observed_at='2026-10-18T16:00:00Z',
        protection=dict(strict=True, required_checks=required),
        checks=[dict(row, head=head, status='completed', conclusion='success') for row in required],
        applicable_workflows=['.github/workflows/fixture.yml'],
        workflows=[dict(path='.github/workflows/fixture.yml', run_id=123, head=head, event='push',
            branch='main', status='completed', conclusion='success',
            applicable_jobs=[dict(status='completed', conclusion='success',
                applicable_steps=[dict(status='completed', conclusion='success')])])]))
    return dict(verdict='equivalent', oracle_status='qualified', run_class='release',
        fixture_only=False, disposable_ci_signatures_only=False, evidence_head=head,
        release_grade=dict(retention_manifest=manifest, retention_verification=verification,
                           campaign=campaign, claim_scope='twin', native_runtime_claimed=False))


class ReleaseGradeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.verdict = release_fixture(self.root)
        self.key = b'unit-fixture-public-key'
        self.options = dict(root=self.root, scope='twin', review_key=self.key,
            production_review_key_sha256=sha256(self.key).hexdigest(), reviews_verified=True)

    def checks(self, verdict=None, **changes):
        return checklist(self.verdict if verdict is None else verdict, **{**self.options, **changes})

    def rewrite(self, name, change):
        ref = self.verdict['release_grade'][name]
        path = self.root/ref['path']
        value = json.loads(path.read_bytes())
        change(value)
        raw = (json.dumps(value)+'\n').encode()
        path.write_bytes(raw)
        ref['sha256'] = sha256(raw).hexdigest()

    def test_each_item_fails_alone_and_changes_rendered_text(self):
        self.assertEqual([], reasons(self.checks()))
        mutations = {
            NAMES[0]: lambda v: v.update(oracle_status='provisional'),
            NAMES[1]: lambda v: v.update(run_class='engineering'),
            NAMES[2]: lambda v: v['release_grade'].pop('retention_verification'),
            NAMES[3]: lambda v: v['release_grade'].update(campaign={**v['release_grade']['campaign'], 'sha256':'0'*64}),
            NAMES[4]: lambda v: v.update(disposable_ci_signatures_only=True),
            NAMES[5]: lambda v: v['release_grade'].update(native_runtime_claimed=True),
        }
        for expected, mutate in mutations.items():
            with self.subTest(item=expected):
                changed = deepcopy(self.verdict)
                mutate(changed)
                result = self.checks(changed)
                # Retention checks bind campaign identity but not its trust hash;
                # changed campaign bytes must also invalidate that reference.
                expected_names = [expected] if expected != NAMES[3] else [NAMES[2], NAMES[3]]
                self.assertEqual(expected_names, reasons(result))
                self.assertNotEqual(paragraph(self.checks()), paragraph(result))
                self.assertIn(expected, paragraph(result))

    def test_campaign_gate_can_fail_independently(self):
        self.rewrite('campaign', lambda x: x['protection'].update(strict=False))
        self.assertEqual([NAMES[3]], reasons(self.checks()))

    def test_release_evaluates_each_named_gate_after_signature_verification(self):
        from lightyear_factory.scenario_policy import PROPOSAL, issue, release
        from lightyear_mainframe.zos_evidence import Signer, initialize_key
        key = self.root/'fixture-judge.pem'
        initialize_key(key)
        signer = Signer(key)
        adequacy = dict(instrumented=True, decision_outcomes='4/4', legacy_mutants_killed='50/50',
            coverage_by_class={'business-logic': {'fraction':'4/4'}},
            systematic_mutation=dict(counts={'killed-divergent':45,'killed-failure':5,'survived':0,
                'not-compiled':0,'equivalent (argued, listed)':0}, eligible_count=50,
                excluded_equivalents=0,equivalent_dispositions=[],unresolved_survivors=[],not_compiled=[]),
            distinct_values_per_output_field={'amount':2},uncovered=[])
        def evaluate(value):
            verdict = signer.sign(value)
            report = issue(verdict, adequacy, ['amount'], signer)
            policy = signer.sign(dict(schema='scenario-policy-approval/1',
                verdict_sha256=verdict['content_sha256'],assessment_sha256=report['content_sha256'],threshold=PROPOSAL))
            return release(verdict, report, signer.public, policy, signer.public,
                release_evidence_root=self.root, production_review_key_sha256=sha256(signer.public).hexdigest())
        self.assertTrue(evaluate(self.verdict)['releasable'])
        for name in NAMES:
            self.verdict = release_fixture(self.root)
            if name == NAMES[0]: self.verdict['oracle_status'] = 'provisional'
            if name == NAMES[1]: self.verdict['run_class'] = 'engineering'
            if name == NAMES[2]: self.verdict['release_grade'].pop('retention_verification')
            if name == NAMES[3]: self.rewrite('campaign', lambda x:x['protection'].update(strict=False))
            if name == NAMES[4]: self.verdict['disposable_ci_signatures_only'] = True
            if name == NAMES[5]: self.verdict['release_grade']['native_runtime_claimed'] = True
            result = evaluate(self.verdict)
            self.assertFalse(result['releasable'], name)
            self.assertEqual([name], result['reasons'])
            self.assertEqual([name], reasons(result['release_grade']))

    def test_production_key_is_external_and_reviews_are_required(self):
        for changes in ({'production_review_key_sha256':None}, {'review_key':b'wrong'},
                        {'reviews_verified':False}):
            self.assertEqual([NAMES[4]], reasons(self.checks(**changes)))
        self.verdict['production_review_key_sha256'] = sha256(self.key).hexdigest()
        self.assertEqual([NAMES[4]], reasons(self.checks(production_review_key_sha256=None)))
        self.verdict['fixture_only'] = True
        self.assertEqual([NAMES[4]], reasons(self.checks()))

    def test_tampered_bytes_missing_values_and_unsafe_paths_refuse(self):
        ref = self.verdict['release_grade']['retention_verification']
        (self.root/ref['path']).write_bytes(b'{}')
        self.assertEqual([NAMES[2]], reasons(self.checks()))
        ref['path'] = '../outside.json'
        self.assertEqual([NAMES[2]], reasons(self.checks()))
        self.assertEqual(list(NAMES), reasons(self.checks({})))
        self.assertEqual(list(NAMES), reasons(self.checks({'release_grade':None})))

    def test_each_campaign_defect_and_cross_head_refuse(self):
        changes = [lambda x:x.update(event='pull_request'), lambda x:x.update(branch='topic'),
            lambda x:x.update(head='b'*40), lambda x:x.update(observed_at='2026-10-18'),
            lambda x:x.update(applicable_workflows=[]), lambda x:x['checks'][0].update(conclusion='failure'),
            lambda x:x['checks'][0].update(app_id=99), lambda x:x['workflows'][0].update(status='in_progress'),
            lambda x:x['workflows'][0]['applicable_jobs'][0].update(conclusion='cancelled')]
        for change in changes:
            self.verdict = release_fixture(self.root)
            self.rewrite('campaign', change)
            self.assertIn(NAMES[3], reasons(self.checks()))

    def test_retention_requires_all_assets_and_matching_campaign(self):
        for change in (lambda x:x['assets'][0].update(verified=False),
                       lambda x:x['assets'].clear(), lambda x:x['assets'].append(x['assets'][0]),
                       lambda x:x.update(manifest_sha256='f'*64)):
            self.verdict = release_fixture(self.root)
            self.rewrite('retention_verification', change)
            self.assertEqual([NAMES[2]], reasons(self.checks()))
        self.verdict = release_fixture(self.root)
        self.rewrite('campaign', lambda x:x.update(run_id=999))
        self.assertIn(NAMES[2], reasons(self.checks()))

    def test_native_flags_cannot_create_a_verifier(self):
        self.verdict['release_grade'].update(claim_scope='zos-facing', native_runtime_claimed=True,
                                            native_capture_verified=True)
        self.assertEqual([NAMES[5]], reasons(self.checks(scope='zos-facing')))
