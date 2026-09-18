"""Explicit simulations of the 100-pair workflow; not native evidence."""
import json
from contextlib import closing
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch
import uuid

from lightyear_workflow import campaign_engine as engine, paired_types as suite
from lightyear_workflow.campaign_service import history, list_runs
from lightyear_workflow.run_store import RunStore
from tests import test_paired_campaign as pilot

ROOT = pilot.ROOT


class FamilySimulation(pilot.SimulatedRunner):
    def observe(self, lane, case):
        return suite.expected(case, lane)


class Core100Tests(unittest.TestCase):
    def setUp(self):
        self.fixture = pilot.PairedCampaignTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.service, self.token = self.fixture.service, self.fixture.token
        shutil.copytree(ROOT / suite.ARTIFACTS, self.root / suite.ARTIFACTS)
        profile = self.root / suite.PROFILE
        profile.parent.mkdir(parents=True)
        profile.write_text((self.root / 'work/campaigns/oracle26ai-alloydb-number/profile.json').read_text())

    def request(self):
        return {'campaign_id': suite.CAMPAIGN, 'plan_sha256': suite.plan(self.root)['plan_sha256'],
                'request_id': str(uuid.uuid4()), 'accept_terms': True, 'reason': 'Approve this explicitly simulated five-family test'}

    def start(self):
        return self.service.start(self.token, self.request())['run_id']

    def run_suite(self, runner=FamilySimulation):
        run = self.start()
        return run, engine.execute(self.root, run, runner_factory=runner)

    def test_materialized_sql_and_exact_plan_bind_all_families(self):
        suite.verify(self.root)
        plan = suite.plan(self.root)
        self.assertEqual(plan['families'], list(suite.FAMILIES))
        self.assertEqual(len(plan['cases']), 100)
        self.assertEqual(len({c['behavior_id'] for c in plan['cases']}), 25)
        self.assertEqual(len(list((self.root / suite.ARTIFACTS / 'cases').rglob('*.sql'))), 200)
        path = next((self.root / suite.ARTIFACTS / 'cases/oracle').glob('*.sql'))
        path.write_text(path.read_text() + '-- changed')
        with self.assertRaises(ValueError):
            suite.plan(self.root)

    def test_hundred_pairs_use_five_bounded_journals_and_signed_checkpoints(self):
        run, result = self.run_suite()
        self.assertEqual(result['status'], 'passed-simulated')
        self.assertEqual(result['matched'], 100)
        self.assertEqual([r['matched'] for r in result['families']], [20] * 5)
        directory = engine.run_path(self.root, run)
        self.assertLess(len(RunStore(directory, read_only=True).events()), 256)
        for topic in suite.FAMILIES:
            self.assertEqual(len(RunStore(directory / 'families' / topic, read_only=True).events()), 60)
        self.assertEqual(engine.read_run(self.root, run, suite.CAMPAIGN)['matched'], 100)
        with patch.object(RunStore, 'events', side_effect=AssertionError('History must not open journals')):
            indexed = history(self.root, suite.CAMPAIGN)
            self.assertEqual(indexed['runs'][0]['matched'], 100)
            self.assertEqual(len(indexed['runs'][0]['families']), 5)

    def test_one_native_value_change_fails_one_pair_without_losing_other_families(self):
        class Difference(FamilySimulation):
            def observe(self, lane, case):
                value = super().observe(lane, case)
                if lane == 'alloydb' and case['id'] == 'ORA-TYPE-016-CASE-01':
                    value['canonical'] = 'A'  # Padding must never be normalized in the comparator.
                return value
        _, result = self.run_suite(Difference)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['comparisons_completed'], 100)
        self.assertEqual(result['matched'], 99)
        self.assertEqual(result['families'][1]['mismatched'], 1)
        self.assertTrue(result['cleanup']['complete'])

    def test_missing_or_swapped_family_journal_clears_figures_but_keeps_history(self):
        run, _ = self.run_suite()
        directory = engine.run_path(self.root, run) / 'families'
        shutil.copyfile(directory / 'number/events.sqlite3', directory / 'char/events.sqlite3')
        value = engine.read_run(self.root, run, suite.CAMPAIGN)
        self.assertEqual(value['status'], 'invalid')
        self.assertNotIn('matched', value)
        self.assertEqual(history(self.root, suite.CAMPAIGN)['runs'][0]['matched'], 100)

    def test_resealing_family_cannot_escape_parent_checkpoint(self):
        run, _ = self.run_suite()
        directory = engine.run_path(self.root, run) / 'families/char'
        # Even an authority-signed extra event cannot modify a closed family.
        from lightyear_workflow.campaign_journals import signed_append
        auth = engine.get_authorization(self.root, run)
        store = RunStore(directory)
        try:
            signed_append(store, engine.Signer(self.root), auth, 'observation',
                          {'family': 'char', 'lane': 'oracle', 'case_id': 'ORA-TYPE-016-CASE-01',
                           'observations': {}, 'evidence_class': 'simulated'}, 'char')
        finally:
            store.close()
        self.assertEqual(engine.read_run(self.root, run, suite.CAMPAIGN)['status'], 'invalid')

    def test_failure_preserves_partial_family_and_blocks_unexecuted_cases(self):
        class Broken(FamilySimulation):
            def observe(self, lane, case):
                if case['topic'] == 'char':
                    raise RuntimeError('Deliberate simulation failure')
                return super().observe(lane, case)
        _, result = self.run_suite(Broken)
        self.assertEqual(result['matched'], 20)
        self.assertEqual(sum(f['blocked'] for f in result['families']), 80)
        self.assertEqual(result['status'], 'failed')
        self.assertTrue(result['cleanup']['complete'])

    def test_campaign_scope_and_shared_resource_exclusion(self):
        old = self.fixture.start()
        with self.assertRaisesRegex(ValueError, 'active'):
            self.start()
        engine.execute(self.root, old, runner_factory=pilot.SimulatedRunner)
        new = self.start()
        self.assertEqual(engine.read_run(self.root, old, suite.CAMPAIGN)['status'], 'invalid')
        self.assertEqual(engine.read_run(self.root, new)['status'], 'invalid')
        self.assertEqual(len(list_runs(self.root)['runs']), 1)
        self.assertEqual(len(list_runs(self.root, suite.CAMPAIGN)['runs']), 1)

    def test_diagnostic_mapping_is_exact_and_empty_string_is_not_null(self):
        for case in suite.cases(self.root):
            a, b = suite.expected(case, 'oracle'), suite.expected(case, 'alloydb')
            self.assertTrue(suite.compare(case, a, b)['equivalent'])
            if 'overflow_code' in b:
                self.assertFalse(suite.compare(case, a, {**b, 'overflow_code': 'XX000'})['equivalent'])
        case = next(c for c in suite.cases(self.root) if c['id'] == 'ORA-TYPE-021-CASE-01')
        self.assertFalse(suite.compare(case, suite.expected(case, 'oracle'), {'canonical': ''})['equivalent'])
        for output in ('', suite.MARKER + '{}', suite.MARKER + '{}\n' + suite.MARKER + '{}'):
            with self.assertRaises(ValueError):
                suite.parse(output, case, 'oracle')

    def test_partial_family_recovery_never_replays_sql_and_exports_verify(self):
        from lightyear_workflow.campaign_journals import signed_append, exported
        run = self.start()
        auth, signer = engine.get_authorization(self.root, run), engine.Signer(self.root)
        directory = engine.run_path(self.root, run)
        with closing(RunStore(directory)) as parent:
            signed_append(parent, signer, auth, 'started', {}, 'campaign')
            signed_append(parent, signer, auth, 'identities', {'identities': FamilySimulation(None, None, None, None).identities()}, 'campaign')
            signed_append(parent, signer, auth, 'family-start', {'family': 'number'}, 'campaign')
        case = suite.cases(self.root)[0]
        with closing(RunStore(directory / 'families/number')) as child:
            signed_append(child, signer, auth, 'observation', {'family': 'number', 'lane': 'oracle', 'case_id': case['id'], 'observations': suite.expected(case, 'oracle'), 'evidence_class': 'simulated'}, 'number')
        with patch('lightyear_workflow.campaign_gcp.GcpRunner', side_effect=AssertionError('No resource recorded; never retry SQL')):
            recovery = engine.recover(self.root, run)
        self.assertFalse(recovery['sql_retried'])
        value = engine.read_run(self.root, run, suite.CAMPAIGN)
        self.assertEqual(value['source_completed'], 1)
        self.assertEqual(value['status'], 'failed')
        self.assertEqual(sum(f['blocked'] for f in value['families']), 100)
        self.assertEqual(exported(value['events'], auth, signer.public), value['events'])
        with self.assertRaises(ValueError):
            exported(value['events'][1:], auth, signer.public)


if __name__ == '__main__':
    unittest.main()
