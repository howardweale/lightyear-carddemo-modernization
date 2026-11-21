"""Read-only human drill-plan verification; never grants execution admission.

This preparatory verifier has no CLI dispatch. Cross-job reservation, role
authorization and OCI binding must be implemented before an admission receipt
can be issued. No HMAC key, signing operation or supplied 'passed' receipt is
accepted here.
"""
from copy import deepcopy
from datetime import datetime, timezone
import re

from lightyear_factory.contracts import canonical_hash
from lightyear_factory.model_admission import FactoryModelAdmission
from .contracts import ExecutionContractError, ExecutionPolicy, safe_name


def _validate_drill_binding(value, order, policy):
    fields = {'schema', 'case_id', 'nonce_sha256', 'work_order_sha256',
              'execution_policy_sha256', 'role_actions', 'ci', 'stub_only',
              'external_model_calls', 'max_attempts'}
    if not isinstance(value, dict) or set(value) != fields:
        raise ExecutionContractError('tower-drill-binding-shape')
    if (value['schema'] != 'factory-human-drill-admission/1'
            or value['stub_only'] is not True
            or type(value['external_model_calls']) is not int or value['external_model_calls'] != 0
            or type(value['max_attempts']) is not int or value['max_attempts'] != 1
            or order.max_attempts != 1 or policy.allowed_secret_names):
        raise ExecutionContractError('tower-drill-scope')
    if not isinstance(value['case_id'], str) or safe_name(value['case_id'], 'drill case') != value['case_id']:
        raise ExecutionContractError('tower-drill-case-name')
    if (not isinstance(value['nonce_sha256'], str)
            or not re.fullmatch('[0-9a-f]{64}', value['nonce_sha256'])
            or value['work_order_sha256'] != order.content_sha256
            or value['execution_policy_sha256'] != policy.content_sha256):
        raise ExecutionContractError('tower-drill-order-policy-binding')
    expected_roles = {role: list(actions) for role, actions in policy.role_actions.items()}
    if value['role_actions'] != expected_roles:
        raise ExecutionContractError('tower-drill-role-binding')
    ci = value['ci']
    if (not isinstance(ci, dict)
            or set(ci) != {'repository', 'workflow_ref', 'job', 'run_attempt'}
            or ci['repository'] != 'howardweale/lightyear-carddemo-modernization'
            or type(ci['run_attempt']) is not int or ci['run_attempt'] != 1
            or not isinstance(ci['workflow_ref'], str)
            or not re.fullmatch(
                r'howardweale/lightyear-carddemo-modernization/\.github/workflows/[A-Za-z0-9_-]+\.yml@[0-9a-f]{40}',
                ci['workflow_ref'])):
        raise ExecutionContractError('tower-drill-ci-binding')
    if not isinstance(ci['job'], str) or safe_name(ci['job'], 'drill job') != ci['job']:
        raise ExecutionContractError('tower-drill-job-name')
    return deepcopy(value)


def verify_human_drill_plan(admission, order, policy, *, now=None):
    """Verify an existing Tower proof, then return an explicitly non-executing plan.

    Expected CI identity is signed input, not a claim that a current CI job has
    authenticated itself. No environment variable can upgrade this result.
    """
    if type(admission) is not FactoryModelAdmission or type(policy) is not ExecutionPolicy:
        raise ExecutionContractError('tower-drill-real-verifier-required')
    current = now or datetime.now(timezone.utc)
    verified = admission.verify_plan(order, now=current)
    plan = admission._committed_json(admission.paths[0])
    if canonical_hash(plan, {'content_sha256'}) != verified['plan_sha256']:
        raise ExecutionContractError('tower-drill-plan-changed')
    binding = _validate_drill_binding(plan.get('drill_admission'), order, policy)
    if binding['ci']['workflow_ref'].rsplit('@', 1)[1] != plan['executable_commit']:
        raise ExecutionContractError('tower-drill-workflow-executable-binding')
    roles = plan['roles']
    if any(value['provider'] != 'p5-scripted' or not value['model'].startswith('p5-stub-')
           for value in roles.values()):
        raise ExecutionContractError('tower-drill-stub-provider-binding')
    # A second real proof verification must return the same trust/decision binding.
    if admission.verify_plan(order, now=current) != verified:
        raise ExecutionContractError('tower-drill-trust-changed')
    result = dict(schema='factory-human-drill-plan-review/1',
                  status='verified-plan-only', execution_authorized=False,
                  admission_receipt_issued=False, nonce_consumed=False,
                  verified_model_admission=verified, drill_binding=binding,
                  unresolved=['cross-job-one-use-reservation', 'ci-execution-identity',
                              'role-action-authorization', 'oci-runtime-binding',
                              'output-authenticity-verification'])
    result['content_sha256'] = canonical_hash(result)
    return result
