"""Inactive answer runtime input reader; no workspace creation or authority."""
from hashlib import sha256
from pathlib import Path
import re

from lightyear_factory.model_admission import _bounded_regular_bytes
from lightyear_factory.workspace import IsolatedWorkspace
from .contracts import ExecutionContractError, ExecutionPolicy
from .configured_receipt_answer_admission import verify_answer_receipt_plan
from .configured_receipt_answer_policy import parse_answer_receipt_policy
from .configured_receipt_answer_inputs import validate_answer_input_bindings, validate_answer_workspace_scope


def verify_answer_receipt_runtime(admission, order, policy, *, source_root,
                                    input_paths, read_manifest):
    # Genuine proof verification occurs before accessing any caller paths.
    review = verify_answer_receipt_plan(admission, order, policy)
    if (Path(source_root).resolve() != admission.root
            or type(input_paths) is not dict
            or set(input_paths) != {'scope','freeze','workspace','execution_policy'}):
        raise ExecutionContractError('configured-human-runtime-root-or-inputs')
    plan = admission._committed_json(admission.paths[0])
    from lightyear_factory.contracts import canonical_hash
    if canonical_hash(plan, {'content_sha256'}) != review['verified_model_admission']['plan_sha256']:
        raise ExecutionContractError('configured-human-runtime-plan-changed')
    validate_answer_input_bindings(plan)
    loaded = {}; raw_inputs = {}; workspace_bytes = {}
    for name, path in input_paths.items():
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = admission.root / candidate
        try:
            relative = candidate.relative_to(admission.root).as_posix()
        except ValueError:
            raise ExecutionContractError('configured-human-runtime-path') from None
        IsolatedWorkspace._strict_relative(relative)
        bound = plan['bound_inputs'][name]
        if relative != bound['path']:
            raise ExecutionContractError('configured-human-runtime-path')
        loaded[name] = admission._committed_json(relative)
        raw = _bounded_regular_bytes(candidate,8*1024*1024,'configured-human-runtime-bytes')
        if sha256(raw).hexdigest() != bound['sha256']:
            raise ExecutionContractError('configured-human-runtime-bytes')
        raw_inputs[relative] = raw
    manifest = loaded['workspace']
    if type(manifest) is not dict or not manifest or read_manifest != manifest:
        raise ExecutionContractError('configured-human-runtime-manifest')
    validate_answer_workspace_scope(order, manifest)
    for path, digest in manifest.items():
        IsolatedWorkspace._strict_relative(path)
        if type(digest) is not str or not re.fullmatch('[0-9a-f]{64}',digest):
            raise ExecutionContractError('configured-human-runtime-manifest')
        raw = _bounded_regular_bytes(admission.root/path,order.max_file_bytes,
                                     'configured-human-workspace-bytes')
        if sha256(raw).hexdigest() != digest:
            raise ExecutionContractError('configured-human-workspace-bytes')
        workspace_bytes[path] = raw
    parsed = parse_answer_receipt_policy(loaded['execution_policy'])
    if parsed.to_dict() != policy.to_dict():
        raise ExecutionContractError('configured-human-runtime-policy')
    # No caller-provided clock: a long hash pass cannot extend the signed window.
    if verify_answer_receipt_plan(admission,order,policy) != review:
        raise ExecutionContractError('configured-human-runtime-proof-changed')
    for relative, raw in raw_inputs.items():
        if _bounded_regular_bytes(admission.root/relative,8*1024*1024,
                'configured-human-runtime-bytes') != raw:
            raise ExecutionContractError('configured-human-runtime-input-changed')
    for relative, raw in workspace_bytes.items():
        if _bounded_regular_bytes(admission.root/relative,order.max_file_bytes,
                'configured-human-workspace-bytes') != raw:
            raise ExecutionContractError('configured-human-workspace-changed')
    if verify_answer_receipt_plan(admission,order,policy) != review:
        raise ExecutionContractError('configured-human-final-runtime-window-or-trust-changed')
    return dict(review['verified_model_admission'],
                workspace_read_manifest=dict(manifest))
