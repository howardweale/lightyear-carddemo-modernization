"""Cutover queue ownership, fresh fixtures and restored-prefix continuation."""
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from test_ms67_finish import KEY, COMMIT, RUN, ENV, IMAGES, CANDIDATES, BINDINGS, SERVICES, engine, finish, drills, target_journeys
from test_ms67_customer_startup import setup, METADATA
from test_ms67_drill_continuation import snapshot, candidate_security
from test_cloudbank_journeys import StatefulRuntime
from lightyear_data.cloudbank_journeys import Journeys, JourneyFailure, SCENARIOS, hashed
from lightyear_data.contracts import sign


def fake_candidate():
    return SimpleNamespace(environment=lambda: ENV, create_probe=lambda: None,
                           direct_candidate_health=lambda s, p: {'http_status': 200})


def failed_journeys(bindings, run_id):
    value = target_journeys(bindings, run_id)
    seen = False
    for i, row in enumerate(value['scenarios']):
        if row['id'] == 'checks-restart-redelivers-inflight':
            value['scenarios'][i] = {'id': row['id'], 'status': 'failed', 'reason': 'inflight-claim-not-observed'}
            seen = True
        elif seen:
            value['scenarios'][i] = {'id': row['id'], 'status': 'not-run', 'reason': 'prior-journey-failed'}
    value['status'] = 'failed'
    return sign(value, KEY, 'unit-operator')


def candidate_routes(obj):
    obj.preflight(); obj.claim(); obj.create_canaries()
    obj.s['cutover_attempt'] = {'run_id': 'ms67-cutover-' + '2'*32, 'parent_run_id': RUN}
    for service in SERVICES:
        obj.route(service, {drills.LABEL: RUN, 'app.kubernetes.io/name': service})


class CompetingConsumer(StatefulRuntime):
    """Simulate a baseline worker sharing the DB queue, irrespective of HTTP route."""
    def __init__(self, deployment_runtime):
        super().__init__()
        self.deployments = deployment_runtime

    def handle(self, service, method, path, role, body, headers):
        response = super().handle(service, method, path, role, body, headers)
        if service == 'testrunner' and response.status == 201 and self.blocked and self.deployments.pods('checks'):
            self.deliver(headers['Idempotency-Key'])
        return response


