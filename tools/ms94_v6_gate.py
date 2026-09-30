"""Prospective B04 equipment hardening; the v6 business predicate is unchanged."""
import re
from pathlib import Path
from lightyear_calibration.contracts import read_json, require, seal, verify
from lightyear_calibration.journey_order import save, file_hash, RUNS
from lightyear_calibration.application_journey import read_trace
from lightyear_calibration.qualified_contract import trace_diagnostics
from tools.ms94_v5_gate import evaluate as base_evaluate, VERSION

EQUIPMENT_REVISION = 'ms94-b04-public-contract-hardening-v1'
LANES = ('oracle', 'postgresql')


def public_contract_checks(run):
    run = Path(run); root = run.resolve().parents[len(RUNS.parts)]
    declaration = read_json(root/'factory/idempiere/qualification-ms94-v3/public/operations.json')
    checks = {}
    for lane in LANES:
        folder = run/'cases/operations/1/execution'/lane
        p = folder/'execution.json'
        if not p.exists(): continue
        execution = read_json(p); verify(execution)
        if execution['exit_code'] != 0: continue
        findings = trace_diagnostics(folder/'journey.xml', declaration)
        if not findings:
            trace, _ = read_trace(folder/'journey.xml')
            for field in sorted(declaration['trace_fields']):
                if field.endswith('.id') and field in trace and not re.fullmatch(r'[1-9][0-9]*', trace[field]):
                    findings.append({'category':'trace-contract', 'code':'invalid-public-identifier', 'field':field})
        checks[lane] = findings
    return checks


def evaluate(run, **unused):
    run = Path(run); plan = read_json(run/'plan.json'); verify(plan)
    require(plan.get('equipment_revision') == EQUIPMENT_REVISION,
            'B04 hardening requires its own prospective plan')
    require(plan['judge_version'] == VERSION and plan['scenario'] == 'operations', 'Wrong B04 scope')
    # Candidate contract checks cannot turn corrupt equipment/input evidence into
    # a nonvoid failure. Missing evidence is retained as insufficient evidence.
    try:
        for name, digest in plan['inputs_sha256'].items():
            require('/' not in name and '\\' not in name and file_hash(run/'inputs'/name) == digest,
                    'Frozen native input changed')
        public = public_contract_checks(run)
    except FileNotFoundError as exc:
        value = {'status':'insufficient-evidence','passed':False,'checks':{},
                 'error':{'stage':'public-contract','type':type(exc).__name__}}
    except Exception as exc:
        value = {'status':'judge-error','passed':False,'checks':{},
                 'error':{'stage':'public-contract','type':type(exc).__name__}}
    else:
        # A genuine controller failure is always handled by its signed envelope.
        exits = {}
        for lane in LANES:
            execution_path = run/'cases/operations/1/execution'/lane/'execution.json'
            if execution_path.exists():
                execution = read_json(execution_path); verify(execution)
                exits[lane] = execution['exit_code']
        if any(public.values()) and exits == {lane:0 for lane in LANES} and not (run/'controller-outcome.json').exists():
            value = {'status':'contract-violation','passed':False,
                     'checks':{'public_contract':public},'error':None}
        else:
            value = dict(base_evaluate(run))
            # A complete, valid observer capture without the publicly required
            # witness is a failed observability contract. Missing/broken/gapped
            # capture still follows the unchanged equipment failure paths.
            combined = value.get('checks',{}).get('combined',{})
            observers = combined.get('database_observers',{})
            if value['status'] == 'insufficient-evidence' and set(observers) == set(LANES):
                violations = {}
                for lane, observation in observers.items():
                    items = []
                    if observation.get('rollback_observed') is False:
                        items.append({'category':'trace-contract','code':'missing-public-rollback-witness'})
                    if observation.get('lock_wait_observed') is False:
                        items.append({'category':'trace-contract','code':'missing-public-lock-witness'})
                    violations[lane] = items
                if any(violations.values()):
                    value.update(status='contract-violation', passed=False)
                    value['checks']['public_contract'] = violations
    value.pop('content_sha256', None)
    value.update(artifact_type='lightyear-structured-native-judgment', judge_version=VERSION,
                 equipment_revision=EQUIPMENT_REVISION, plan_sha256=plan['content_sha256'],
                 qualification_only=plan.get('qualification_only',False), autonomous_success=False,
                 platform_qualification=False, builder_visible=False)
    value = seal(value); save(run/'gate.json', value)
    return value
