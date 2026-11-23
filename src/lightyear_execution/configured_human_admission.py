"""Inactive configured human proof boundary, not execution admission.

This separate proposal does not widen public-drill verification. No production
context, broker, CLI or reservation calls it. It checks one configured control
case against a genuine Factory proof, returning non-authorizing scope evidence.
The configured values in the existing binding fields require exact review with
the full worker/input/context/controller packet before publication.
"""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import re

from lightyear_factory.contracts import WorkOrder, canonical_hash
from lightyear_factory.model_admission import FactoryModelAdmission, _bounded_regular_bytes
from .contracts import ExecutionContractError, ExecutionPolicy


def _require(condition, reason):
    if not condition:
        raise ExecutionContractError(reason)


def _validate_configured_binding(value, order, policy, executable):
    """Pure structural validation; synthetic inputs here never grant authority."""
    fields = {'schema', 'case_id', 'nonce_sha256', 'work_order_sha256',
              'execution_policy_sha256', 'role_actions', 'ci', 'stub_only',
              'external_model_calls', 'max_attempts'}
    _require(type(value) is dict and set(value) == fields,
             'configured-human-binding-shape')
    _require(value['schema'] == 'factory-human-drill-admission/1'
             and value['case_id'] == order.order_id == 'configured-build-control'
             and order.baseline_first and order.max_attempts == 1
             and order.max_model_calls == 3 and 0 < order.max_model_cost_usd <= 10
             and value['stub_only'] is False
             and type(value['external_model_calls']) is int
             and value['external_model_calls'] == order.max_model_calls
             and type(value['max_attempts']) is int and value['max_attempts'] == 1,
             'configured-human-case-and-caps')
    _require(type(value['nonce_sha256']) is str
             and re.fullmatch('[0-9a-f]{64}', value['nonce_sha256'])
             and value['work_order_sha256'] == order.content_sha256
             and value['execution_policy_sha256'] == policy.content_sha256,
             'configured-human-order-policy-binding')
    _require(value['role_actions'] == {
                 role: list(actions) for role, actions in policy.role_actions.items()},
             'configured-human-role-binding')
    ci = value['ci']
    prefix = 'howardweale/lightyear-carddemo-modernization'
    _require(type(executable) is str and re.fullmatch('[0-9a-f]{40}', executable)
             and type(ci) is dict
             and set(ci) == {'repository', 'workflow_ref', 'job', 'run_attempt'}
             and ci['repository'] == prefix
             and type(ci['run_attempt']) is int and ci['run_attempt'] == 1
             and type(ci['workflow_ref']) is str
             and re.fullmatch(re.escape(prefix) +
                 r'/\.github/workflows/[A-Za-z0-9_-]+\.yml@' + executable,
                 ci['workflow_ref'])
             and type(ci['job']) is str
             and re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', ci['job']),
             'configured-human-ci-binding')
    return deepcopy(value)


def verify_configured_human_plan(admission, order, policy):
    """Recheck real human proof and exact committed policy; never consume nonce.

    Live CI identity, atomic reservation, model-byte/Flex binding, runtime
    isolation, credential leasing and original controller output are separate
    required boundaries. A caller-supplied passed dictionary is not accepted.
    """
    _require(type(admission) is FactoryModelAdmission and type(order) is WorkOrder
             and type(policy) is ExecutionPolicy, 'configured-human-real-verifier')
    # Reparse even an exact dataclass instance: construction is not validation.
    parsed = ExecutionPolicy.from_configured_human_dict(policy.to_dict())
    _require(parsed.to_dict() == policy.to_dict()
             and type(admission.public_key) is bytes
             and sha256(admission.public_key).hexdigest() == policy.trusted_key_ids[0],
             'configured-human-current-key-binding')
    current = datetime.now(timezone.utc)
    _require(current.tzinfo is not None, 'configured-human-timezone-required')
    verified = admission.verify_plan(order, now=current)
    plan = admission._committed_json(admission.paths[0])
    _require(canonical_hash(plan, {'content_sha256'}) == verified['plan_sha256'],
             'configured-human-plan-changed')
    binding = _validate_configured_binding(plan.get('drill_admission'), order,
                                          policy, plan['executable_commit'])
    _require(set(plan['roles']) == {'planner', 'analyst', 'builder'}
             and all(row['provider'] == 'openai-responses' for row in plan['roles'].values()),
             'configured-human-provider-binding')
    bound = plan['bound_inputs']['execution_policy']
    document = admission._committed_json(bound['path'])
    raw = _bounded_regular_bytes(admission.root / bound['path'], 8*1024*1024,
                                 'configured-human-policy-bytes')
    _require(sha256(raw).hexdigest() == bound['sha256']
             and ExecutionPolicy.from_configured_human_dict(document).to_dict() == policy.to_dict(),
             'configured-human-committed-policy-binding')
    _require(admission.verify_plan(order, now=datetime.now(timezone.utc)) == verified
             and admission._committed_json(bound['path']) == document
             and _bounded_regular_bytes(admission.root / bound['path'], 8*1024*1024,
                 'configured-human-policy-bytes') == raw,
             'configured-human-trust-or-policy-changed')
    # Input hashing can take time: the final operation rechecks current trust
    # and the actual clock. A caller cannot freeze a previously valid window.
    _require(admission.verify_plan(order, now=datetime.now(timezone.utc)) == verified,
             'configured-human-final-window-or-trust-changed')
    result = dict(schema='factory-human-drill-plan-review/1',
        status='verified-plan-only', execution_authorized=False,
        admission_receipt_issued=False, nonce_consumed=False,
        verified_model_admission=verified, drill_binding=binding,
        unresolved=['live-ci-identity', 'atomic-cross-job-reservation',
                    'per-role-authorization', 'committed-model-flex-binding',
                    'scoped-credential-broker', 'runtime-isolation',
                    'original-controller-outcome-and-receipt',
                    'physical-count-generation-evidence'])
    result['content_sha256'] = canonical_hash(result)
    return result
