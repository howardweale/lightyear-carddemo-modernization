"""Read-only human-proof and public expected-output verification.

An expected-output match is not proof that the controller produced the supplied
observations. This component grants no execution or receipt qualification.
"""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import PurePosixPath
import re

from lightyear_factory.model_admission import FactoryModelAdmission, _bounded_regular_bytes
from .contracts import ExecutionContractError, canonical_hash
from .tower_drill_admission import verify_human_drill_plan


def _digest(value):
    return isinstance(value,str) and re.fullmatch('[0-9a-f]{64}',value) is not None


def validate_public_output_plan(script, order_hash, case_id):
    fields={'schema','case_id','work_order_sha256','provider','model','steps','content_sha256'}
    if (type(script) is not dict or set(script)!=fields
            or script['schema']!='factory-public-drill-outputs/1'
            or script['case_id']!=case_id or script['work_order_sha256']!=order_hash
            or script['provider']!='p5-scripted'
            or not re.fullmatch(r'p5-stub-\d{4}-\d{2}-\d{2}',str(script['model']))
            or script['content_sha256']!=canonical_hash(script,{'content_sha256'})
            or type(script['steps']) is not list or not 1<=len(script['steps'])<=32):
        raise ExecutionContractError('public-drill-output-plan-binding')
    for index,row in enumerate(script['steps'],1):
        if (type(row) is not dict or set(row)!={'sequence','role','invocation_sha256','schema_sha256',
                                              'response_content','response_sha256'}
                or type(row['sequence']) is not int or row['sequence']!=index
                or row['role'] not in {'planner','builder','failure_analyst'}
                or not _digest(row['invocation_sha256']) or not _digest(row['schema_sha256'])
                or type(row['response_content']) is not dict
                or row['response_sha256']!=canonical_hash({'content':row['response_content']})):
            raise ExecutionContractError('public-drill-output-step-binding')
    try:json.dumps(script,ensure_ascii=False,allow_nan=False).encode('utf-8')
    except (ValueError,UnicodeError):raise ExecutionContractError('public-drill-output-json') from None
    return deepcopy(script)


def match_public_outputs(script, observed):
    """Pure comparison only. The caller still must authenticate observation origin."""
    script=validate_public_output_plan(script,script.get('work_order_sha256'),script.get('case_id'))
    if (type(observed) is not list
            or canonical_hash({'steps':observed})!=canonical_hash({'steps':script['steps']})):
        raise ExecutionContractError('public-drill-output-mismatch')
    result=dict(schema='factory-public-drill-output-comparison/1',status='matched-expected-content',
        expected_plan_sha256=script['content_sha256'],steps=len(observed),
        response_sha256=[row['response_sha256'] for row in observed],
        controller_origin_verified=False,execution_authorized=False,qualifies_for_factory_receipt=False)
    result['content_sha256']=canonical_hash(result)
    return result


def require_public_contract_source(contract, binding):
    """Match the installed Tower's three-field source shape; grants no authority."""
    from lightyear_control_tower.factory_policy import validate_contract
    validate_contract(contract, check_evidence=False)
    if (type(binding) is not dict or set(binding) != {'path', 'sha256'}
            or not isinstance(binding['path'], str)
            or not binding['path'].startswith('docs/factory/p5-human-clean-control/')
            or not _digest(binding['sha256'])):
        raise ExecutionContractError('public-drill-contract-source-binding')
    expected = dict(binding, commit=contract['details']['executable_commit'])
    if contract['kind'] != 'engineering-run-approval' or expected not in contract['sources']:
        raise ExecutionContractError('public-drill-contract-source-binding')


def review_public_drill_outputs(admission,order,policy,script_path):
    if type(admission) is not FactoryModelAdmission:
        raise ExecutionContractError('public-drill-genuine-admission-required')
    path=PurePosixPath(str(script_path))
    if (path.is_absolute() or '..' in path.parts or '\\' in str(script_path)
            or not str(path).startswith('docs/factory/p5-human-clean-control/') or path.suffix!='.json'):
        raise ExecutionContractError('public-drill-public-fixture-path-required')
    review=verify_human_drill_plan(admission,order,policy)
    plan=admission._committed_json(admission.paths[0])
    binding=plan.get('public_drill_outputs')
    if (type(binding) is not dict or set(binding)!={'path','sha256'}
            or binding['path']!=str(path) or not _digest(binding['sha256'])):
        raise ExecutionContractError('public-drill-signed-output-binding-required')
    contract=admission._committed_json(admission.paths[2])
    require_public_contract_source(contract, binding)
    script=admission._committed_json(str(path))
    raw=_bounded_regular_bytes(admission.root/str(path),262144,'public-drill-fixture-size')
    if sha256(raw).hexdigest()!=binding['sha256']:
        raise ExecutionContractError('public-drill-fixture-byte-binding')
    validated=validate_public_output_plan(script,order.content_sha256,review['drill_binding']['case_id'])
    if any(v!={'provider':'p5-scripted','model':validated['model']} for v in plan['roles'].values()):
        raise ExecutionContractError('public-drill-output-model-binding')
    if verify_human_drill_plan(admission,order,policy)!=review or admission._committed_json(str(path))!=script:
        raise ExecutionContractError('public-drill-output-review-changed')
    result=dict(schema='factory-human-public-proof-preflight/1',status='verified-review-only',
        plan_sha256=review['verified_model_admission']['plan_sha256'],
        decision_sha256=review['verified_model_admission']['decision_sha256'],
        trusted_journal_head=review['verified_model_admission']['trusted_journal_head'],
        output_plan_sha256=validated['content_sha256'],output_file_sha256=binding['sha256'],
        expected_steps=len(validated['steps']),nonce_consumed=False,signatures_created=0,
        model_calls=0,execution_authorized=False,qualifies_for_factory_receipt=False,
        gaps=['cli-execution-dispatch-not-integrated','controller-output-origin-not-bound',
              'full-controller-receipt-route-not-integrated'])
    result['content_sha256']=canonical_hash(result)
    return result
