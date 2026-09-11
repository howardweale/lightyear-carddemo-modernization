"""Service version races, fail-closed ownership and retained rollback failures."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_ms67_finish import KEY, COMMIT, RUN, ENV, IMAGES, CANDIDATES, BINDINGS, SERVICES, engine, finish, drills, target_journeys
from test_ms67_customer_startup import setup, METADATA
from test_ms67_cutover_checks import fake_candidate
from test_ms67_drill_continuation import snapshot, candidate_security
from lightyear_data.cloudbank_journeys import JourneyFailure, hashed
from lightyear_data.contracts import sign


def target(service='azn-server'):
    return {drills.LABEL: RUN, 'app.kubernetes.io/name': service}


def bump(runtime, service='azn-server'):
    meta = runtime.resources['service', service]['metadata']
    meta['resourceVersion'] = str(int(meta['resourceVersion']) + 1)
    meta['annotations'] = {'controller-observation': meta['resourceVersion']}


def passed_journeys_failed_rollback(folder):
    obj, runtime, cloud = setup(folder)
    real = obj.patch
    def reject(kind, name, current, operations):
        if kind == 'service' and name == 'azn-server' and obj.s.get('pre_rollback_state'):
            raise JourneyFailure('operator-command-failed')
        return real(kind, name, current, operations)
    # Reproduce the preceding worker's undifferentiated error after the target
    # journeys and snapshot. Its ordinary cleanup must still restore everything.
    original_cutover = obj.cutover
    def cutover():
        with patch.object(obj, 'patch', side_effect=reject):
            try:
                original_cutover()
            except JourneyFailure as exc:
                if str(exc) == 'service-route-patch-failed-azn-server':
                    raise JourneyFailure('operator-command-failed') from None
                raise
    with patch.object(obj, 'database_query', return_value='\n'.join(map(json.dumps, METADATA))), \
         patch.object(obj, 'stable_snapshot', return_value=snapshot()), \
         patch.object(drills, 'CandidateRuntime', return_value=fake_candidate()), \
         patch.object(drills, 'execute_journeys', side_effect=lambda r, b, *a, **kw: target_journeys(b, kw['run_id'])), \
         patch.object(obj, 'cutover', side_effect=cutover):
        result = obj.run(repair_customer_startup=True)
    if result['reason'] != 'operator-command-failed' or result['recovery']['status'] != 'restored':
        raise AssertionError(result)
    return obj, runtime, cloud, result


class RollbackRoutesTests(unittest.TestCase):
    def test_version_change_during_intent_reproduces_old_failure_and_new_route_passes(self):
        with tempfile.TemporaryDirectory() as folder:
            obj, runtime, cloud = engine(folder); obj.preflight(); obj.claim()
            stale = runtime.get('service', 'azn-server')
            real_intent = obj.intent
            def intent(*args):
                real_intent(*args)
                bump(runtime)
            with patch.object(obj, 'intent', side_effect=intent):
                obj.route('azn-server', target())
            self.assertEqual(runtime.get('service', 'azn-server')['spec']['selector'], target())
            with self.assertRaisesRegex(JourneyFailure, 'test-json-patch-conflict'):
                obj.patch('service', 'azn-server', stale,
                          [{'op': 'replace', 'path': '/spec/selector', 'value': target()}])
            saved = json.loads(cloud.objects[obj.journal.uri][1])
            self.assertEqual(saved['route_operation']['patch_attempts'], 1)
            self.assertEqual(saved['route_operation']['operation'], 'desired-route-verified')

    def test_atomic_conflict_is_retried_only_after_unchanged_spec_readback(self):
        for always in (False, True):
            with self.subTest(always=always), tempfile.TemporaryDirectory() as folder:
                obj, runtime, _ = engine(folder); obj.preflight(); obj.claim()
                real = obj.patch
                calls = []
                def conflict(kind, name, current, operations):
                    calls.append(current['metadata']['resourceVersion'])
                    if always or len(calls) == 1: bump(runtime)
                    try: return real(kind, name, current, operations)
                    except JourneyFailure as exc:
                        if str(exc) == 'test-json-patch-conflict':
                            raise JourneyFailure('operator-command-failed') from None
                        raise
                with patch.object(obj, 'patch', side_effect=conflict):
                    if always:
                        with self.assertRaisesRegex(JourneyFailure, 'service-route-patch-failed-azn-server'):
                            obj.route('azn-server', target())
                    else:
                        obj.route('azn-server', target())
                self.assertEqual(len(calls), 3 if always else 2)
                self.assertEqual(len(set(calls)), len(calls))

    def test_lost_committed_response_is_adopted_from_full_spec_readback(self):
        with tempfile.TemporaryDirectory() as folder:
            obj, runtime, _ = engine(folder); obj.preflight(); obj.claim()
            real = obj.patch
            def lost(*args):
                real(*args)
                raise JourneyFailure('operator-command-unavailable-or-timed-out')
            with patch.object(obj, 'patch', side_effect=lost) as calls:
                obj.route('azn-server', target())
            self.assertEqual(calls.call_count, 1)
            self.assertEqual(obj.s['route_operation']['operation'], 'desired-route-verified-after-command-error')
            self.assertEqual(runtime.get('service', 'azn-server')['spec']['selector'], target())

    def test_uid_spec_selector_and_lease_drift_are_never_overwritten(self):
        for timing in ('intent', 'patch'):
            for change in ('uid', 'spec', 'selector', 'deleting', 'lease'):
                with self.subTest(timing=timing, change=change), tempfile.TemporaryDirectory() as folder:
                    obj, runtime, _ = engine(folder); obj.preflight(); obj.claim()
                    def mutate():
                        value = runtime.resources['service', 'azn-server']
                        if change == 'uid': value['metadata']['uid'] = 'replacement'
                        elif change == 'spec': value['spec']['sessionAffinity'] = 'ClientIP'
                        elif change == 'selector': value['spec']['selector'] = {'foreign': 'route'}
                        elif change == 'deleting': value['metadata']['deletionTimestamp'] = 'now'
                        else: runtime.resources['lease', drills.LEASE]['spec']['holderIdentity'] = 'another-run'
                    real = obj.intent
                    def intent(*args):
                        real(*args)
                        mutate()
                    def rejected(*args):
                        mutate(); bump(runtime)
                        raise JourneyFailure('operator-command-failed')
                    with patch.object(obj, 'intent', side_effect=intent if timing == 'intent' else real), \
                         patch.object(obj, 'patch', side_effect=rejected) as calls:
                        with self.assertRaises(JourneyFailure): obj.route('azn-server', target())
                    self.assertEqual(calls.call_count, 0 if timing == 'intent' else 1)
                    self.assertNotEqual(runtime.get('service', 'azn-server')['spec']['selector'], target())

    def test_failed_checkpoint_blocks_patch_and_unchanged_version_error_is_not_retried(self):
        with tempfile.TemporaryDirectory() as folder:
            obj, runtime, cloud = engine(folder); obj.preflight(); obj.claim()
            cloud.fail_reads = True
            with patch.object(obj, 'patch') as calls:
                with self.assertRaises(JourneyFailure): obj.route('azn-server', target())
            calls.assert_not_called()
        with tempfile.TemporaryDirectory() as folder:
            obj, runtime, _ = engine(folder); obj.preflight(); obj.claim()
            with patch.object(obj, 'patch', side_effect=JourneyFailure('operator-command-failed')) as calls:
                with self.assertRaisesRegex(JourneyFailure, 'service-route-patch-failed-azn-server'):
                    obj.route('azn-server', target())
            self.assertEqual(calls.call_count, 1)

    def test_command_success_requires_exact_readback_and_new_attempt_clears_old_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            obj, runtime, _ = engine(folder); obj.preflight(); obj.claim()
            with patch.object(obj, 'patch', return_value='success'):
                with self.assertRaisesRegex(JourneyFailure, 'service-route-readback-mismatch-azn-server'):
                    obj.route('azn-server', target())
            self.assertNotEqual(runtime.get('service', 'azn-server')['spec']['selector'], target())
        with tempfile.TemporaryDirectory() as folder:
            obj, _, _, _ = passed_journeys_failed_rollback(folder)
            old = copy.deepcopy(obj.s['pre_rollback_state'])
            with patch.object(obj, 'create_canaries', side_effect=JourneyFailure('new-attempt-interrupted')):
                with self.assertRaisesRegex(JourneyFailure, 'new-attempt-interrupted'): obj.cutover()
            self.assertNotIn('pre_rollback_state', obj.s)
            self.assertNotIn('target_journeys', obj.s)
            self.assertEqual(obj.s['prior_cutover_attempts'][-1]['pre_rollback_state'], old)

    def test_failure_context_survives_cleanup_and_retry_reuses_only_completed_groups(self):
        with tempfile.TemporaryDirectory() as folder:
            obj, runtime, cloud, result = passed_journeys_failed_rollback(folder)
            context = result['failure_context']
            self.assertEqual(context['phase'], 'route-azn-server-intent')
            self.assertEqual(context['last_route_operation']['operation'], 'patch-service-selector-failed')
            self.assertEqual(context['last_route_operation']['service'], 'azn-server')
            saved = json.loads(cloud.objects[obj.journal.uri][1])
            drills.verify_rollback_failure(saved, KEY, obj.bindings, IMAGES, CANDIDATES, ENV)
            old_journeys = copy.deepcopy(saved['target_journeys'])
            old_prefix = copy.deepcopy(saved['completed'])
            old_snapshot = copy.deepcopy(saved['pre_rollback_state'])
            runtime.actions.clear()
            resumed = drills.FinalDrills(runtime, CANDIDATES, obj.bindings, KEY, 'unit', obj.prefix,
                                        state=saved, cloud=cloud, pause=lambda _: None)
            with patch.object(resumed, 'stable_snapshot', return_value=snapshot()), \
                 patch.object(drills, 'CandidateRuntime', return_value=fake_candidate()), \
                 patch.object(drills, 'execute_journeys', side_effect=lambda r, b, *a, **kw: target_journeys(b, kw['run_id'])):
                next_result = resumed.run(repair_customer_startup=True)
            drills.verify_observation(next_result, KEY, obj.bindings, IMAGES, CANDIDATES, ENV)
            self.assertIsNone(next_result['failure_context'])
            self.assertTrue(all(next_result['completed'][k] == v for k, v in old_prefix.items()))
            self.assertFalse(any(a[0] == 'drain' for a in runtime.actions))
            self.assertNotEqual(next_result['target_journeys']['run_id'], old_journeys['run_id'])
            archived = resumed.s['prior_cutover_attempts'][-1]
            self.assertEqual(archived['target_journeys'], old_journeys)
            self.assertEqual(archived['pre_rollback_state'], old_snapshot)
            self.assertEqual(archived['failure_context'], context)

    def test_continuation_rejects_invalid_signed_prefix_and_preserves_exact_original_records(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            obj, _, cloud, _ = passed_journeys_failed_rollback(folder)
            checkpoint = json.loads(cloud.objects[obj.journal.uri][1])
            mutations = [lambda v: v.update(cleanup_required=True), lambda v: v.update(failure='other'),
                lambda v: v.pop('pre_rollback_state'),
                lambda v: v['pre_rollback_state'].update(state_sha256='0'*64),
                lambda v: v['completed']['resilience'].pop('failure-domain'),
                lambda v: v['checks_isolation'].update(baseline_pods_observed=2),
                lambda v: v['cutover_attempt'].update(parent_run_id='other'),
                lambda v: v['target_journeys']['signature'].update(value='0'*64)]
            for mutate in mutations:
                bad = copy.deepcopy(checkpoint); mutate(bad)
                with self.assertRaises(JourneyFailure):
                    drills.verify_rollback_failure(sign(bad, KEY, 'unit'), KEY, obj.bindings, IMAGES, CANDIDATES, ENV)
            context = {'images': IMAGES, 'bindings': BINDINGS, 'environment': ENV}
            with patch.object(finish, 'invoke', cloud), \
                 patch.object(finish, 'cloud', side_effect=lambda *a, **kw: cloud(['gcloud', *a], **kw)), \
                 patch.object(finish, 'verify_child', side_effect=lambda phase, value, *a: value):
                old = finish.Session(root, context, KEY, finish.ROUTE_REPAIR_SOURCE)
                security = candidate_security(old.state['run_id'])
                checkpoint['run_id'] = old.state['run_id']
                checkpoint['cutover_attempt']['parent_run_id'] = old.state['run_id']
                checkpoint['bindings']['candidate_image_lock_sha256'] = security['candidate_lock']['content_sha256']
                journeys = checkpoint['target_journeys']
                journeys['bindings']['image_lock_sha256'] = security['candidate_lock']['content_sha256']
                checkpoint['target_journeys'] = sign(journeys, KEY, 'unit')
                checkpoint = sign(checkpoint, KEY, 'unit')
                old.state.update(candidate_controller_commit=finish.DRILL_CONTINUATION_SOURCE,
                    candidate_build={'phase': 'submitted', 'build_id': 'candidate-build'},
                    customer_startup_repair=True, cutover_checks_isolation=True)
                old.state['completed']['candidates'] = old.publish('candidate-security.json', security)
                for phase in finish.CHILDREN: old.state['completed'][phase] = old.publish(phase+'.json', {'status': 'passed'})
                old.state['active'] = {'phase': 'drills', 'recovery': old.publish('restored.json', checkpoint)}
                prior = sign({'controller_commit': finish.CUTOVER_REPAIR_SOURCE,
                    'run_id': old.state['run_id'], 'context_sha256': hashed(context)}, KEY, 'unit')
                old.state['controller_transition'] = {'from': finish.CUTOVER_REPAIR_SOURCE,
                    'to': finish.ROUTE_REPAIR_SOURCE, 'previous_parent': old.publish('previous-controller.json', prior)}
                old.save()
                with self.assertRaises(JourneyFailure): finish.Session(root, context, KEY, COMMIT, resume_drills=True)
                new = finish.Session(root, context, KEY, COMMIT, resume_drills=True, repair_rollback_routes=True)
                transition = new.state['controller_transition']
                self.assertEqual(new.read(transition['previous_drill_failure']), checkpoint)
                self.assertEqual(new.read(transition['previous_target_journeys']), checkpoint['target_journeys'])
                self.assertEqual(new.state['completed'], old.state['completed'])
                self.assertFalse(new.state['ms67_complete'])
                self.assertEqual(finish.candidates(new)[0], security)
                again = finish.Session(root, context, KEY, COMMIT, resume_drills=True, repair_rollback_routes=True)
                self.assertEqual(again.state['controller_transition'], transition)


if __name__ == '__main__': unittest.main()
