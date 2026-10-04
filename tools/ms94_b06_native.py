"""Authorized, single-use J2/J3 native pair adapter; no model transport.

Call only with an independently frozen plan and an operator-signed qualification
authorization. This module does not create approvals or choose replacement slots.
"""
from datetime import datetime, timezone
from pathlib import Path
import time

from lightyear_calibration.contracts import read_json, seal
from lightyear_calibration.journey_order import RUNS
from lightyear_calibration.measured_native import cleanup_owned
from lightyear_control_tower.decisions import verify_envelope
from tools.ms94_calendar import guard
from tools.ms94_calendar_runner import CalendarRunner
from tools.ms94_b06_admission import (LANES, check, bound_file, verify_inputs,
                                    sign_once, full_entry, replay_entry, classify_failure)
from tools.ms94_b06_native_gate import evaluate
from tools.ms94_b06_runtime_contract import clock_record
from tools.ms94_b06_candidate_result import CandidateTimeout
from lightyear_calibration.journey_runtime import JourneyAbort


def group_window_guard(plan, moment=None, *, starting=False):
    if plan.get('execution_admission_version') != 3:
        return  # Historical fixture plans cannot be promoted by the v3 converter.
    from tools.ms94_b06_admission import utc
    current = utc(moment or now())
    spec = plan['docker_run_window']
    remaining = (utc(spec['deadline_utc']) - current).total_seconds()
    check(utc(spec['not_before_utc']) <= current and remaining > 0, 'native-outside-approved-group-window')
    if starting:
        check(remaining >= plan['declaration']['policy']['max_elapsed_seconds'], 'native-no-full-pair-window')


def now():
    return datetime.now(timezone.utc).isoformat()


def failure_record(exc):
    kind = classify_failure(exc)
    return {'kind': kind, 'exception_type': type(exc).__name__,
            'closed_reason': 'candidate-timeout' if isinstance(exc, CandidateTimeout) else
                             str(exc) if kind == 'insufficient-evidence' else None}


class NativeRunner(CalendarRunner):
    def __init__(self, root, run, plan, emit):
        super().__init__(root, run, plan, emit)
        self.clock_samples = {l: [] for l in LANES}

    def check_cancel(self):
        group_window_guard(self.plan)
        return super().check_cancel()

    def trusted_identity(self, lane):
        # Bracket each real SQL clock query with host UTC and monotonic time.
        start, monotonic = now(), time.monotonic()
        result = super().trusted_identity(lane)
        stages = self.plan['evidence_contract']['clock_stages']
        check(len(self.clock_samples[lane]) < len(stages), 'clock-sample-count')
        self.clock_samples[lane].append({'stage': stages[len(self.clock_samples[lane])], 'host_before_utc': start, 'host_after_utc': now(),
                                         'monotonic': monotonic, 'value': result['clock']['value']})
        return result

    def worker(self, command, payload, timeout):
        try:
            return super().worker(command, payload, timeout)
        except JourneyAbort as exc:
            # Only the inherited application watchdog code is candidate-shaped.
            # Cancellation, calendar and controller deadlines retain their type.
            if command == 'execute' and str(exc) == 'application-timeout':
                raise CandidateTimeout() from exc
            raise


