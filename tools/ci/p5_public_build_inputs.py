"""Unsigned, CI-only three-role formatting for a separate public repair control.

This helper does not run gates, a controller, providers or admission. A supplied
baseline report is input data, not authenticated evidence of OCI execution.
The caller must separately retain and authenticate the real CI baseline.
"""
from copy import deepcopy
from hashlib import sha256
import os
from pathlib import Path

CASE = 'configured-build-control'
# Fixture identity is independent of the single reviewed admission case.
WORKER = 'tests/fixtures/p5_public/human-public-build-control/worker.py'
WORKER_SHA256 = 'db4d559f1badcf6a6473d6ade51fd463f91b814f67d1a7b3bc20f31076d3d47a'
ROLES = ('planner', 'failure_analyst', 'builder')
FAILED_STDOUT = 'public-build-control-failed\n'


def require(value, reason):
    if not value:
        raise ValueError(reason)


def compile_requests(root, order_document, baseline_report):
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'public-build-ci-only')
    from lightyear_factory.agents import ModelAgentSet
    from lightyear_factory.context import GraphContextAssembler
    from lightyear_factory.contracts import WorkOrder, canonical_hash
    from lightyear_factory.gates import builder_failure_view
    from lightyear_factory.orchestrator import FactoryOrchestrator
    from lightyear_factory.providers import _validate_schema
    from lightyear_execution.public_drill_outputs import validate_public_output_plan

    root = Path(root)
    path = root / WORKER
    require(root.is_absolute() and path.is_file() and all(
        not p.is_symlink() and not getattr(p, 'is_junction', lambda: False)()
        for p in (path, *path.parents)), 'public-build-regular-workspace')
    require(path.stat().st_size <= 65536, 'public-build-worker-size')
    raw = path.read_bytes()
    require(sha256(raw).hexdigest() == WORKER_SHA256, 'public-build-exact-worker')
    order = WorkOrder.from_dict(deepcopy(order_document))
    require(order.order_id == CASE and order.allowed_paths == (WORKER,)
            and order.graph_node_ids == () and order.baseline_first is True
            and order.max_attempts == 1 and order.max_model_calls == 3
            and order.allow_network is False
            and order.metadata == {'context_schema': '1.0', 'graph': 'packed'},
            'public-build-order-scope')
    require(len(order.gates) == 1 and order.gates[0].gate_id == 'public-arithmetic'
            and order.gates[0].command == ('python3', WORKER)
            and order.gates[0].expose_output_to_builder is False,
            'public-build-gate-scope')
    # Only this public synthetic failure can reach the native formatters.
    require(type(baseline_report) is dict and baseline_report.get('status') == 'failed'
            and type(baseline_report.get('gates')) is list
            and len(baseline_report['gates']) == 1, 'public-build-baseline-shape')
    row = baseline_report['gates'][0]
    require(type(row) is dict and row.get('id') == order.gates[0].gate_id
            and row.get('command') == list(order.gates[0].command)
            and row.get('status') == 'failed' and type(row.get('exit_code')) is int
            and row['exit_code'] == 1 and row.get('timed_out') is False
            and row.get('stdout') == FAILED_STDOUT and row.get('stderr') == ''
            and row.get('expose_output_to_builder') is False
            and row.get('output_sha256') == sha256(FAILED_STDOUT.encode() + b'\0').hexdigest(),
            'public-build-exact-baseline')
    public = builder_failure_view(baseline_report)
    context = GraphContextAssembler(None, None).assemble(order, root)
    plan = dict(summary='Repair the deliberately defective public arithmetic fixture.',
                tasks=[dict(id='repair-public-addition', objective=order.goal,
                            paths=[WORKER], graph_node_ids=[], evidence_capsule_ids=[])],
                risks=['Scripted public control only; no COPAU or production qualification.'])
    diagnosis = dict(summary='The public baseline gate failed.',
                     failure_codes=['public-arithmetic'],
                     builder_guidance='Inspect the approved public addition implementation.',
                     risk='low')
    repair = dict(summary='Remove the deliberate subtraction from public addition.',
                  edits=[dict(path=WORKER, find='return left + right - 1',
                              replace='return left + right',
                              rationale='Restore addition; keep the same acceptance check.')],
                  blocked_reason=None)
    responses = (plan, diagnosis, repair)

    class FormatOnly(ModelAgentSet):
        def __init__(self):
            super().__init__(None)
            self.requests = []

        def _call(self, current_order, role, instruction, payload, schema):
            index = len(self.requests)
            require(current_order is order and index < len(ROLES)
                    and role == ROLES[index], 'public-build-role-sequence')
            response = responses[index]
            _validate_schema(response, schema, 'public-build-response')
            self.requests.append(deepcopy(dict(instruction=instruction, payload=payload, schema=schema)))
            return deepcopy(response)

    formatter = FormatOnly()
    require(formatter.plan(order, context) == plan, 'public-build-plan-format')
    require(formatter.analyze_failure(order, public, 0) == diagnosis, 'public-build-analysis-format')
    envelope = FactoryOrchestrator._failure_envelope(public, diagnosis)
    require(formatter.build(order, plan, envelope, root, 1) == repair, 'public-build-repair-format')
    require(len(formatter.requests) == 3 and path.read_bytes() == raw, 'public-build-format-only')
    steps = [dict(sequence=i, role=role, invocation_sha256=canonical_hash(request),
                  schema_sha256=canonical_hash(request['schema']), response_content=deepcopy(response),
                  response_sha256=canonical_hash({'content': response}))
             for i, (role, request, response) in enumerate(zip(ROLES, formatter.requests, responses), 1)]
    script = dict(schema='factory-public-drill-outputs/1', case_id=CASE,
                  work_order_sha256=order.content_sha256, provider='p5-scripted',
                  model='p5-stub-2026-10-28', steps=steps)
    script['content_sha256'] = canonical_hash(script)
    validate_public_output_plan(script, order.content_sha256, CASE)
    return dict(status='unsigned-three-role-format-only', requests=formatter.requests,
                public_outputs=script, public_baseline=public,
                work_order_sha256=order.content_sha256, worker_sha256=WORKER_SHA256,
                baseline_origin_verified=False, controller_executed=False,
                provider_calls=0, execution_authorized=False, signature_created=False,
                nonce_consumed=False, qualifies_for_factory_receipt=False,
                missing=['authenticated-real-oci-baseline', 'reviewed-exact-work-order-and-policy',
                         'approved-executable-and-workflow', 'fresh-human-proof',
                         'explicit-execution-approval', 'admitted-controller-output-provenance'])
