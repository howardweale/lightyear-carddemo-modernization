from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lightyear_data.contracts import seal
from lightyear_data.idempiere_comparison import compare_pair, REPORT_PATH
from lightyear_workflow.policy import CATALOG, default_policy, load_policy, parse_policy
from lightyear_workflow.planner import build_plan, classify_reason, plan_pair
from lightyear_workflow.artifacts import emit, read_snapshot, project_snapshot

ROOT = Path(__file__).resolve().parents[1]


class PolicyTests(unittest.TestCase):
    def test_every_human_and_blocked_action_rejects_every_automatic_mode(self):
        for kind, spec in CATALOG.items():
            if spec.action_class == 'autonomous':
                continue
            for mode in ('auto', 'auto-within-declared-scope', 'auto-if-unexpired'):
                with self.subTest(kind=kind, mode=mode):
                    policy = default_policy(); policy['autonomy'][kind] = mode
                    with self.assertRaises(ValueError): parse_policy(policy)

    def test_policy_may_reduce_but_not_widen_conditional_autonomy(self):
        for kind in ('apply-ledger-entry', 'extend-corpus'):
            policy = default_policy(); policy['autonomy'][kind] = 'auto'
            with self.assertRaises(ValueError): parse_policy(policy)
            policy['autonomy'][kind] = 'always-ask'
            self.assertEqual('always-ask', parse_policy(policy)['autonomy'][kind])

    def test_unknown_actions_missing_locks_caps_and_execution_mode_fail_closed(self):
        mutations = [lambda p: p['autonomy'].update({'agent-decide': 'auto'}),
                     lambda p: p['autonomy'].pop('promote-claim'),
                     lambda p: p.update(mode='execute'), lambda p: p.update(max_autonomous_iterations=True),
                     lambda p: p.update(max_autonomous_iterations=9), lambda p: p.update(halt_on=['budget']),
                     lambda p: p.update(owners={'business-owner': ''})]
        for mutate in mutations:
            policy = default_policy(); mutate(policy)
            with self.assertRaises(ValueError): parse_policy(policy)

    def test_duplicate_json_keys_cannot_hide_an_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'policy.json'
            path.write_text(json.dumps(default_policy()).replace('"propose-normalization": "always-ask"', '"propose-normalization": "auto", "propose-normalization": "always-ask"'))
            with self.assertRaisesRegex(ValueError, 'Duplicate'): load_policy(path)


class ActionTests(unittest.TestCase):
    def plan(self, oracle, postgresql):
        record = compare_pair('pair:test', oracle, postgresql)
        source = {'pair_id': 'pair:test', **{d: {'path': d + '.sql', 'logical_sha256': hashlib.sha256(s.encode()).hexdigest()}
                                           for d, s in [('oracle', oracle), ('postgresql', postgresql)]}}
        original = copy.deepcopy(record)
        result = plan_pair(record, source, default_policy())
        self.assertEqual(original, record)
        self.assertEqual(record['verdict'], result['verdict'])
        self.assertTrue(all(not a['execution_enabled'] for a in result['actions']))
        return result

    def test_divergent_numeric_domain_remains_divergent_and_requires_human(self):
        result = self.plan('ALTER TABLE x ADD y NUMBER(10,2);', 'ALTER TABLE x ADD y NUMERIC(9,2);')
        self.assertEqual('divergent', result['verdict'])
        self.assertEqual(['classify-intentional-change'], [a['kind'] for a in result['actions']])
        self.assertEqual('approval-required', result['actions'][0]['class'])
        self.assertFalse(result['actions'][0]['signature_enabled'])

    def test_date_proposal_is_scoped_and_refusal_does_not_invent_divergence(self):
        result = self.plan('ALTER TABLE x ADD y DATE;', 'ALTER TABLE x ADD y DATE;')
        action = result['actions'][0]
        self.assertEqual('undecidable', result['sub_verdict'])
        self.assertEqual('propose-normalization', action['kind'])
        self.assertIn('indeterminate remains unresolved', action['if_refused'])
        self.assertEqual(2, action['impact']['sql_units'])
        self.assertIsNone(action['impact']['suppressed_comparisons'])
        self.assertIsNone(action['owner'])
        self.assertEqual([], action['decision_provenance'])

    def test_unparsed_construct_is_our_backlog_with_named_team(self):
        result = self.plan('BEGIN NULL; END;\n/', 'DO $$ BEGIN NULL; END $$;')
        self.assertEqual('unparsed', result['sub_verdict'])
        self.assertEqual('require-parser-work', result['actions'][0]['kind'])
        self.assertEqual('LIGHTYEAR parser engineering', result['actions'][0]['owner'])

    def test_equal_static_effect_has_no_promotion_or_convergence_claim(self):
        result = self.plan('ALTER TABLE x ADD y NUMBER(10,2);', 'ALTER TABLE x ADD y NUMERIC(10,2);')
        self.assertEqual('equivalent', result['verdict'])
        self.assertEqual([], result['actions'])
        self.assertEqual('static-declared-effects', result['evidence_class'])
        self.assertEqual(0, result['observations'])
        self.assertIsNone(result['agreement'])

    def test_unknown_and_opaque_reasons_never_become_business_policy(self):
        for reason in ('new-future-reason', 'opaque-default-expression', 'ordered-effect-alignment-required'):
            self.assertEqual('unparsed', classify_reason(reason, 'parsed-but-indeterminate'))
        self.assertEqual('no-output', classify_reason('candidate-no-output', 'parsed-but-indeterminate'))
        self.assertEqual('uncovered', classify_reason('path-uncovered', 'parsed-but-indeterminate'))
        self.assertEqual('unauthorised', classify_reason('approved-provider-required', 'parsed-but-indeterminate'))

    def test_empty_output_proposes_rerun_without_claiming_it_ran(self):
        result = self.plan('', '')
        self.assertEqual('no-output', result['sub_verdict'])
        self.assertEqual('indeterminate', result['verdict'])
        self.assertEqual('rerun', result['actions'][0]['kind'])
        self.assertEqual('autonomous', result['actions'][0]['class'])
        self.assertIn('changed-inputs', result['actions'][0]['preconditions'])


class ArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = build_plan(ROOT, default_policy())

    def snapshot(self, plan=None):
        return seal({'artifact_type': 'lightyear-action-plan-snapshot', 'schema_version': '1.0',
                     'emitted_at': datetime.now(timezone.utc).isoformat(), 'plan': plan or self.plan})

    def read(self, snapshot, now=None):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'plan.json.gz'
            path.write_bytes(gzip.compress(json.dumps(snapshot).encode()))
            return read_snapshot(ROOT, path, now=now)

    def test_real_corpus_has_exact_conserved_verdicts_and_unit_denominator(self):
        report = json.loads((ROOT / REPORT_PATH).read_text())
        self.assertEqual([(r['pair_id'], r['verdict'], r['content_sha256']) for r in report['results']],
                         [(r['entity_id'], r['verdict'], r['source_verdict_sha256']) for r in self.plan['results']])
        s = self.plan['summary']
        self.assertEqual(1078, s['entities'])
        self.assertEqual(110517, sum(s['exclusive_unresolved_units'].values()))
        self.assertEqual(6595, s['parser_units_reported_by_comparator'])
        self.assertEqual(0, s['resolved_autonomously'])
        self.assertEqual(0, s['converged_cannot_improve'])
        self.assertTrue(all(n == 0 for n in self.plan['execution'].values()))

    def test_resealed_mutations_of_class_verdict_and_counts_are_rejected(self):
        for field, value in [('class', 'autonomous'), ('source_verdict', 'equivalent')]:
            changed = copy.deepcopy(self.plan)
            changed['results'][0]['actions'][0][field] = value
            changed = seal(changed)
            self.assertEqual('invalid', self.read(self.snapshot(changed))['status'])
        changed = copy.deepcopy(self.plan); changed['summary']['resolved_autonomously'] = 412
        self.assertEqual('invalid', self.read(self.snapshot(seal(changed)))['status'])

    def test_stale_valid_missing_and_corrupt_snapshots_are_explicit(self):
        snapshot = self.snapshot()
        result = self.read(snapshot, now=datetime.now(timezone.utc) + timedelta(days=2))
        self.assertEqual('stale', result['status'])
        self.assertEqual('no-executor-in-step-1', result['engine_status'])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'missing.gz'
            self.assertEqual('unavailable', read_snapshot(ROOT, path)['status'])
            path.write_bytes(b'corrupt')
            self.assertEqual('invalid', read_snapshot(ROOT, path)['status'])

    def test_pagination_and_approval_projection_are_read_only(self):
        snapshot = {'status': 'snapshot', 'plan': self.plan}
        page = project_snapshot(snapshot, action_class='approval-required', limit=20)
        self.assertEqual(223, page['total'])
        self.assertEqual(20, len(page['items']))
        self.assertTrue(all(a['class'] == 'approval-required' and not a['signature_enabled'] for a in page['items']))
        with self.assertRaises(ValueError): project_snapshot(snapshot, limit=1000)

    def test_emit_is_headless_and_does_not_mutate_source_evidence(self):
        before = (ROOT / REPORT_PATH).read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'plan.gz'
            with patch('subprocess.Popen', side_effect=AssertionError('No execution permitted')):
                snapshot = emit(ROOT, path)
            self.assertEqual(self.plan, snapshot['plan'])
        self.assertEqual(before, (ROOT / REPORT_PATH).read_bytes())

    def test_changed_source_admission_blocks_plan_instead_of_showing_green(self):
        with patch('lightyear_workflow.planner.validate_stage2_artifacts', return_value=['stage2-binding-drift']):
            with self.assertRaisesRegex(ValueError, 'admission failed'): build_plan(ROOT, default_policy())


if __name__ == '__main__':
    unittest.main()
