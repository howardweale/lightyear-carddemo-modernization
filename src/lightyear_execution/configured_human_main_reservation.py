"""Uninvoked main-only reservation proposal; not a context or execution grant.

Atomic protocol is AST-identical to the original PR-only algorithm except its
function name; _ci_identity resolves to the separate strict main identity here.
No main dispatch opts in. Calling the public entry would consume an admission
nonce and requires separate exact execution approval; do not invoke now.
"""
from copy import deepcopy
import json,re
from lightyear_factory.contracts import canonical_hash
from .contracts import ExecutionContractError
from .tower_drill_reservation import _GitHubAPI,_PREFIX
from .configured_human_main_identity import _read_main_ci_identity as _ci_identity


def _consume_verified_main_plan(review, api, environment, reverify):
    """Internal algorithm boundary for CI-only synthetic API tests.

    This function deliberately returns non-authorizing evidence even when all
    inputs are supplied by a test. Production callers must use the public
    verifier entry below; no caller-supplied dict grants execution authority.
    """
    if (review.get('status') != 'verified-plan-only'
            or review.get('execution_authorized') is not False
            or review.get('nonce_consumed') is not False):
        raise ExecutionContractError('drill-reservation-plan-state')
    binding = review['drill_binding']
    model = review['verified_model_admission']
    head = model['executable_commit']
    identity = _ci_identity(binding, head, api, environment)
    if reverify() != review:
        raise ExecutionContractError('drill-reservation-plan-or-trust-changed')
    # The namespace follows the nonce within the fixed repository. Changing a
    # plan, work order, run id or job cannot reuse the same signed nonce.
    name = 'factory-human-drill-consumed-' + binding['nonce_sha256']
    record = dict(schema='factory-human-drill-consumption/1',
                  case_id=binding['case_id'], nonce_sha256=binding['nonce_sha256'],
                  plan_sha256=model['plan_sha256'], decision_sha256=model['decision_sha256'],
                  trusted_journal_head=model['trusted_journal_head'],
                  work_order_sha256=binding['work_order_sha256'],
                  execution_policy_sha256=binding['execution_policy_sha256'], ci=identity,
                  consumed_before_execution=True, execution_authorized=False,
                  admission_receipt_issued=False)
    record['content_sha256'] = canonical_hash(record)
    message = json.dumps(record, sort_keys=True, separators=(',', ':'))
    # An annotated object binds the exact record. It is NOT cryptographically
    # signed. An orphan object after any failure is never execution authority.
    tag = api.request('POST', _PREFIX + '/git/tags',
                      dict(tag=name, message=message, object=head, type='commit'))
    if (not isinstance(tag.get('sha'), str) or not re.fullmatch('[0-9a-f]{40}', tag['sha'])
            or tag.get('tag') != name or tag.get('message') != message
            or tag.get('object') != {'type': 'commit', 'sha': head,
                                    'url': 'https://api.github.com' + _PREFIX + '/git/commits/' + head}):
        raise ExecutionContractError('drill-reservation-tag-object-stop')
    # Atomic create is the only consumption transition. Existing refs, including
    # claims by this same run, fail. No force, PATCH, DELETE or retry exists.
    ref = 'refs/tags/' + name
    result = api.request('POST', _PREFIX + '/git/refs', dict(ref=ref, sha=tag['sha']))
    if (result.get('ref') != ref or result.get('object', {}).get('sha') != tag['sha']
            or result.get('object', {}).get('type') != 'tag'):
        raise ExecutionContractError('drill-reservation-ref-binding-stop')
    readback = api.request('GET', _PREFIX + '/git/ref/tags/' + name)
    object_readback = api.request('GET', _PREFIX + '/git/tags/' + tag['sha'])
    if (readback.get('ref') != ref or readback.get('object', {}).get('sha') != tag['sha']
            or readback.get('object', {}).get('type') != 'tag'
            or object_readback.get('sha') != tag['sha']
            or object_readback.get('tag') != name or object_readback.get('message') != message
            or object_readback.get('object') != tag['object']):
        raise ExecutionContractError('drill-reservation-readback-stop')
    if reverify() != review or _ci_identity(binding, head, api, environment) != identity:
        raise ExecutionContractError('drill-reservation-post-create-binding-stop-consumed')
    return dict(schema='factory-human-drill-reservation-review/1', status='consumed-only',
                ref=ref, tag_object_sha=tag['sha'], record=deepcopy(record),
                execution_authorized=False, admission_receipt_issued=False,
                unresolved=['role-action-authorization', 'oci-runtime-binding',
                            'output-authenticity-verification', 'cli-dispatch'])


def reserve_configured_main_plan(admission,order,policy):
    # No caller-provided API, environment, review, reverify callback, old claim
    # or resume flag is accepted at this production boundary.
    from .configured_human_admission import verify_configured_human_plan
    from .configured_human_main_identity import _main_environment
    from .tower_drill_context import _workflow_source
    review=verify_configured_human_plan(admission,order,policy)
    environment=_main_environment()
    source=_workflow_source(admission.root,review,environment)
    def reverify():
        if (_main_environment()!=environment
                or _workflow_source(admission.root,review,environment)!=source):
            raise ExecutionContractError('configured-main-consumption-source-or-environment-changed')
        # Actual clock and original proof are verified last, after workflow IO.
        return verify_configured_human_plan(admission,order,policy)
    return _consume_verified_main_plan(review,_GitHubAPI(),environment,reverify)
