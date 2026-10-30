"""Inactive answer model-byte review; no provider or credential construction."""
from hashlib import sha256
import json
from pathlib import Path
from lightyear_factory.contracts import ContractError
from lightyear_factory.model_admission import _bounded_regular_bytes
from lightyear_factory.workspace import IsolatedWorkspace
from .configured_receipt_models import validate_control_model_document
from .configured_receipt_answer_admission import verify_answer_receipt_plan
from .configured_receipt_answer_runtime import verify_answer_receipt_runtime
from .configured_receipt_answer_inputs import DOCUMENTS

MODELS = DOCUMENTS + 'models.json'

def _require(value, reason):
    if not value:
        raise ContractError(reason)


def review_answer_receipt_models(admission,order,policy,config_path,*,input_paths,read_manifest):
    review=verify_answer_receipt_plan(admission,order,policy)
    runtime=verify_answer_receipt_runtime(admission,order,policy,source_root=admission.root,
        input_paths=input_paths,read_manifest=read_manifest)
    plan=admission._committed_json(admission.paths[0])
    contract=admission._committed_json(admission.paths[2])
    candidate=Path(config_path)
    if not candidate.is_absolute():candidate=admission.root/candidate
    try:relative=candidate.relative_to(admission.root).as_posix()
    except ValueError:raise ContractError('configured-human-model-path') from None
    IsolatedWorkspace._strict_relative(relative)
    _require(relative == MODELS, 'configured-answer-exact-model-path')
    document=admission._committed_json(relative)
    raw=_bounded_regular_bytes(candidate,65536,'configured-human-model-bytes')
    _require(json.loads(raw)==document,'configured-human-model-changed')
    digest=sha256(raw).hexdigest()
    matches=[row for row in contract['sources'] if row['path']==relative]
    _require(matches==[dict(path=relative,sha256=digest,commit=plan['executable_commit'])],
             'configured-human-model-not-human-bound')
    value=validate_control_model_document(document,plan['roles'])
    _require(_bounded_regular_bytes(candidate,65536,'configured-human-model-bytes')==raw
             and verify_answer_receipt_runtime(admission,order,policy,source_root=admission.root,
                 input_paths=input_paths,read_manifest=read_manifest)==runtime
             and verify_answer_receipt_plan(admission,order,policy)==review,
             'configured-human-model-final-window-or-input-changed')
    return dict(path=relative,sha256=digest,document=value,
        plan_sha256=runtime['plan_sha256'],decision_sha256=runtime['decision_sha256'],
        trusted_journal_head=runtime['trusted_journal_head'],
        work_order_sha256=order.content_sha256,execution_policy_sha256=policy.content_sha256)
