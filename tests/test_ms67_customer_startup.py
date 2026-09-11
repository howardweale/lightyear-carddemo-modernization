"""Guarded runtime correction, interruption recovery, and source retention."""
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from test_ms67_finish import (KEY, COMMIT, ENV, IMAGES, CANDIDATES, BINDINGS, SERVICES,
                             engine, finish, drills, target_journeys)
from test_ms67_drill_continuation import candidate_security, failed_domain, snapshot
from lightyear_data.cloudbank_journeys import JourneyFailure, hashed
from lightyear_data.contracts import sign

METADATA = [{'customer_changesets': 3, 'expected_changesets': 3, 'successful_changesets': 3},
            {'locks': 1, 'unlocked': 1}]


def setup(folder, explicit=True):
    obj, runtime, cloud = engine(folder)
    for service in ('transfer', 'checks'):
        runtime.resources['deployment', service]['spec']['template']['spec']['containers'][0].setdefault('env', []).append(
            {'name': 'CLOUDBANK_SECURITY_SERVICE_TOKEN_ENABLED', 'value': 'true'})
    env = runtime.resources['deployment', 'customer']['spec']['template']['spec']['containers'][0].setdefault('env', [])
    if explicit:
        env.append({'name': 'LIQUIBASE_ENABLED', 'value': 'true'})
    failed_domain(obj)
    runtime.evacuated = set()
    runtime.actions.clear()
    return obj, runtime, cloud


