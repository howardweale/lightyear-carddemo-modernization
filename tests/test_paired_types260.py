"""Explicit simulations validate orchestration; these are never native evidence."""
import json
import shutil
import unittest
from unittest.mock import patch
import uuid

from lightyear_workflow import campaign_engine as engine, paired_types260 as suite, paired_types as previous
from lightyear_workflow.campaign_journals import exported
from lightyear_workflow.campaign_service import history
from lightyear_workflow.run_store import RunStore
from tests import test_paired_core100 as core

ROOT = core.ROOT


class FamilySimulation(core.FamilySimulation):
    def observe(self, lane, case):
        return suite.expected(case, lane)


class Types260Tests(unittest.TestCase):
    def setUp(self):
        self.fixture = core.Core100Tests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root, self.service, self.token = self.fixture.root, self.fixture.service, self.fixture.token
        shutil.copytree(ROOT / suite.ARTIFACTS, self.root / suite.ARTIFACTS)
        profile = self.root / suite.PROFILE
        profile.parent.mkdir(parents=True)
        profile.write_text((self.root / previous.PROFILE).read_text())

    def request(self):
        return dict(campaign_id=suite.CAMPAIGN, plan_sha256=suite.plan(self.root)['plan_sha256'],
                    request_id=str(uuid.uuid4()), accept_terms=True, reason='Explicit thirteen-family simulation; no cloud operations')

    def start(self):
        return self.service.start(self.token, self.request())['run_id']

    def run_suite(self, runner=FamilySimulation):
        run = self.start()
        return run, engine.execute(self.root, run, runner_factory=runner)

    def test_scope_binds_260_cases_and_preserves_every_prior_sql_byte(self):
        suite.verify(self.root)
        plan = suite.plan(self.root)
        self.assertEqual(len(plan['cases']), 260)
        self.assertEqual(len({c['behavior_id'] for c in plan['cases']}), 65)
        self.assertEqual(len(list((self.root / suite.ARTIFACTS / 'cases').rglob('*.sql'))), 520)
        self.assertEqual(plan['families'], list(suite.EXECUTION_FAMILIES))
        for case in previous.cases(self.root):
            for lane in ('oracle', 'alloydb'):
                self.assertEqual(suite.render(case, lane), previous.render(case, lane))
                self.assertEqual(suite.expected(case, lane), previous.expected(case, lane))
        path = self.root / suite.ARTIFACTS / 'cases/oracle/ORA-TYPE-006-CASE-01.sql'
        path.write_text(path.read_text() + '-- changed')
        with self.assertRaises(ValueError):
            suite.plan(self.root)

    def test_260_simulated_pairs_have_thirteen_bounded_signed_journals(self):
        run, result = self.run_suite()
        self.assertEqual(result['status'], 'passed-simulated')
        self.assertEqual(result['matched'], 260)
        self.assertEqual([f['matched'] for f in result['families']], [20] * 13)
        directory = engine.run_path(self.root, run)
        self.assertLess(len(RunStore(directory, read_only=True).events()), 256)
        for topic in suite.FAMILIES:
            self.assertEqual(len(RunStore(directory / 'families' / topic, read_only=True).events()), 60)
        auth = engine.get_authorization(self.root, run)
        value = engine.read_run(self.root, run, suite.CAMPAIGN)
        self.assertEqual(exported(value['events'], auth, engine.public_key(self.root)), value['events'])
        with patch.object(RunStore, 'events', side_effect=AssertionError('History may not open journals')):
            self.assertEqual(history(self.root, suite.CAMPAIGN)['runs'][0]['matched'], 260)
        self.assertEqual(engine.read_run(self.root, run, previous.CAMPAIGN)['status'], 'invalid')

    def test_one_changed_bit_fails_without_stopping_remaining_families(self):
        class ChangedBit(FamilySimulation):
            def observe(self, lane, case):
                value = super().observe(lane, case)
                if lane == 'alloydb' and case['id'] == 'ORA-TYPE-006-CASE-01':
                    value['canonical'] = '3FC00001'
                return value
        _, value = self.run_suite(ChangedBit)
        self.assertEqual(value['status'], 'failed')
        self.assertEqual(value['comparisons_completed'], 260)
        self.assertEqual(value['matched'], 259)
        self.assertTrue(value['cleanup']['complete'])

    def test_interruption_retains_completed_families_and_blocks_only_remaining(self):
        class Broken(FamilySimulation):
            def observe(self, lane, case):
                if case['topic'] == 'binary-float':
                    raise TimeoutError('Explicit simulated interruption')
                return super().observe(lane, case)
        _, value = self.run_suite(Broken)
        self.assertEqual(value['matched'], 140)
        self.assertEqual(sum(f['blocked'] for f in value['families']), 120)
        self.assertTrue(value['cleanup']['complete'])

    def test_missing_late_family_cannot_preserve_a_verified_pass(self):
        run, _ = self.run_suite()
        directory = engine.run_path(self.root, run) / 'families'
        shutil.copyfile(directory / 'interval-ym/events.sqlite3', directory / 'interval-ds/events.sqlite3')
        value = engine.read_run(self.root, run, suite.CAMPAIGN)
        self.assertEqual(value['status'], 'invalid')
        self.assertNotIn('matched', value)
        self.assertEqual(history(self.root, suite.CAMPAIGN)['runs'][0]['matched'], 260)

    def test_new_contracts_reject_wrong_codes_null_types_and_bits(self):
        for case in suite.cases(self.root):
            if case['topic'] in previous.FAMILIES:
                continue
            a, b = suite.expected(case, 'oracle'), suite.expected(case, 'alloydb')
            self.assertTrue(suite.compare(case, a, b)['equivalent'])
            raw = suite.MARKER + json.dumps(dict(case_id=case['id'], observations=b))
            self.assertEqual(suite.parse(raw, case, 'alloydb'), b)
            for key in b:
                wrong = {**b, key: '' if b[key] is None else True}
                self.assertFalse(suite.compare(case, a, wrong)['equivalent'])
            with self.assertRaises(ValueError):
                suite.parse(raw + '\n' + raw, case, 'alloydb')

    def test_260_does_not_inherit_100_authorization(self):
        pending = self.fixture.start()
        with self.assertRaisesRegex(ValueError, 'active'):
            self.start()
        engine.execute(self.root, pending, runner_factory=core.FamilySimulation)
        request = self.request()
        request['plan_sha256'] = previous.plan(self.root)['plan_sha256']
        with self.assertRaises(ValueError):
            self.service.start(self.token, request)


if __name__ == '__main__':
    unittest.main()
