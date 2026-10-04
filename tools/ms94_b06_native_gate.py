"""Offline J2/J3 gate from full native captures. No Docker, model calls or writes."""
from pathlib import Path

from lightyear_calibration.contracts import read_json, seal, verify
from lightyear_calibration.journey_order import file_hash
from tools.ms94_b06_candidate_result import candidate_trace
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
    completed = {'finished': [], 'bindings': {}}
    try:
        return verify_run(run, public_key, completed)
    except BusinessViolation as exc:
        check(completed.get('entry') is True, 'business-rejection-before-entry-replay')
        plan = read_json(Path(run) / 'plan.json')
        return seal({'artifact_type': 'ms94-b06-complete-native-gate/1',
                     'plan_sha256': plan['content_sha256'], 'journey': plan['journey'],
                     'passed': False, 'status': 'business-failure', 'closed_reason': str(exc),
                     'full_entry_replayed': True, 'complete_gate_replayed': False,
                     'evidence_bindings': completed['bindings'],
                     'gate_progress': {'completed': completed['finished'],
                                       'failed': completed['current'],
                                       'not_executed': completed['stages'][len(completed['finished']) + 1:]},
                     'native_qualification': False, 'independently_attested': False})


def verify_run(run, public_key, completed=None):
    completed = completed if completed is not None else {'finished': [], 'bindings': {}}
    completed['stages'] = ['input-authorization', 'entry', 'clock', 'captures', 'private-derivation', 'catalog-register',
                           *[lane + ':' + part for lane in LANES for part in ('execution', 'trace', 'footprint', 'business')],
                           'comparison']
    def begin(name):
        completed['current'] = name
    def done():
        completed['finished'].append(completed['current'])
    run = Path(run)
    begin('input-authorization')
    plan = read_json(run / 'plan.json')
    contract = verify_inputs(run, plan)
    auth = read_json(run / 'authorization.json')
    check(verify_envelope(auth, public_key) and auth['run_id'] == run.name and
          auth['plan']['plan_sha256'] == plan['content_sha256'] and
          auth['scope'] == 'zero-model-native-qualification', 'native-authorization-invalid')
    completed['bindings'].update(plan_sha256=plan['content_sha256'], authorization_sha256=auth['content_sha256'])
    done(); begin('entry')
    entry = replay_entry(run, public_key)
    if completed is not None:
        completed['entry'] = True
    completed['bindings']['entry_sha256'] = entry['content_sha256']
    done(); begin('clock')
    clocks = replay_clocks(run, public_key)
    completed['bindings']['clock'] = clocks
    done(); begin('captures')
    before, after, bindings = native_pair_tables(run)
    completed['bindings']['capture_bindings'] = bindings
    done(); begin('private-derivation')
    from tools.ms94_b06_expectations import verify_private_derivation
    verify_private_derivation(run, contract, before)
    done(); begin('catalog-register')
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
    done()
    lanes, executions, footprints = {}, {}, {}
    completed['bindings']['executions'] = {}
    completed['bindings']['traces'] = {}
    for lane in LANES:
        begin(lane + ':execution')
        where = folder / 'execution' / lane
        execution = read_json(where / 'execution.json'); verify(execution)
        executions[lane] = execution
        check(execution['harness_sha256'] == plan['harness_sha256'] and
              execution['application_source_commit'] == plan['declaration']['application']['source_commit'],
              'execution-source-binding-invalid')
        check(execution['exit_code'] == 0, 'execution-failure-needs-diagnostic-adapter')
        completed['bindings']['executions'][lane] = execution['content_sha256']
        done(); begin(lane + ':trace')
        trace_path = where / 'journey.xml'
        completed['bindings']['traces'][lane] = file_hash(trace_path) if trace_path.is_file() else None
        trace, trace_hash = candidate_trace(trace_path, plan['journey'])
        business_require(trace.get('database') == lane and trace.get('status') == 'completed-and-committed'
                         and trace.get('newIssueCount') == '0', 'journey-completion-missing')
        done(); begin(lane + ':footprint')
        footprints[lane] = validate(before[lane], after[lane], trace, contract, execution['runtime_facts'])
        done(); begin(lane + ':business')
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
        done()
    begin('comparison')
    comparison = compare(run, before, after, executions, lanes,
                         ms94_v3_procurement.bindings if plan['journey'] == 'J2' else material_bindings)
    done()
    return seal({'evidence_bindings': completed['bindings'],
                 'gate_progress': {'completed': completed['finished'], 'failed': None, 'not_executed': []},
                 'artifact_type': 'ms94-b06-complete-native-gate/1', 'journey': plan['journey'],
                 'plan_sha256': plan['content_sha256'], 'entry_sha256': entry['content_sha256'],
                 'clock': clocks, 'capture_bindings': bindings, 'footprints': footprints,
                 'lanes': lanes, 'comparison': comparison, 'passed': comparison['passed'],
                 'full_entry_replayed': True, 'complete_gate_replayed': True,
                 'native_qualification': False, 'independently_attested': False})
