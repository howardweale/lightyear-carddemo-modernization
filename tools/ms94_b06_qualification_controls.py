"""Declared native mutations and negative evidence projections, never model tools.

Original native captures and signed clock records are never rewritten. Evidence
controls operate on a separate, recorded projection of genuine native evidence.
"""
from copy import deepcopy
from pathlib import Path
import json
from lightyear_calibration.contracts import canonical, read_json, verify, seal
from lightyear_calibration.ms94_faults_v2 import FAULTS
from lightyear_control_tower.decisions import verify_envelope
from tools.ms94_b06_admission import check, sign_once, bound_file, LANES
from tools.ms94_b06_runtime_contract import clock_record, verify_runtime

BOUNDARIES = {
    'clock-missing-sample': 'clock-sample-count',
    'clock-extra-sample': 'clock-sample-count',
    'clock-reordered-samples': 'clock-sample-stages',
    'runtime-missing-container': 'runtime-clock-attestation-incomplete',
    'runtime-duplicate-container': 'runtime-clock-inventory-differs',
    'runtime-wrong-role-image': 'runtime-clock-manipulation-or-image',
}
DB_MODULE = 'src/lightyear_calibration/ms94_faults_v2.py'


def validate_plan(plan):
    kind, control = plan.get('slot_kind', 'candidate'), plan.get('control')
    check(kind in ('candidate', 'posting-origin', 'native-mutator', 'evidence-boundary'), 'unknown-slot-kind')
    if kind == 'native-mutator':
        check(plan['journey'] == 'J1' and control in (*FAULTS, 'duplicate-trace-key'), 'unknown-native-mutation')
        recipe = plan['fault_recipe']; verify(recipe)
        check(recipe['fault'] == control and recipe['unchanged_J1_mutator'] is True, 'mutation-recipe-binding')
        check(plan['implementation_sha256'].get(recipe['module']) == recipe['module_sha256'], 'mutation-code-binding')
        check(plan['fault'] == control, 'mutation-plan-fault-differs')
    elif kind == 'evidence-boundary':
        check(control in BOUNDARIES and plan['journey'] in ('J2', 'J3'), 'unknown-evidence-boundary')
        check(plan['model_calls'] == 0 and plan['qualification_only'] is True, 'boundary-not-qualification')


def native_mutation(runner, lane, execution, folder, signer):
    """Call the unchanged J1 SQL mutator only after a successful native process."""
    plan = runner.plan; validate_plan(plan)
    if plan.get('slot_kind') != 'native-mutator' or plan['control'] == 'duplicate-trace-key': return None
    check(execution['exit_code'] == 0, 'mutation-reference-did-not-complete')
    check(lane in LANES and plan['model_calls'] == 0 and plan['qualification_only'], 'mutation-not-qualification')
    where = Path(folder) / 'mutations' / (lane + '.json')
    check(not where.exists(), 'native-mutation-already-applied')
    bound_file(runner.root, DB_MODULE, plan['implementation_sha256'][DB_MODULE])
    from lightyear_calibration.journey_runtime import docker
    response = docker('exec', '-i', runner.runner, 'python', '-m', 'lightyear_calibration.ms94_faults_v2',
                      input=canonical({'lane': lane, 'fault': plan['control'], 'password': runner.password}), timeout=120)
    record = json.loads(response.stdout); verify(record)
    check(record['lane'] == lane and record['fault'] == plan['control'] and record['committed'] is True and
          record['affected_rows'] > 0 and record['qualification_only'] is True, 'native-mutation-not-observed')
    where.parent.mkdir(exist_ok=True)
    return sign_once(where, {k: v for k, v in record.items() if k != 'content_sha256'}, signer)


def projection(clock, control):
    """A deterministic mutation of a copy; its original native evidence survives."""
    check(control in BOUNDARIES, 'unknown-evidence-boundary')
    value = deepcopy(clock)
    samples = value['lanes']['oracle']['queries']
    if control == 'clock-missing-sample': samples.pop()
    elif control == 'clock-extra-sample': samples.append(deepcopy(samples[-1]))
    elif control == 'clock-reordered-samples': samples.reverse()
    elif control == 'runtime-missing-container': value['runtime'].pop()
    elif control == 'runtime-duplicate-container': value['runtime'][-1] = deepcopy(value['runtime'][0])
    elif control == 'runtime-wrong-role-image': value['runtime'][-1]['image'] = 'sha256:' + '0'*64
    return value


def rejection(plan, value, executions):
    for lane in LANES:
        clock_record(value['lanes'][lane]['queries'], executions[lane], plan['evidence_contract']['clock_stages'])
    verify_runtime(value['runtime'], plan['evidence_contract'])


def boundary_body(run, plan, gate, public_key):
    """Require a healthy original gate before crediting the negative projection."""
    validate_plan(plan)
    check(plan['slot_kind'] == 'evidence-boundary' and gate['passed'] is True and
          gate['complete_gate_replayed'] is True, 'boundary-original-native-gate-not-passed')
    original = read_json(Path(run) / 'b06-clock-evidence.json')
    check(verify_envelope(original, public_key) and original['plan_sha256'] == plan['content_sha256'],
          'boundary-original-clock-signature')
    executions = {l: read_json(Path(run) / 'cases/operations/1/execution' / l / 'execution.json') for l in LANES}
    for record in executions.values(): verify(record)
    rejection(plan, original, executions)  # genuine evidence must first pass
    invalid = projection(original, plan['control'])
    try:
        rejection(plan, invalid, executions)
    except ValueError as exc:
        reason = str(exc)
    else:
        check(False, 'boundary-mutant-not-rejected')
    check(reason == BOUNDARIES[plan['control']], 'boundary-unexpected-rejection')
    return {'artifact_type': 'ms94-b06-native-evidence-boundary/1', 'plan_sha256': plan['content_sha256'],
            'source_clock_sha256': original['content_sha256'], 'original_gate_sha256': gate['content_sha256'],
            'control': plan['control'], 'projected_evidence_sha256': seal({k:v for k,v in invalid.items()
                if k not in ('content_sha256', 'signature')})['content_sha256'],
            'closed_reason': reason, 'status': 'insufficient-evidence', 'equipment_suspect': True,
            'original_evidence_preserved': True, 'original_complete_gate_replayed': True,
            'mutated_projection_rejected': True, 'qualification_credit': False, 'model_calls': 0}


def replay_boundary(run, plan, gate, public_key):
    expected = boundary_body(run, plan, gate, public_key)
    record = read_json(Path(run) / 'evidence-boundary.json')
    check(verify_envelope(record, public_key) and all(record.get(k) == v for k, v in expected.items()),
          'boundary-record-does-not-replay')
    return record