def execute_pair(root, run, signer):
    root, run = Path(root).resolve(), Path(run).resolve()
    check(run.parent == (root / RUNS).resolve(), 'unexpected-native-run-location')
    plan = read_json(run / 'plan.json')
    verify_inputs(run, plan)
    check(plan['harness_sha256'] == plan['inputs_sha256']['operations.java'], 'candidate-input-binding')
    guard(plan['calendar'])
    group_window_guard(plan, starting=True)
    for name, expected in plan['implementation_sha256'].items():
        bound_file(root, name, expected)
    auth = read_json(run / 'authorization.json')
    check(verify_envelope(auth, signer.public) and auth['run_id'] == run.name and
          auth['plan']['plan_sha256'] == plan['content_sha256'] and
          auth['scope'] == 'zero-model-native-qualification', 'native-authorization-invalid')
    if plan.get('execution_admission_version') == 3:
        check(auth.get('docker_run_window') == plan['docker_run_window'], 'native-window-authorization-binding')
    check(not any((run / p).exists() for p in ('started.json', 'receipt.json', 'cases', 'resources.json')),
          'native-slot-already-attempted')
    sign_once(run / 'started.json', {'artifact_type': 'ms94-b06-native-start/1',
              'plan_sha256': plan['content_sha256'], 'authorization_sha256': auth['content_sha256'],
              'real_utc': now(), 'model_calls': 0}, signer)
    started = time.monotonic()
    def emit(kind, payload):
        # Private append-only host log. It cannot confer a verdict or admission.
        from lightyear_calibration.contracts import canonical
        with (run / 'native-events.jsonl').open('ab') as stream:
            stream.write(canonical({'real_utc': now(), 'kind': kind, 'payload': payload}) + b'\n')
    if 'posting_observer' in plan:
        from tools.ms94_b06_observed_runner import ObservedRunner
        runner = ObservedRunner(root, run, plan, emit)
        runner.signer = signer
    else:
        runner = NativeRunner(root, run, plan, emit)
    def before_candidate(lane):
        entry = replay_entry(run, signer.public)
        runner.checkpoint('candidate-admitted:' + lane)
        sign_once(run / ('candidate-started-' + lane + '.json'), {
            'artifact_type': 'ms94-b06-candidate-start/1', 'lane': lane, 'real_utc': now(),
            'entry_sha256': entry['content_sha256'], 'plan_sha256': plan['content_sha256']}, signer)
    runner.before_candidate = before_candidate
    error, executions, cleaned, gate, delivery = None, {}, None, None, None
    inherited_observers = []
    try:
        folder = runner.prepare('operations', 1)
        if plan['journey'] == 'J1':
            from lightyear_control_tower.status_export import atomic_new
            atomic_new(run / 'selected-attempts.json', {'operations': 1})
        full_entry(run, signer)
        for lane in LANES:
            runner.checkpoint('execute-lane:' + lane)
            original_observer = None
            try:
                if plan['journey'] == 'J1':
                    from lightyear_calibration.qualification_observer_runtime_v4 import Observer
                    original_observer = Observer(runner, lane)
                    inherited_observers.append(original_observer)
                    original_observer.start()
                    runner.assert_real_runtime(original_observer.container)
                executions[lane] = runner.worker('execute', {
                    'lane': lane, 'output': runner.inside(folder / 'execution' / lane),
                    'harness_sha256': plan['harness_sha256'], 'test': 'LightyearOperationsTest',
                    'source_commit': plan['declaration']['application']['source_commit'],
                    'timeout_seconds': plan['candidate_timeout_seconds']},
                    timeout=plan['candidate_timeout_seconds'] + 30)
            finally:
                if original_observer is not None and original_observer.process is not None:
                    original_observer.stop()
            # Early throws still have full entry and real after-state capture.
            runner.worker('capture', {'lane': lane, 'output': runner.inside(folder / 'after' / lane)}, timeout=1800)
        runner.record_guard('pair-complete')
        clock_lanes = {}
        for lane in LANES:
            clock_lanes[lane] = clock_record(runner.clock_samples[lane], executions[lane],
                                              plan['evidence_contract']['clock_stages'])
        sign_once(run / 'b06-clock-evidence.json', {'artifact_type': 'ms94-b06-real-clock-evidence/1',
                  'plan_sha256': plan['content_sha256'], 'lanes': clock_lanes,
                  'runtime': read_json(run / 'real-time-containers.json')}, signer)
    except Exception as exc:
        error = failure_record(exc)
    finally:
        try:
            cleaned = cleanup_owned(runner)
        except Exception as exc:
            cleaned = {'complete': False, 'inventory_known': False, 'exception_type': type(exc).__name__}
        cleanup = sign_once(run / 'cleanup.json', {'artifact_type': 'ms94-b06-native-cleanup/1',
                            'plan_sha256': plan['content_sha256'], 'run_id': run.name, **cleaned}, signer)
        for observer in inherited_observers:
            try:
                observer.publish_after_application_stopped(folder / 'observers' / observer.lane)
            except Exception as exc:
                emit('J1-observer-publication-failure', {'lane': observer.lane, 'exception_type': type(exc).__name__})
                error = error or failure_record(exc)
    if not cleaned['complete']:
        error = {'kind': 'equipment-failure', 'exception_type': 'CleanupIncomplete'}
    if error is None:
        if any(x['exit_code'] == 124 for x in executions.values()):
            error = {'kind': 'candidate-timeout', 'exception_type': 'CandidateTimeout', 'closed_reason': 'candidate-timeout'}
        elif any(x['exit_code'] for x in executions.values()):
            error = {'kind': 'execution-failure', 'exception_type': 'CandidateProcessFailed'}
            if 'runtime_delivery' in plan:
                try:
                    from tools.ms94_b06_runtime_delivery import record_zero_model_delivery, replay_delivery
                    delivery = record_zero_model_delivery(root, run, signer)
                    replay_delivery(root, run, signer.public)
                except Exception as exc:
                    error = failure_record(exc)
                    delivery = None
        else:
            try:
                if plan['journey'] == 'J1':
                    from tools.ms94_b06_j1_bridge import evaluate as j1_evaluate
                    gate = j1_evaluate(run, signer.public)
                    sign_once(run / 'b06-j1-gate-attestation.json', {
                        'artifact_type': 'ms94-b06-J1-unchanged-gate-attestation/1',
                        'plan_sha256': plan['content_sha256'], 'gate_sha256': gate['content_sha256']}, signer)
                else:
                    gate = evaluate(run, signer.public)
                    sign_once(run / 'gate.json', {k: v for k, v in gate.items() if k != 'content_sha256'}, signer)
            except Exception as exc:
                error = failure_record(exc)
    return sign_once(run / 'receipt.json', {
        'artifact_type': 'ms94-b06-native-receipt/1', 'plan_sha256': plan['content_sha256'],
        'authorization_sha256': auth['content_sha256'], 'cleanup_sha256': cleanup['content_sha256'],
        'journey': plan['journey'], 'model_calls': 0, 'elapsed_seconds': round(time.monotonic() - started, 3),
        'real_finished_utc': now(), 'status': error['kind'] if error else ('passed' if gate['passed'] else gate.get('status', 'contract-violation')),
        'error': error, 'execution_sha256': {l: x['content_sha256'] for l, x in executions.items()},
        'gate_sha256': read_json(run / 'gate.json')['content_sha256'] if (run / 'gate.json').exists() else None,
        'runtime_delivery_sha256': delivery['content_sha256'] if delivery else None,
        'equipment_suspect': (delivery['equipment_suspect'] if delivery else
            error is not None and error['kind'] not in ('business-failure', 'candidate-timeout')),
        'qualification_credit': False, 'independently_attested': False,
    }, signer)
