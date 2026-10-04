"""Offline J2/J3 gate from full native captures. No Docker, model calls or writes."""
from pathlib import Path

from lightyear_calibration.contracts import read_json, seal, verify
from lightyear_calibration.application_journey import read_trace
from lightyear_calibration.ms94_v3_errors import business_require, BusinessViolation
from lightyear_calibration import ms94_v3_procurement
from lightyear_calibration.native_catalog import read_capture
from lightyear_calibration.datatype_mappings import assess
from lightyear_control_tower.decisions import verify_envelope
from tools.ms94_b06_admission import check, verify_inputs, replay_entry, replay_clocks, native_pair_tables, LANES
from tools.ms94_b06_footprint import validate
from tools.ms94_b06_reconciliation import compare
from tools import ms94_b06_materials, ms94_b06_procurement


def material_bindings(trace):
    from tools.ms94_b06_footprint import MATERIALS
    return {stage + '.uuid': (table, table + '_uu', {table + '_id': int(trace[stage + '.id'])})
            for stage, table in MATERIALS.items()}


def evaluate(run, public_key):
    """Keep the same typed business rejection during independent offline replay."""
    completed = {}
    try:
        return verify_run(run, public_key, completed)
    except BusinessViolation as exc:
        check(completed.get('entry') is True, 'business-rejection-before-entry-replay')
        plan = read_json(Path(run) / 'plan.json')
        return seal({'artifact_type': 'ms94-b06-complete-native-gate/1',
                     'plan_sha256': plan['content_sha256'], 'journey': plan['journey'],
                     'passed': False, 'status': 'business-failure', 'closed_reason': str(exc),
                     'full_entry_replayed': True, 'complete_gate_replayed': True,
                     'native_qualification': False, 'independently_attested': False})


def verify_run(run, public_key, completed=None):
    run = Path(run)
    plan = read_json(run / 'plan.json')
    contract = verify_inputs(run, plan)
    auth = read_json(run / 'authorization.json')
    check(verify_envelope(auth, public_key) and auth['run_id'] == run.name and
          auth['plan']['plan_sha256'] == plan['content_sha256'] and
          auth['scope'] == 'zero-model-native-qualification', 'native-authorization-invalid')
    entry = replay_entry(run, public_key)
    if completed is not None:
        completed['entry'] = True
    clocks = replay_clocks(run, public_key)
    before, after, bindings = native_pair_tables(run)
    from tools.ms94_b06_expectations import verify_private_derivation
    verify_private_derivation(run, contract, before)
    folder = run / 'cases/operations/1'
    catalogs = {l: read_capture(folder / 'baseline' / l / 'catalog.json') for l in LANES}
    oracle = catalogs['oracle']['results']['identity']['rows']
    postgres = [r for r in catalogs['postgresql']['results']['settings']['rows'] if r['name'] == 'TimeZone']
    check(len(oracle) == len(postgres) == 1 and oracle[0]['time_zone'] == postgres[0]['setting'] == 'UTC',
          'native-capture-timezone-not-UTC')
    check(assess(catalogs)['columns'] == read_json(run / 'inputs/datatype-inventory.json')['columns'],
          'datatype-inventory-changed')
    register = read_json(run / 'inputs/comparison-register.json')
    check(verify_envelope(register['timestamp_decision'], public_key), 'comparison-decision-signature-invalid')
    lanes, executions, footprints = {}, {}, {}
    for lane in LANES:
        where = folder / 'execution' / lane
        execution = read_json(where / 'execution.json'); verify(execution)
        executions[lane] = execution
        check(execution['harness_sha256'] == plan['harness_sha256'] and
              execution['application_source_commit'] == plan['declaration']['application']['source_commit'],
              'execution-source-binding-invalid')
        check(execution['exit_code'] == 0, 'execution-failure-needs-diagnostic-adapter')
        trace, trace_hash = read_trace(where / 'journey.xml')
        business_require(trace.get('database') == lane and trace.get('status') == 'completed-and-committed'
                         and trace.get('newIssueCount') == '0', 'journey-completion-missing')
        footprints[lane] = validate(before[lane], after[lane], trace, contract, execution['runtime_facts'])
        if plan['journey'] == 'J2':
            # Complete inherited monetary, stock, allocation and accounting judge.
            lanes[lane] = ms94_v3_procurement.verify_lane(folder / 'after' / lane, where / 'journey.xml',
                                                          execution, (run / 'inputs/operations.java').read_bytes())
            from tools.ms94_v3_scope import validate as purchasing_scope, accounting_cache
            bounds = read_json(run / 'inputs/history-bound.json'); verify(bounds)
            footprints[lane]['purchasing'] = purchasing_scope(after[lane], before[lane], trace, bounds)
            footprints[lane]['cache'] = accounting_cache(after[lane], before[lane], trace)
            footprints[lane]['supplemental'] = ms94_b06_procurement.verify_rows(
                before[lane], after[lane], trace, contract['business_date'])
        else:
            result = ms94_b06_materials.verify_rows(before[lane], after[lane], trace, contract)
            lanes[lane] = {'trace': trace, 'trace_sha256': trace_hash, 'business': result}
    comparison = compare(run, before, after, executions, lanes,
                         ms94_v3_procurement.bindings if plan['journey'] == 'J2' else material_bindings)
    return seal({'artifact_type': 'ms94-b06-complete-native-gate/1', 'journey': plan['journey'],
                 'plan_sha256': plan['content_sha256'], 'entry_sha256': entry['content_sha256'],
                 'clock': clocks, 'capture_bindings': bindings, 'footprints': footprints,
                 'lanes': lanes, 'comparison': comparison, 'passed': comparison['passed'],
                 'full_entry_replayed': True, 'complete_gate_replayed': True,
                 'native_qualification': False, 'independently_attested': False})
