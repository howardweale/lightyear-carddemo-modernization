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


def now():
    return datetime.now(timezone.utc).isoformat()


class NativeRunner(CalendarRunner):
    def __init__(self, root, run, plan, emit):
        super().__init__(root, run, plan, emit)
        self.clock_samples = {l: [] for l in LANES}

    def trusted_identity(self, lane):
        # Bracket each real SQL clock query with host UTC and monotonic time.
        start, monotonic = now(), time.monotonic()
        result = super().trusted_identity(lane)
        self.clock_samples[lane].append({'host_before_utc': start, 'host_after_utc': now(),
                                         'monotonic': monotonic, 'value': result['clock']['value']})
        return result


def execute_pair(root, run, signer):
    root, run = Path(root).resolve(), Path(run).resolve()
    check(run.parent == (root / RUNS).resolve(), 'unexpected-native-run-location')
    plan = read_json(run / 'plan.json')
    verify_inputs(run, plan)
    check(plan['harness_sha256'] == plan['inputs_sha256']['operations.java'], 'candidate-input-binding')
    guard(plan['calendar'])
    for name, expected in plan['implementation_sha256'].items():
        bound_file(root, name, expected)
    auth = read_json(run / 'authorization.json')
    check(verify_envelope(auth, signer.public) and auth['run_id'] == run.name and
          auth['plan']['plan_sha256'] == plan['content_sha256'] and
          auth['scope'] == 'zero-model-native-qualification', 'native-authorization-invalid')
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
    runner = NativeRunner(root, run, plan, emit)
    def before_candidate(lane):
        entry = replay_entry(run, signer.public)
        runner.checkpoint('candidate-admitted:' + lane)
        sign_once(run / ('candidate-started-' + lane + '.json'), {
            'artifact_type': 'ms94-b06-candidate-start/1', 'lane': lane, 'real_utc': now(),
            'entry_sha256': entry['content_sha256'], 'plan_sha256': plan['content_sha256']}, signer)
    runner.before_candidate = before_candidate
    error, executions, cleaned, gate = None, {}, None, None
    try:
        folder = runner.prepare('operations', 1)
        full_entry(run, signer)
        for lane in LANES:
            runner.checkpoint('execute-lane:' + lane)
            executions[lane] = runner.worker('execute', {
                'lane': lane, 'output': runner.inside(folder / 'execution' / lane),
                'harness_sha256': plan['harness_sha256'], 'test': 'LightyearOperationsTest',
                'source_commit': plan['declaration']['application']['source_commit'],
                'timeout_seconds': plan['candidate_timeout_seconds']},
                timeout=plan['candidate_timeout_seconds'] + 30)
            # Early throws still have full entry and real after-state capture.
            runner.worker('capture', {'lane': lane, 'output': runner.inside(folder / 'after' / lane)}, timeout=1800)
        runner.record_guard('pair-complete')
        clock_lanes = {}
        for lane in LANES:
            a, b = runner.clock_samples[lane]
            clock_lanes[lane] = {'host_start_utc': a['host_before_utc'], 'host_end_utc': b['host_before_utc'],
                                 'monotonic_seconds': b['monotonic'] - a['monotonic'],
                                 'queries': [a, b], 'execution_sha256': executions[lane]['content_sha256']}
        sign_once(run / 'b06-clock-evidence.json', {'artifact_type': 'ms94-b06-real-clock-evidence/1',
                  'plan_sha256': plan['content_sha256'], 'lanes': clock_lanes,
                  'runtime': read_json(run / 'real-time-containers.json')}, signer)
    except Exception as exc:
        error = {'kind': classify_failure(exc), 'exception_type': type(exc).__name__}
    finally:
        try:
            cleaned = cleanup_owned(runner)
        except Exception as exc:
            cleaned = {'complete': False, 'inventory_known': False, 'exception_type': type(exc).__name__}
        cleanup = sign_once(run / 'cleanup.json', {'artifact_type': 'ms94-b06-native-cleanup/1',
                            'plan_sha256': plan['content_sha256'], 'run_id': run.name, **cleaned}, signer)
    if not cleaned['complete']:
        error = {'kind': 'equipment-failure', 'exception_type': 'CleanupIncomplete'}
    if error is None:
        if any(x['exit_code'] for x in executions.values()):
            # Diagnostic/provenance qualification is a separate admission. Never
            # turn missing origin evidence into a candidate-origin error report.
            error = {'kind': 'execution-failure', 'exception_type': 'CandidateProcessFailed'}
        else:
            try:
                gate = evaluate(run, signer.public)
                sign_once(run / 'gate.json', {k: v for k, v in gate.items() if k != 'content_sha256'}, signer)
            except Exception as exc:
                error = {'kind': classify_failure(exc), 'exception_type': type(exc).__name__}
    return sign_once(run / 'receipt.json', {
        'artifact_type': 'ms94-b06-native-receipt/1', 'plan_sha256': plan['content_sha256'],
        'authorization_sha256': auth['content_sha256'], 'cleanup_sha256': cleanup['content_sha256'],
        'journey': plan['journey'], 'model_calls': 0, 'elapsed_seconds': round(time.monotonic() - started, 3),
        'real_finished_utc': now(), 'status': error['kind'] if error else ('passed' if gate['passed'] else gate.get('status', 'contract-violation')),
        'error': error, 'execution_sha256': {l: x['content_sha256'] for l, x in executions.items()},
        'gate_sha256': read_json(run / 'gate.json')['content_sha256'] if (run / 'gate.json').exists() else None,
        'equipment_suspect': error is not None and error['kind'] != 'business-failure',
        'qualification_credit': False, 'independently_attested': False,
    }, signer)