class CustomerStartupTests(unittest.TestCase):
    def test_cutover_allows_only_known_public_token_booleans(self):
        self.assertTrue(drills.safe_candidate_env({'name': 'CLOUDBANK_SECURITY_SERVICE_TOKEN_ENABLED', 'value': 'true'}))
        for name in ('CLOUDBANK_SECURITY_SERVICE_TOKEN_ENABLED', 'SERVICE_TOKEN', 'DATABASE_PASSWORD', 'CLIENT_SECRET'):
            self.assertFalse(drills.safe_candidate_env({'name': name, 'value': 'literal-credential'}))
            self.assertTrue(drills.safe_candidate_env({'name': name, 'valueFrom': {'secretKeyRef': {'name': 'existing', 'key': 'key'}}}))

    def test_admission_uses_original_candidate_controller_after_continuation(self):
        values = {name: {'content_sha256': name} for name in ('ms65', 'ms66-receipt', 'sql', 'load')}
        context = {'images': IMAGES, 'bindings': BINDINGS,
                   'retained_sha256': {name: value['content_sha256'] for name, value in values.items()}}
        session = SimpleNamespace(context=context, key=KEY, commit=COMMIT,
                                  state={'run_id': 'unit', 'candidate_controller_commit': finish.DRILL_CONTINUATION_SOURCE})
        with patch.object(finish, 'verify_contract'), patch.object(finish, 'verify_child'), \
             patch.object(finish.current_tools, 'verify_result'), \
             patch.object(finish.candidate_tools, 'verify_result', side_effect=JourneyFailure('stop-after-source-check')) as verify:
            with self.assertRaisesRegex(JourneyFailure, 'stop-after-source-check'):
                finish.assemble(session, values, {}, {p: {} for p in finish.CHILDREN}, {}, {})
        self.assertEqual(verify.call_args.args[1]['controller_commit'], finish.DRILL_CONTINUATION_SOURCE)

    def test_customer_reseed_failure_requires_exact_two_changed_relations(self):
        before = drills.detailed_snapshot('\n'.join(json.dumps(x) for x in [
            {'unsupported': 0}, {'relation': 'cloudbank_customer.customers', 'rows': 4, 'sha256': 'a'*64},
            {'relation': 'public.databasechangelog', 'rows': 6, 'sha256': 'b'*64}, {'schema_sha256': 'c'*64}]))
        after = copy.deepcopy(before)
        for record in after['objects'][:2]: record['sha256'] = 'd'*64
        after['state_sha256'] = hashed(after['objects'])
        row = {'kind': 'failure-domain', 'pre_state': before, 'post_state': after,
               'difference': drills.snapshot_difference(before, after)}
        drills.verify_customer_failure({'evacuation_comparisons': [row]})
        for mutate in (lambda r: r.update(kind='node'),
                       lambda r: r['post_state']['objects'][0].update(rows=3),
                       lambda r: r['post_state']['objects'].append({'sequence': 'public.seq', 'sha256': 'e'*64})):
            bad = copy.deepcopy(row); mutate(bad)
            bad['difference'] = drills.snapshot_difference(bad['pre_state'], bad['post_state'])
            with self.assertRaises(JourneyFailure): drills.verify_customer_failure({'evacuation_comparisons': [bad]})

    def test_correction_preserves_seven_rollouts_and_measures_remaining_groups(self):
        for explicit in (True, False):
            with self.subTest(explicit=explicit), tempfile.TemporaryDirectory() as folder:
                obj, runtime, _ = setup(folder, explicit)
                prior = copy.deepcopy(obj.s['completed'])
                specs = {s: runtime.deployment(s)['spec'] for s in SERVICES}
                fake = SimpleNamespace(environment=lambda: ENV, create_probe=lambda: None,
                                       direct_candidate_health=lambda s, p: {'http_status': 200}, close=lambda: None)
                with patch.object(obj, 'database_query', return_value='\n'.join(map(json.dumps, METADATA))), \
                     patch.object(obj, 'stable_snapshot', return_value=snapshot()), \
                     patch.object(drills, 'CandidateRuntime', return_value=fake), \
                     patch.object(drills, 'execute_journeys', side_effect=lambda r, b, *a, **kw: target_journeys(b, kw["run_id"])):
                    result = obj.run(repair_customer_startup=True)
                self.assertIsNone(result['reason'], result)
                drills.verify_observation(result, KEY, obj.bindings, IMAGES, CANDIDATES, ENV)
                self.assertEqual(result['customer_startup']['previous_completed'], prior)
                self.assertEqual(len([a for a in runtime.actions if a[0] == 'drain']), 2)
                for s in SERVICES:
                    if s != 'customer':
                        self.assertEqual(runtime.deployment(s)['spec'], specs[s])
                        before = next(r for r in prior['rolling']['rows'] if r['service'] == s)
                        after = next(r for r in result['completed']['rolling']['rows'] if r['service'] == s)
                        self.assertEqual(before, after)
                self.assertEqual(next(r for r in runtime.deployment('customer')['spec']['template']['spec']['containers'][0]['env']
                                      if r['name'] == 'LIQUIBASE_ENABLED')['value'], 'false')
                for mutate in (lambda v: v['customer_startup'].update(applied=False),
                               lambda v: v['customer_startup'].update(post_state=snapshot('f'*64))):
                    bad = copy.deepcopy(result); mutate(bad)
                    with self.assertRaises(JourneyFailure):
                        drills.verify_observation(sign(bad, KEY, 'unit'), KEY, obj.bindings, IMAGES, CANDIDATES, ENV)

    def test_interrupted_patch_adopts_only_exact_new_spec_and_keeps_runtime_mode(self):
        with tempfile.TemporaryDirectory() as folder:
            obj, runtime, cloud = setup(folder)
            obj.preflight(); obj.claim()
            original_patch = obj.patch
            def disconnect(*args):
                original_patch(*args)
                raise JourneyFailure('response-lost-after-applied-patch')
            with patch.object(obj, 'database_query', return_value='\n'.join(map(json.dumps, METADATA))), \
                 patch.object(obj, 'stable_snapshot', return_value=snapshot()), patch.object(obj, 'patch', side_effect=disconnect):
                with self.assertRaisesRegex(JourneyFailure, 'response-lost'): obj.repair_customer_startup()
            self.assertEqual(obj.cleanup()['status'], 'restored')
            saved = json.loads(cloud.objects[obj.journal.uri][1])
            self.assertTrue(saved['customer_startup']['applied'])
            resumed = drills.FinalDrills(runtime, CANDIDATES, obj.bindings, KEY, 'unit', obj.prefix,
                                         state=saved, cloud=cloud, pause=lambda _: None)
            resumed.preflight(); resumed.claim()
            with patch.object(resumed, 'stable_snapshot', return_value=snapshot()): resumed.repair_customer_startup()
            self.assertEqual(resumed.s['customer_startup']['status'], 'passed')
            # An interruption while the customer's measured rollout is at the
            # candidate image must still recover to the revised baseline spec.
            resumed.set_image('customer', CANDIDATES['customer'])
            self.assertEqual(resumed.cleanup()['status'], 'restored')

    def test_missing_migrations_and_unrelated_spec_drift_fail_before_patch(self):
        with tempfile.TemporaryDirectory() as folder:
            obj, runtime, _ = setup(folder)
            obj.preflight(); obj.claim()
            runtime.actions.clear()
            with patch.object(obj, 'database_query', return_value='{}'):
                with self.assertRaisesRegex(JourneyFailure, 'initialized-unlocked'): obj.repair_customer_startup()
            self.assertEqual(runtime.actions, [])
            runtime.resources['deployment', 'customer']['spec']['revisionHistoryLimit'] = 999
            with patch.object(obj, 'database_query', return_value='\n'.join(map(json.dumps, METADATA))):
                with self.assertRaisesRegex(JourneyFailure, 'baseline-spec-drift'): obj.repair_customer_startup()
            self.assertEqual(runtime.actions, [])

    def test_repair_source_transition_retains_original_candidate_and_archive_chain(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            obj, _, cloud = setup(folder)
            checkpoint = json.loads(cloud.objects[obj.journal.uri][1])
            context = {'images': IMAGES, 'bindings': BINDINGS, 'environment': ENV}
            with patch.object(finish, 'invoke', cloud), patch.object(finish, 'cloud', side_effect=lambda *a, **kw: cloud(['gcloud', *a], **kw)), \
                 patch.object(finish, 'verify_child', side_effect=lambda phase, value, *a: value):
                session = finish.Session(root, context, KEY, finish.DRILL_CONTINUATION_SOURCE)
                security = candidate_security(session.state['run_id'])
                checkpoint['run_id'] = session.state['run_id']
                checkpoint['bindings']['candidate_image_lock_sha256'] = security['candidate_lock']['content_sha256']
                session.state['candidate_build'] = {'phase': 'submitted', 'build_id': 'candidate-build'}
                session.state['completed']['candidates'] = session.publish('candidate-security.json', security)
                for phase in finish.CHILDREN: session.state['completed'][phase] = session.publish(phase+'.json', {'status': 'passed'})
                ref = session.publish('restored-drill.json', sign(checkpoint, KEY, 'unit'))
                session.state['active'] = {'phase': 'drills', 'recovery': ref}; session.save()
                old = finish.Session(root, context, KEY, finish.CUSTOMER_REPAIR_SOURCE, resume_drills=True)
                with self.assertRaises(JourneyFailure): finish.Session(root, context, KEY, COMMIT, resume_drills=True)
                with self.assertRaisesRegex(JourneyFailure, 'customer-reseed'):
                    finish.Session(root, context, KEY, COMMIT, resume_drills=True, repair_customer_startup=True)
                # Detailed-failure rejection above is real. The positive
                # transition isolates that already separately tested gate.
                with patch.object(finish, 'verify_customer_failure'):
                    new = finish.Session(root, context, KEY, COMMIT, resume_drills=True, repair_customer_startup=True)
                self.assertEqual(new.state['completed'], old.state['completed'])
                self.assertEqual(new.state['controller_transition']['previous_transition'], old.state['controller_transition'])
                self.assertEqual(finish.candidates(new)[0], security)
                again = finish.Session(root, context, KEY, COMMIT, resume_drills=True, repair_customer_startup=True)
                self.assertTrue(again.state['customer_startup_repair'])


if __name__ == '__main__': unittest.main()
