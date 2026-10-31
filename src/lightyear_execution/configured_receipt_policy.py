"""Exact receipt-policy parsing only; no key read, lease or authority.

The SSH signer uses separately provisioned external files. This policy describes
only broker-managed host secrets; it does not authorize signer provisioning.
"""
from copy import deepcopy
from dataclasses import replace
from .contracts import ExecutionContractError,ExecutionPolicy

POLICY_ID='lightyear:configured-receipt:configured-build-control'
TRANSPORT_SECRET='FACTORY_TRANSPORT_KEY'


def parse_configured_receipt_policy(payload):
    if type(payload) is not dict:
        raise ExecutionContractError('configured-receipt-policy-shape')
    value=deepcopy(payload)
    roles=value.get('identities',{}).get('roles',{})
    secrets=value.get('secrets',{})
    expected={
        'planner':{'actions':['factory:plan']},
        'failure_analyst':{'actions':['factory:analyze-failure']},
        'builder':{'actions':['factory:build']},
        'verifier':{'actions':['factory:verify']},
        'provider':{'actions':['secret:lease:OPENAI_API_KEY']},
        'recorder':{'actions':['secret:lease:FACTORY_TRANSPORT_KEY']}}
    if (value.get('id')!=POLICY_ID or roles!=expected
            or secrets!={'allowed_names':['OPENAI_API_KEY',TRANSPORT_SECRET],'persist_values':False}
            or any(name in value.get('runtime',{}).get('allowed_environment',[])
                   for name in ('OPENAI_API_KEY',TRANSPORT_SECRET))):
        raise ExecutionContractError('configured-receipt-policy-exact-scope')
    # Reuse the unchanged isolation/resource/public-key validation, not its
    # authority. Parsing a temporary structural projection creates no proof.
    base=deepcopy(value)
    base['id']='lightyear:configured-human:configured-build-control'
    del base['identities']['roles']['recorder']
    base['secrets']['allowed_names']=['OPENAI_API_KEY']
    parsed=ExecutionPolicy.from_configured_human_dict(base)
    result=replace(parsed,policy_id=POLICY_ID,
        role_actions={role:tuple(spec['actions']) for role,spec in sorted(expected.items())},
        allowed_secret_names=('OPENAI_API_KEY',TRANSPORT_SECRET))
    # All hashes and subsequent proof checks use the original receipt policy.
    # No additional fields or silently normalized scope may enter this route.
    if result.to_dict()!=value:
        raise ExecutionContractError('configured-receipt-policy-lossy-roundtrip')
    return result
