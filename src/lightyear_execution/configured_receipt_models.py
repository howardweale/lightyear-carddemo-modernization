"""Inactive configured human model-byte preflight; no provider construction.

No HMAC review entry is imported or substituted. The shared pure model document
validator grants nothing. Genuine current human proof and runtime input bindings
must verify before and after the exact committed model bytes are read.
"""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from lightyear_factory.contracts import ContractError
from lightyear_factory.flex_billing import validate_flex_billing
from lightyear_factory.model_admission import _bounded_regular_bytes
from lightyear_factory.model_versions import require_snapshot
from lightyear_factory.workspace import IsolatedWorkspace
from .configured_receipt_admission import verify_configured_receipt_plan
from .configured_receipt_runtime import verify_configured_receipt_runtime

def _require(value, reason):
    if not value:
        raise ContractError(reason)


def validate_control_model_document(document, roles):
    """Pure scope validation, with no proof or authority claim."""
    _require(type(document) is dict and set(document) == {'default', 'models'},
             'configured-control-no-routing-or-fallback')
    models = document['models']
    default = document['default']
    _require(type(default) is str and bool(default) and type(models) is dict
             and set(models) == {default}, 'configured-control-single-model')
    model = models[default]
    fields = {'provider', 'model', 'input_usd_per_million', 'output_usd_per_million',
              'max_output_tokens', 'service_tier', 'billing_policy'}
    _require(type(model) is dict and set(model) == fields,
             'configured-control-model-fields')
    _require(model['provider'] == 'openai' and model['service_tier'] == 'flex'
             and type(model['max_output_tokens']) is int
             and 1 <= model['max_output_tokens'] <= 65536,
             'configured-control-provider-tier')
    require_snapshot(model['model'])
    _require(type(roles) is dict and set(roles) == {'planner', 'analyst', 'builder'}
             and all(row == {'provider': 'openai-responses', 'model': model['model']}
                     for row in roles.values()), 'configured-control-plan-roles')
    validate_flex_billing(model['billing_policy'], model=model['model'],
        input_price=model['input_usd_per_million'],
        output_price=model['output_usd_per_million'], token_preflight=True,
        max_retries=0, service_tier='flex')
    return deepcopy(document)



def review_configured_receipt_models(admission,order,policy,config_path,*,input_paths,read_manifest):
    review=verify_configured_receipt_plan(admission,order,policy)
    runtime=verify_configured_receipt_runtime(admission,order,policy,source_root=admission.root,
        input_paths=input_paths,read_manifest=read_manifest)
    plan=admission._committed_json(admission.paths[0])
    contract=admission._committed_json(admission.paths[2])
    candidate=Path(config_path)
    if not candidate.is_absolute():candidate=admission.root/candidate
    try:relative=candidate.relative_to(admission.root).as_posix()
    except ValueError:raise ContractError('configured-human-model-path') from None
    IsolatedWorkspace._strict_relative(relative)
    document=admission._committed_json(relative)
    raw=_bounded_regular_bytes(candidate,65536,'configured-human-model-bytes')
    _require(json.loads(raw)==document,'configured-human-model-changed')
    digest=sha256(raw).hexdigest()
    matches=[row for row in contract['sources'] if row['path']==relative]
    _require(matches==[dict(path=relative,sha256=digest,commit=plan['executable_commit'])],
             'configured-human-model-not-human-bound')
    value=validate_control_model_document(document,plan['roles'])
    _require(_bounded_regular_bytes(candidate,65536,'configured-human-model-bytes')==raw
             and verify_configured_receipt_runtime(admission,order,policy,source_root=admission.root,
                 input_paths=input_paths,read_manifest=read_manifest)==runtime
             and verify_configured_receipt_plan(admission,order,policy)==review,
             'configured-human-model-final-window-or-input-changed')
    return dict(path=relative,sha256=digest,document=value,
        plan_sha256=runtime['plan_sha256'],decision_sha256=runtime['decision_sha256'],
        trusted_journal_head=runtime['trusted_journal_head'],
        work_order_sha256=order.content_sha256,execution_policy_sha256=policy.content_sha256)
