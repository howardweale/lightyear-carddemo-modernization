"""Inactive configured public-only isolation inputs; no secret access.

Uses the existing public isolation document shape and path restrictions. It
does not accept a scripted output plan as configured output evidence.
"""
from hashlib import sha256
from lightyear_factory.contracts import ContractError,canonical_hash
from lightyear_factory.model_admission import _bounded_regular_bytes
from .configured_receipt_admission import verify_configured_receipt_plan
from .human_drill_dispatch import _public_path,validate_public_domain
from .public_drill_outputs import require_public_contract_source


def validate_configured_isolation_document(value,order_sha256):
    fields={'schema','case_id','work_order_sha256','values','content_sha256'}
    if (type(value) is not dict or set(value)!=fields
            or value['schema']!='factory-public-drill-isolation/1'
            or value['case_id']!='configured-build-control'
            or value['work_order_sha256']!=order_sha256
            or value['content_sha256']!=canonical_hash(value,{'content_sha256'})
            or type(value['values']) is not list or not 3<=len(value['values'])<=32
            or any(type(v) is not str or len(''.join(v.casefold().split()))<40 for v in value['values'])
            or len(set(value['values']))!=len(value['values'])):
        raise ContractError('configured-human-public-isolation-content')
    return tuple(value['values'])


def review_configured_receipt_isolation(admission,order,policy,manifest,path):
    review=verify_configured_receipt_plan(admission,order,policy)
    path=_public_path(path)
    plan=admission._committed_json(admission.paths[0]);binding=plan.get('public_drill_isolation')
    if (type(binding) is not dict or set(binding)!={'path','sha256'} or binding['path']!=path
            or path in manifest or 'public_drill_outputs' in plan):
        raise ContractError('configured-human-isolation-binding-or-scripted-output')
    # Reuse the public workspace restrictions, without manufacturing an output
    # file. The same isolation path is excluded in both argument positions.
    validate_public_domain(order,manifest,path,path)
    require_public_contract_source(admission._committed_json(admission.paths[2]),binding)
    value=admission._committed_json(path)
    raw=_bounded_regular_bytes(admission.root/path,65536,'configured-human-isolation-bytes')
    if sha256(raw).hexdigest()!=binding['sha256']:
        raise ContractError('configured-human-isolation-byte-binding')
    values=validate_configured_isolation_document(value,order.content_sha256)
    if (_bounded_regular_bytes(admission.root/path,65536,'configured-human-isolation-bytes')!=raw
            or verify_configured_receipt_plan(admission,order,policy)!=review):
        raise ContractError('configured-human-isolation-final-window-or-trust-changed')
    return values
