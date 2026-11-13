"""CI-only clean-control execution; genuine public proof, no signing or mocks.

A successful component result never changes strict P5 qualification. The native
CLI deliberately returns 1 while full production receipt integration is open.
"""
import json
import os
from pathlib import Path
import subprocess
import sys


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_positive_records(dispatch, provenance, receipt, admission):
    """Validate retained relationships only; never grant execution authority."""
    from lightyear_factory.contracts import canonical_hash
    for value in (dispatch, provenance, receipt, admission):
        require(type(value) is dict and value.get('content_sha256') ==
                canonical_hash(value, {'content_sha256'}), 'positive-record-digest')
    require(dispatch.get('schema') == 'factory-human-drill-dispatch/1'
            and provenance.get('schema') == 'factory-human-drill-controller-provenance/1'
            and admission.get('schema') == 'factory-human-drill-context-admission/1',
            'positive-record-schema')
    require(dispatch.get('controller_status') == receipt.get('status') == 'passed'
            and dispatch.get('controller_raised_refusal') is False,
            'positive-controller-did-not-pass')
    require(dispatch.get('run_id') == receipt.get('run_id')
            and dispatch.get('receipt_sha256') == provenance.get('receipt_sha256') == receipt['content_sha256']
            and dispatch.get('provenance_sha256') == provenance['content_sha256']
            and receipt.get('work_order_sha256') == admission.get('work_order_sha256'),
            'positive-cross-record-binding')
    require(provenance.get('status') == 'complete-public-trace'
            and provenance.get('controller_origin_verified') is True
            and provenance.get('output_plan_complete') is True,
            'positive-incomplete-trace')
    for field, expected in (('completed_public_calls', 1), ('unfinished_public_calls', 0), ('accounted_calls', 1)):
        require(type(provenance.get(field)) is int and provenance[field] == expected,
                'positive-call-count')
    require(type(receipt.get('attempts')) is int and receipt['attempts'] == 0
            and receipt.get('changed_paths') == []
            and receipt.get('initial_snapshot_sha256') == receipt.get('final_snapshot_sha256'),
            'positive-clean-baseline-only')
    gates = receipt.get('verification', {}).get('gates')
    require(receipt.get('verification', {}).get('status') == 'passed'
            and type(gates) is list and bool(gates)
            and all(g.get('status') == 'passed' and type(g.get('output_sha256')) is str
                    and len(g['output_sha256']) == 64 for g in gates), 'positive-gates-not-passed')
    require(admission.get('stub_only') is True and admission.get('status') == 'passed'
            and admission.get('credentials_issued') is False and admission.get('secrets_leased') is False,
            'positive-admission-scope')
    for value in (dispatch, provenance):
        require(type(value.get('external_model_calls')) is int and value['external_model_calls'] == 0
                and type(value.get('signatures_created')) is int and value['signatures_created'] == 0,
                'positive-external-side-effects')
        require(value.get('production_qualified') is False
                and value.get('qualifies_for_factory_receipt') is False
                and value.get('gaps') == ['full-production-build-receipt-route-not-integrated'],
                'positive-must-retain-qualification-gap')
    require(receipt.get('execution_security', {}).get('production_ready') is False
            and receipt['execution_security'].get('admission_receipt_sha256') == admission['content_sha256']
            and bool(receipt['execution_security'].get('gate_execution_sha256')),
            'positive-native-gate-evidence')
    return dict(schema='factory-human-drill-positive-record-check/1',
                retained_relationships_verified=True, execution_authorized=False,
                production_qualified=False, qualifies_for_factory_receipt=False)


