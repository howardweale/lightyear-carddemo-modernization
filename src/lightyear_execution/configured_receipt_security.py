"""Derive existing security-summary fields from original observed operations.

Registries describe the reviewed same process, not remote attestation. Synthetic
scope/evidence dictionaries alone cannot establish any of these observations.
"""
from copy import deepcopy
from weakref import WeakKeyDictionary
from .contracts import ExecutionContractError,canonical_hash

_AUTH=WeakKeyDictionary();_LEASES=WeakKeyDictionary()
_GATES=WeakKeyDictionary();_PENDING=WeakKeyDictionary()


def _live(context):
    from .configured_receipt_context import ConfiguredReceiptExecutionContext
    if type(context) is not ConfiguredReceiptExecutionContext:
        raise ExecutionContractError('configured-security-original-context-required')
    context._live()


def observe_authorization(context,scope):
    _live(context)
    from .configured_receipt_scopes import verify_configured_receipt_role
    current=verify_configured_receipt_role(context._admission,context._order,context.policy,scope['role'],scope['action'])
    if current!=scope:raise ExecutionContractError('configured-security-original-role-required')
    _AUTH.setdefault(context,[]).append(deepcopy(scope))


def observe_lease(context,scope,receipt):
    _live(context)
    from .configured_receipt_scopes import verify_configured_receipt_role
    pairs={'OPENAI_API_KEY':'provider','FACTORY_TRANSPORT_KEY':'recorder'}
    name=receipt.get('name');role=pairs.get(name)
    if role is None:raise ExecutionContractError('configured-security-secret-scope')
    current=verify_configured_receipt_role(context._admission,context._order,context.policy,role,'secret:lease:'+name)
    expected=dict(name=name,role=role,work_order_sha256=context._order.content_sha256,
        execution_policy_sha256=context.policy.content_sha256,
        admission_receipt_sha256=context.admission_receipt['content_sha256'],
        role_scope_sha256=current['content_sha256'],one_use=True,persisted=False)
    expected['content_sha256']=canonical_hash(expected)
    rows=_LEASES.setdefault(context,[])
    if current!=scope or receipt!=expected or any(row['name']==name for row in rows):
        raise ExecutionContractError('configured-security-original-lease-required')
    _LEASES[context].append(deepcopy(receipt))


def accept_original_gate_report(context,report):
    _live(context);pending=_PENDING.get(context)
    if (pending is None or pending[0] is not report or pending[1]!=canonical_hash(report)):
        raise ExecutionContractError('configured-security-original-gate-report-required')
    del _PENDING[context]
    rows=deepcopy([row['execution'] for row in report['gates']])
    _GATES.setdefault(context,[]).extend(rows)
    return deepcopy(rows)


def receipt_security_summary(context,required_actions=None):
    _live(context)
    actions=required_actions or {('planner','factory:plan'),('verifier','factory:verify')}
    auth=_AUTH.get(context,[]);leases=_LEASES.get(context,[]);gates=_GATES.get(context,[])
    if (auth!=context.authorization_receipts or leases!=context.secret_receipts
            or gates!=context.execution_evidence):
        raise ExecutionContractError('configured-security-observed-evidence-changed')
    authorized={(row['role'],row['action']) for row in auth}
    gates_enforced=bool(gates) and context not in _PENDING and all(
        row.get('enforced') is True and row.get('assurance')=='enforced'
        and row.get('network_mode')=='none' and row.get('workspace_read_only') is True
        and row.get('candidate_build_root')=='/tmp/factory-build'
        and row.get('content_sha256')==canonical_hash(row,{'content_sha256'}) for row in gates)
    actions_authorized=actions.issubset(authorized)
    leases_bound=(context._lease_completed and context._transport_lease_completed
        and {row['name'] for row in leases}=={'OPENAI_API_KEY','FACTORY_TRANSPORT_KEY'})
    gaps=[]
    if not gates_enforced:gaps.append('container-runtime-enforcement-not-observed')
    if not actions_authorized:gaps.append('required-agent-actions-not-authorized')
    if not leases_bound:gaps.append('original-host-secret-leases-not-observed')
    enforced=gates_enforced and actions_authorized and leases_bound
    # Same existing security-summary shape. Identity list is empty because the
    # human proof path issues no machine credentials; do not invent them.
    result=dict(evidence_class='signed-admitted-oci-factory-run',
        status='enforced' if enforced else 'simulated',production_ready=enforced,
        backend=context.backend.backend_id,work_order_sha256=context._order.content_sha256,
        execution_policy_sha256=context.policy.content_sha256,
        admission_receipt_sha256=context.admission_receipt['content_sha256'],identity_receipt_sha256=[],
        authorization_receipt_sha256=[row['content_sha256'] for row in auth],
        required_agent_actions=sorted(role+':'+action for role,action in actions),
        authorized_agent_actions=sorted(role+':'+action for role,action in authorized),
        gate_execution_sha256=[row['content_sha256'] for row in gates],
        secret_lease_sha256=[row['content_sha256'] for row in leases],secrets_persisted=False,gaps=gaps)
    result['content_sha256']=canonical_hash(result)
    return result