class CutoverChecksTests(unittest.TestCase):
    def test_real_journey_assertion_fails_with_competitor_and_passes_after_isolation(self):
        with tempfile.TemporaryDirectory() as folder:
            obj, runtime, _ = engine(folder)
            candidate_routes(obj)
            database = CompetingConsumer(runtime)
            driver = Journeys(database, 'before-isolation', timeout=0, pause=lambda _: None)
            driver.customer(); driver.prepare_accounts()
            # The HTTP Service already selects only the two candidate pods.
            self.assertEqual(len(runtime.get('endpoints', 'checks')['subsets'][0]['addresses']), 2)
            with self.assertRaisesRegex(JourneyFailure, 'inflight-claim-not-observed'):
                driver.checks_restart()
            old_message = driver.message_id('inflight')
            self.assertEqual(database.messages[old_message]['state'], 'PROCESSED')
            before = runtime.deployment('checks')['spec']
            obj.isolate_baseline_checks()
            second = Journeys(database, obj.s['cutover_attempt']['run_id'], timeout=0, pause=lambda _: None)
            second.prepare_accounts()
            self.assertNotEqual(second.message_id('inflight'), old_message)
            proof = second.checks_restart()
            self.assertTrue(proof)
            self.assertEqual(database.messages[second.message_id('inflight')]['attempts'], 2)
            obj.restore_baseline_checks()
            self.assertEqual(runtime.deployment('checks')['spec'], before)
            self.assertEqual(obj.cleanup()['status'], 'restored')

    def test_scale_response_loss_restores_from_signed_journal(self):
        with tempfile.TemporaryDirectory() as folder:
            obj, runtime, cloud = engine(folder)
            candidate_routes(obj)
            before = runtime.deployment('checks')['spec']
            real = obj.patch
            def disconnect(*args):
                real(*args)
                raise JourneyFailure('lost-scale-response')
            with patch.object(obj, 'patch', side_effect=disconnect):
                with self.assertRaisesRegex(JourneyFailure, 'lost-scale-response'):
                    obj.isolate_baseline_checks()
            self.assertEqual(runtime.deployment('checks')['spec']['replicas'], 0)
            saved = json.loads(cloud.objects[obj.journal.uri][1])
            resumed = drills.FinalDrills(runtime, CANDIDATES, obj.bindings, KEY, 'unit', obj.prefix,
                                         state=saved, cloud=cloud, pause=lambda _: None)
            self.assertEqual(resumed.cleanup()['status'], 'restored')
            self.assertEqual(runtime.deployment('checks')['spec'], before)

    def test_replaced_or_changed_baseline_is_never_scaled(self):
        for timing in ('before', 'after'):
            for change in ('uid', 'spec'):
                with self.subTest(timing=timing, change=change), tempfile.TemporaryDirectory() as folder:
                    obj, runtime, _ = engine(folder); candidate_routes(obj)
                    if timing == 'after': obj.isolate_baseline_checks()
                    current = runtime.resources['deployment', 'checks']
                    if change == 'uid': current['metadata']['uid'] = 'foreign'
                    else: current['spec']['revisionHistoryLimit'] = 999
                    runtime.actions.clear()
                    with self.assertRaisesRegex(JourneyFailure, 'identity-or-spec-drift'):
                        (obj.isolate_baseline_checks if timing == 'before' else obj.restore_baseline_checks)()
                    self.assertEqual(runtime.actions, [])

    def test_other_queue_consumer_is_rejected_and_baseline_recovers(self):
        with tempfile.TemporaryDirectory() as folder:
            obj, runtime, _ = engine(folder); candidate_routes(obj)
            foreign = copy.deepcopy(runtime.resources['deployment', 'checks'])
            foreign['metadata'].update(name='foreign-checks', uid='foreign')
            runtime.resources['deployment', 'foreign-checks'] = foreign
            runtime.generations['foreign-checks'] = 1
            with self.assertRaisesRegex(JourneyFailure, 'unexpected-checks-queue-consumers'):
                obj.isolate_baseline_checks()
            obj.restore_baseline_checks()
            self.assertEqual(len(runtime.pods('checks')), 2)
            self.assertIn(('deployment', 'foreign-checks'), runtime.resources)

    def test_failed_journey_is_cloud_durable_and_retry_retains_both_evacuations(self):
        with tempfile.TemporaryDirectory() as folder:
            obj, runtime, cloud = setup(folder)
            def failed(r, b, *a, **kw):
                self.assertEqual(runtime.pods('checks'), [])
                value = failed_journeys(b, kw['run_id']); kw['checkpoint'](value)
                retained = copy.deepcopy(value)
                # The canonical runner appends skipped scenarios after a failed
                # checkpoint, then performs recovery IO before its final save.
                value['scenarios'].append({'id': 'later-progress', 'status': 'not-run'})
                obj.save('recovery-after-more-journey-progress')
                durable = json.loads(cloud.objects[obj.journal.uri][1])
                self.assertEqual(durable['target_journeys'], retained)
                drills.verified(durable['target_journeys'], KEY)
                return retained
            with patch.object(obj, 'database_query', return_value='\n'.join(map(json.dumps, METADATA))), \
                 patch.object(obj, 'stable_snapshot', return_value=snapshot()), \
                 patch.object(drills, 'CandidateRuntime', return_value=fake_candidate()), \
                 patch.object(drills, 'execute_journeys', side_effect=failed):
                result = obj.run(repair_customer_startup=True)
            self.assertEqual(result['reason'], 'target-cutover-business-journeys-failed')
            saved = json.loads(cloud.objects[obj.journal.uri][1])
            self.assertEqual(saved['target_journeys'], result['target_journeys'])
            self.assertEqual(saved['checks_isolation']['status'], 'restored')
            self.assertEqual(set(saved['completed']['resilience']), {'node', 'failure-domain'})
            prior = copy.deepcopy(saved['completed'])
            first_id = saved['target_journeys']['run_id']
            first_file = Path(folder) / ('target-journeys-' + first_id) / 'journeys.json'
            first_bytes = first_file.read_bytes()
            runtime.actions.clear()
            resumed = drills.FinalDrills(runtime, CANDIDATES, obj.bindings, KEY, 'unit', obj.prefix,
                                         state=saved, cloud=cloud, pause=lambda _: None)
            def passed(r, b, *a, **kw):
                self.assertEqual(runtime.pods('checks'), [])
                self.assertNotEqual(first_id, kw['run_id'])
                value = target_journeys(b, kw['run_id']); kw['checkpoint'](value)
                return value
            with patch.object(resumed, 'stable_snapshot', return_value=snapshot()), \
                 patch.object(resumed, 'rolling', side_effect=AssertionError('repeated rolling')), \
                 patch.object(resumed, 'resilience', side_effect=AssertionError('repeated evacuations')), \
                 patch.object(drills, 'CandidateRuntime', return_value=fake_candidate()), \
                 patch.object(drills, 'execute_journeys', side_effect=passed):
                passed_result = resumed.run()
            self.assertIsNone(passed_result['reason'], passed_result)
            drills.verify_observation(passed_result, KEY, obj.bindings, IMAGES, CANDIDATES, ENV)
            self.assertEqual(first_file.read_bytes(), first_bytes)
            for group, value in prior.items(): self.assertEqual(passed_result['completed'][group], value)
            for field, value in [('baseline_pods_observed', 1), ('restored_replicas', 0), ('journey_run_id', RUN)]:
                bad = copy.deepcopy(passed_result)
                bad['checks_isolation'][field] = bad['completed']['cutover']['checks_isolation'][field] = value
                with self.assertRaises(JourneyFailure):
                    drills.verify_observation(sign(bad, KEY, 'unit'), KEY, obj.bindings, IMAGES, CANDIDATES, ENV)

    def test_source_transition_archives_failed_journey_and_preserves_candidates_and_prefix(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            obj, runtime, cloud = setup(folder)
            with patch.object(obj, 'database_query', return_value='\n'.join(map(json.dumps, METADATA))), \
                 patch.object(obj, 'stable_snapshot', return_value=snapshot()), \
                 patch.object(drills, 'CandidateRuntime', return_value=fake_candidate()), \
                 patch.object(drills, 'execute_journeys', side_effect=lambda r, b, *a, **kw: failed_journeys(b, kw['run_id'])):
                obj.run(repair_customer_startup=True)
            checkpoint = copy.deepcopy(obj.s)
            context = {'images': IMAGES, 'bindings': BINDINGS, 'environment': ENV}
            with patch.object(finish, 'invoke', cloud), patch.object(finish, 'cloud', side_effect=lambda *a, **kw: cloud(['gcloud', *a], **kw)), \
                 patch.object(finish, 'verify_child', side_effect=lambda phase, value, *a: value):
                old = finish.Session(root, context, KEY, finish.CUTOVER_REPAIR_SOURCE)
                security = candidate_security(old.state['run_id'])
                checkpoint['run_id'] = old.state['run_id']
                checkpoint['bindings']['candidate_image_lock_sha256'] = security['candidate_lock']['content_sha256']
                legacy_bindings = {'ms64_receipt_sha256': BINDINGS['ms64_receipt_sha256'],
                    'image_lock_sha256': security['candidate_lock']['content_sha256'], 'environment': ENV, 'lane': 'gke-postgresql-target'}
                journeys = failed_journeys(legacy_bindings, old.state['run_id'])
                checkpoint.pop('target_journeys', None)
                checkpoint.pop('cutover_attempt', None)
                checkpoint.pop('checks_isolation', None)
                checkpoint = sign(checkpoint, KEY, 'unit')
                old.state['candidate_controller_commit'] = finish.DRILL_CONTINUATION_SOURCE
                old.state['candidate_build'] = {'phase': 'submitted', 'build_id': 'candidate-build'}
                old.state['completed']['candidates'] = old.publish('candidate-security.json', security)
                for phase in finish.CHILDREN: old.state['completed'][phase] = old.publish(phase+'.json', {'status': 'passed'})
                old.state['active'] = {'phase': 'drills', 'recovery': old.publish('restored.json', checkpoint)}
                prior = sign({'controller_commit': finish.CUSTOMER_REPAIR_SOURCE,
                    'run_id': old.state['run_id'], 'context_sha256': hashed(context)}, KEY, 'unit')
                old.state['controller_transition'] = {'from': finish.CUSTOMER_REPAIR_SOURCE,
                    'to': finish.CUTOVER_REPAIR_SOURCE, 'previous_parent': old.publish('previous-controller.json', prior)}
                old.state['customer_startup_repair'] = True; old.save()
                path = root / 'drills' / 'target-journeys' / 'journeys.json'
                path.parent.mkdir(parents=True); path.write_text(json.dumps(journeys))
                before = path.read_bytes()
                with self.assertRaises(JourneyFailure): finish.Session(root, context, KEY, COMMIT, resume_drills=True)
                bad = copy.deepcopy(journeys); bad['scenarios'][0]['status'] = 'failed'
                path.write_text(json.dumps(sign(bad, KEY, 'unit')))
                with self.assertRaises(JourneyFailure):
                    finish.Session(root, context, KEY, COMMIT, resume_drills=True, isolate_cutover_checks=True)
                path.write_bytes(before)
                new = finish.Session(root, context, KEY, COMMIT, resume_drills=True, isolate_cutover_checks=True)
                self.assertEqual(new.state['completed'], old.state['completed'])
                self.assertEqual(new.read(new.state['controller_transition']['previous_target_journeys']), journeys)
                self.assertEqual(new.read(new.state['controller_transition']['previous_drill_failure']), checkpoint)
                self.assertEqual(finish.candidates(new)[0], security)
                self.assertEqual(path.read_bytes(), before)
                again = finish.Session(root, context, KEY, COMMIT, resume_drills=True, isolate_cutover_checks=True)
                self.assertTrue(again.state['cutover_checks_isolation'])
                bad = copy.deepcopy(checkpoint); bad['completed']['resilience'].pop('failure-domain')
                with self.assertRaises(JourneyFailure):
                    drills.verify_cutover_failure(sign(bad, KEY, 'unit'), journeys, KEY, checkpoint['bindings'], IMAGES, CANDIDATES, ENV)


if __name__ == '__main__': unittest.main()