def main(argv=None):
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'positive-ci-only')
    from lightyear_factory.cli import build_parser
    from lightyear_factory.contracts import canonical_hash, WorkOrder
    from lightyear_factory.model_admission import FactoryModelAdmission, _bounded_regular_bytes
    from lightyear_factory.ledger import RunLedger
    from lightyear_execution.contracts import ExecutionPolicy
    from lightyear_execution.tower_drill_admission import verify_human_drill_plan
    from lightyear_execution.public_drill_outputs import review_public_drill_outputs
    from lightyear_execution.public_drill_runtime import verify_receipt_tail
    from lightyear_execution.human_drill_dispatch import load_public_isolation, validate_public_domain
    arguments=list(sys.argv[1:] if argv is None else argv)
    parsed=build_parser().parse_args(['human-drill-execute', *arguments])
    root=parsed.source_root.resolve(strict=True)
    require(parsed.runs_root.is_absolute() and not parsed.runs_root.exists(), 'positive-new-evidence-root')
    # Independently use the real public-proof verifier; no injected API or test patches.
    trust=FactoryModelAdmission.from_external_trust(root, parsed.factory_plan,
        parsed.factory_approval, parsed.factory_contract, parsed.factory_trust)
    order=WorkOrder.load(parsed.work_order); policy=ExecutionPolicy.load(parsed.execution_policy)
    review=verify_human_drill_plan(trust, order, policy)
    plan=trust._committed_json(trust.paths[0])
    inputs={key:root/row['path'] for key,row in plan['bound_inputs'].items()}
    runtime=trust.verify_runtime(order, source_root=root, input_paths=inputs, policy=policy)
    manifest=runtime['workspace_read_manifest']
    validate_public_domain(order, manifest, parsed.public_output_plan, parsed.public_isolation_plan)
    review_public_drill_outputs(trust, order, policy, parsed.public_output_plan)
    load_public_isolation(trust, order, policy, manifest, parsed.public_isolation_plan)
    script=trust._committed_json(parsed.public_output_plan)
    require(order.baseline_first is True and len(script['steps']) == 1
            and script['steps'][0]['role'] == 'planner', 'positive-one-planner-baseline')
    # Exactly one native CLI invocation. A timeout or ambiguous failure consumes
    # the attempted case; no retry, resume, tag deletion or alternate route.
    completed=subprocess.run([sys.executable, '-B', '-m', 'lightyear_factory',
        'human-drill-execute', *arguments], cwd=root, capture_output=True,
        timeout=order.max_elapsed_seconds+120, check=False)
    require(completed.returncode == 1, 'positive-native-cli-qualification-exit')
    def read(path):
        return json.loads(_bounded_regular_bytes(path, 1024*1024, 'positive-evidence-file'))
    evidence=parsed.runs_root
    dispatch=read(evidence/'dispatch-summary.json')
    provenance=read(evidence/'controller-output-provenance.json')
    admission=read(evidence/'human-admission.json')
    expected_id='drill-'+review['drill_binding']['nonce_sha256'][:32]
    require(dispatch.get('run_id') == expected_id, 'positive-exact-run-id')
    run=evidence/expected_id; receipt=read(run/'receipt.json'); summary=read(run/'summary.json')
    require(json.loads(completed.stdout) == dispatch, 'positive-cli-output-binding')
    check=validate_positive_records(dispatch, provenance, receipt, admission)
    events=RunLedger(run/'events.jsonl').events
    verify_receipt_tail(receipt, summary, events)
    require(summary.get('receipt_sha256') == receipt['content_sha256'], 'positive-summary-binding')
    require(verify_human_drill_plan(trust, order, policy) == review, 'positive-proof-or-trust-changed')
    require(all(admission.get(k) == review['verified_model_admission'][k] for k in
                ('plan_sha256','decision_sha256','trusted_journal_head')), 'positive-human-proof-binding')
    require(admission.get('nonce_sha256') == review['drill_binding']['nonce_sha256'], 'positive-nonce-binding')
    result=dict(schema='factory-human-drill-positive-ci/1', status='passed-component-execution',
        native_cli_exit=completed.returncode, run_id=expected_id,
        receipt_sha256=receipt['content_sha256'], provenance_sha256=provenance['content_sha256'],
        admission_sha256=admission['content_sha256'], record_check=check,
        trust_boundary='reviewed-github-workflow-and-runner', external_model_calls=0,
        signatures_created=0, execution_authorized=False, production_qualified=False,
        qualifies_for_factory_receipt=False, gaps=['full-production-build-receipt-route-not-integrated'])
    result['content_sha256']=canonical_hash(result)
    with (evidence/'positive-ci.json').open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(result, sort_keys=True, separators=(',',':'))+'\n')
        stream.flush(); os.fsync(stream.fileno())
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
