"""Independent offline replay of one B06 qualification archive working copy.

Call on an extracted copy: the inherited J1 judge writes its gate there. Never
call against the original run as a shortcut, and never invent missing stages.
"""
from pathlib import Path
from lightyear_calibration.contracts import canonical, read_json, verify
from lightyear_control_tower.decisions import verify_envelope
from tools.ms94_b06_admission import check, bound_file, replay_entry, replay_clocks, native_pair_tables, LANES


def signed(path, key):
    record = read_json(path)
    check(verify_envelope(record, key), 'qualification-signature-invalid')
    return record


def incomplete_equipment(run, plan, receipt, public_key):
    """Authenticate preserved prefixes, never invent absent execution stages.

    This is a failed-run audit, not observer, clock, diagnostic or gate replay.
    Complete-run admission still requires every original replay predicate.
    """
    import hashlib, json
    from tools.ms94_b06_forwarding_stub import receipt_records
    from tools.ms94_b06_observer_v2 import commitments
    check(receipt['status'] == 'equipment-failure' and receipt['equipment_suspect'] is True and
          receipt.get('error', {}).get('kind') == 'equipment-failure', 'partial-audit-not-equipment')
    check(receipt.get('runtime_delivery_sha256') is None and receipt.get('gate_sha256') is None and
          not any((run/n).exists() for n in ('zero-model-builder-inbox.json','runtime-diagnostic.json','gate.json')),
          'partial-equipment-unexpected-verdict-or-feedback')
    records = []
    for lane in LANES:
        folder = run/'posting-observer'/lane
        failure_path, census_path = folder/'failure.json', folder/'frame-census.json'
        if not failure_path.exists() and not census_path.exists():
            check(not folder.exists() or not any(folder.iterdir()), 'partial-collector-unsealed')
            continue
        census = signed(census_path, public_key)
        check(census['plan_sha256'] == plan['content_sha256'] and census['lane'] == lane and
              census['model_calls'] == 0 and census['native_qualification'] is False,
              'partial-census-binding')
        raw = (folder/'events.jsonl').read_bytes()
        check(hashlib.sha256(raw).hexdigest() == census['event_file_sha256'], 'partial-event-bytes')
        events = [json.loads(line) for line in raw.splitlines()]
        check(len(events) == census['event_count'], 'partial-event-count')
        previous = None
        for index, item in enumerate(events, 1):
            verify(item)
            check(item['previous_sha256'] == previous and item['event']['sequence'] == index,
                  'partial-event-chain')
            previous = item['content_sha256']
        check(previous == census['last_event_sha256'] and census['frame_records'] == receipt_records(events),
              'partial-frame-commitments')
        if plan.get('posting_observer', {}).get('observer_binding_v2') is not None:
            check(census['v2_records'] == commitments(events), 'partial-v2-commitments')
        failure = None
        if failure_path.exists():
            failure = signed(failure_path, public_key)
            check(failure['plan_sha256'] == plan['content_sha256'] and failure['lane'] == lane and
                  failure['complete'] is False and census['complete'] is False and
                  failure['event_count'] == len(events) and failure['last_event_sha256'] == previous,
                  'partial-failure-binding')
        else:
            check(census['complete'] is True, 'partial-missing-failure-record')
        records.append({'lane':lane,'census_sha256':census['content_sha256'],
                        'failure_sha256':failure['content_sha256'] if failure else None,
                        'event_count':len(events),'prefix_authenticated':True})
    return {'partial_evidence':True, 'equipment_failure_audited':True,
            'collector_prefixes':records, 'missing_artifacts':[
                name for name in ('b06-clock-evidence.json', 'gate.json',
                    *('cases/operations/1/execution/'+lane+'/execution.json' for lane in LANES))
                if not (run/name).exists()],
            'audit_scope':'authenticated preserved evidence only; no completed-stage or provenance claim'}


