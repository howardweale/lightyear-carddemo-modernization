"""Inactive answer-fragment preflight composition; no context or reservation.

Uses original native checks and current clocks/service observations. Returning
these bindings is not admission, execution approval, or strict outcome evidence.
"""
import os
from pathlib import Path

from lightyear_factory.model_admission import FactoryModelAdmission
from .backend import OCIContainerBackend
from .contracts import ExecutionContractError, ExecutionPolicy
from .configured_receipt_answer_admission import verify_answer_receipt_plan
from .configured_receipt_answer_runtime import verify_answer_receipt_runtime
from .configured_receipt_answer_models import review_answer_receipt_models
from .configured_receipt_answer_isolation import review_answer_receipt_isolation
from .configured_receipt_answer_materials import review_answer_receipt_public_materials
from .configured_receipt_answer_main import review_answer_receipt_main_identity
from .tower_drill_context import _workflow_source


def review_answer_receipt_preflight(admission,order,policy,backend,source_root,input_paths,manifest,model_path,isolation_path):
    if (type(admission) is not FactoryModelAdmission or type(policy) is not ExecutionPolicy
            or type(backend) is not OCIContainerBackend or backend.execute_enabled is not True
            or backend.policy.to_dict()!=policy.to_dict()):
        raise ExecutionContractError('configured-human-native-context-required')
    if any(part.casefold()=='onedrive' for part in Path(source_root).parts):
        raise ExecutionContractError('configured-human-onedrive-refused')
    review=verify_answer_receipt_plan(admission,order,policy)
    runtime=verify_answer_receipt_runtime(admission,order,policy,source_root=source_root,
        input_paths=input_paths,read_manifest=manifest)
    models=review_answer_receipt_models(admission,order,policy,model_path,
        input_paths=input_paths,read_manifest=manifest)
    values=review_answer_receipt_isolation(admission,order,policy,manifest,isolation_path)
    workflow=_workflow_source(admission.root,review,os.environ)
    public_materials=review_answer_receipt_public_materials(admission,order,policy,manifest)
    main=review_answer_receipt_main_identity(admission,order,policy)
    if verify_answer_receipt_plan(admission,order,policy)!=review:
        raise ExecutionContractError('configured-human-final-preflight-trust-changed')
    return dict(review=review,runtime=runtime,models=models,values=values,workflow=workflow,main=main,public_materials=public_materials)