def replay_pair(root, run, public_key):
    root, run = Path(root), Path(run)
    plan = read_json(run / 'plan.json'); verify(plan)
    from tools.ms94_b06_engineering_boundary import refuse_engineering
    refuse_engineering(plan, run)
    for name, sha in plan['implementation_sha256'].items(): bound_file(root, name, sha)
    for name, sha in plan['inputs_sha256'].items(): bound_file(run / 'inputs', name, sha)
    receipt = signed(run / 'receipt.json', public_key)
    cleanup = signed(run / 'cleanup.json', public_key)
    auth = signed(run / 'authorization.json', public_key)
    start = signed(run / 'started.json', public_key)
    check(receipt['plan_sha256'] == cleanup['plan_sha256'] == start['plan_sha256'] == plan['content_sha256'] and
          receipt['authorization_sha256'] == start['authorization_sha256'] == auth['content_sha256'] and
          auth['plan']['plan_sha256'] == plan['content_sha256'] and auth['run_id'] == run.name and
          auth['scope'] == 'zero-model-native-qualification' and
          auth['docker_run_window'] == plan['docker_run_window'], 'qualification-receipt-binding')
    check(cleanup['complete'] is True and receipt['cleanup_sha256'] == cleanup['content_sha256'] and
          receipt['model_calls'] == 0, 'qualification-cleanup-or-model-use')
    entry = replay_entry(run, public_key)
    result = {'receipt_sha256': receipt['content_sha256'], 'entry_sha256': entry['content_sha256'],
              'full_entry_replayed': True, 'complete_gate_replayed': False, 'clock_replayed': False,
              'diagnostic_replayed': False, 'delivery_replayed': False, 'observer_replayed': False,
              'status': receipt['status'], 'equipment_suspect': receipt['equipment_suspect'],
              'diagnostics': [], 'gate': None, 'partial_evidence': False}
    if plan['control'] == 'genuine-equipment-fault':
        from tools.ms94_b06_fault_hook import replay
        result.update(replay(run, public_key))
        check(receipt['equipment_suspect'] is True and receipt['runtime_delivery_sha256'] is None,
              'database-fault-delivered-feedback')
        check(not (run / 'zero-model-builder-inbox.json').exists(), 'database-fault-unexpected-inbox')
        return result
    if receipt['status'] == 'equipment-failure':
        result.update(incomplete_equipment(run, plan, receipt, public_key))
        return result
    result.update(replay_clocks(run, public_key))
    native_pair_tables(run)  # every captured table, including early failures
    executions = {}
    for lane in LANES:
        ex = read_json(run / 'cases/operations/1/execution' / lane / 'execution.json'); verify(ex)
        check(receipt['execution_sha256'].get(lane) == ex['content_sha256'] and
              ex['harness_sha256'] == plan['harness_sha256'] and
              ex['application_source_commit'] == plan['declaration']['application']['source_commit'],
              'qualification-execution-binding')
        if 'built_runtime' in plan:
            from tools.ms94_b06_built_runtime import replay as replay_built
            replay_built(root, plan, ex, run / 'cases/operations/1/execution' / lane)
        executions[lane] = ex
    if receipt['status'] == 'candidate-timeout':
        check(any(ex['exit_code'] == 124 for ex in executions.values()) and
              not receipt['equipment_suspect'] and not (run / 'zero-model-builder-inbox.json').exists(),
              'qualification-timeout-not-observed')
        result['partial_evidence'] = True
        return result
    from tools.ms94_b06_posting_replay import replay
    for lane in LANES: replay(root, run, lane, public_key)
    result['observer_replayed'] = True
    if any(ex['exit_code'] != 0 for ex in executions.values()):
        from tools.ms94_b06_runtime_delivery import replay_delivery
        result.update(replay_delivery(root, run, public_key))
        projection = signed(run / 'runtime-diagnostic.json', public_key)
        result['diagnostics'] = projection['diagnostics']
        check(receipt['runtime_delivery_sha256'] == result['delivery_sha256'] and
              receipt['equipment_suspect'] == result['equipment_suspect'] and
              receipt['status'] == 'execution-failure', 'qualification-diagnostic-receipt-binding')
        result['partial_evidence'] = True
    else:
        old = read_json(run / 'gate.json')
        if plan['journey'] == 'J1':
            from tools.ms94_b06_j1_bridge import evaluate
            attestation = signed(run / 'b06-j1-gate-attestation.json', public_key)
            check(attestation['gate_sha256'] == old['content_sha256'], 'qualification-j1-attestation')
            expected = evaluate(run, public_key)
            check(canonical(old) == canonical(expected), 'qualification-J1-gate-replay-differs')
        else:
            from tools.ms94_b06_native_gate import evaluate
            check(verify_envelope(old, public_key), 'qualification-gate-signature')
            expected = evaluate(run, public_key)
            check(all(old.get(k) == v for k,v in expected.items() if k != 'content_sha256'),
                  'qualification-gate-replay-differs')
        check(receipt['gate_sha256'] == old['content_sha256'], 'qualification-gate-receipt-binding')
        result['gate'] = expected
        result['complete_gate_replayed'] = expected.get('complete_gate_replayed', expected['passed'])
        from tools.ms94_b06_runtime_delivery import replay_delivery
        delivered = replay_delivery(root, run, public_key)
        check(delivered['delivered'] is False and delivered['equipment_suspect'] is False and
              receipt['runtime_delivery_sha256'] == delivered['delivery_sha256'],
              'qualification-success-delivery-binding')
        result.update({k:v for k,v in delivered.items() if k != 'equipment_suspect'})
        if plan.get('slot_kind') == 'evidence-boundary':
            from tools.ms94_b06_qualification_controls import replay_boundary
            boundary = replay_boundary(run, plan, expected, public_key)
            check(receipt['evidence_boundary_sha256'] == boundary['content_sha256'] and
                  receipt['status'] == 'insufficient-evidence' and receipt['equipment_suspect'],
                  'qualification-boundary-receipt-binding')
            result['evidence_boundary_replayed'] = True
        else:
            check(receipt['status'] == ('passed' if expected['passed'] else expected.get('status','contract-violation')),
                  'qualification-verdict-differs')
    if plan.get('slot_kind') == 'posting-origin':
        projection = signed(run / 'runtime-diagnostic.json', public_key)
        check(result['diagnostic_replayed'] and result['delivery_replayed'] and
              projection['posting_control_replayed'] is True, 'qualification-posting-delivery-missing')
        result.update(posting_control_replayed=True, posting_causes=projection['posting_causes'])
    if plan.get('slot_kind') == 'native-mutator':
        from tools.ms94_v3_negative_checks import negative_checks
        from lightyear_calibration.ms94_faults_v2 import FAULTS
        if plan['control'] in FAULTS:
            for lane in LANES:
                mutation = signed(run / 'cases/operations/1/mutations' / (lane+'.json'), public_key)
                check(mutation['lane'] == lane and mutation['fault'] == plan['control'] and
                      mutation['committed'] is True and mutation['affected_rows'] > 0, 'qualification-mutation-binding')
        gate = result['gate'] or {'status': receipt['status']}
        checks = negative_checks(run, plan['control'], gate)
        check(set(checks) == set(LANES) and all(v['passed'] for v in checks.values()), 'qualification-mutant-not-killed')
        result['native_mutation_replayed'] = True
    return result
