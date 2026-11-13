"""Native unsigned fixture rebinding and independently observed producer identity.

No proof, authority or passed context can be supplied by this helper. Source is
an unexecuted proposal until exact workflow/publication approval and real CI.
"""
import json,os,re,subprocess
from pathlib import Path

REPOSITORY='howardweale/lightyear-carddemo-modernization'
PRODUCER='.github/workflows/operator-flow-producer.yml'
CONSUMER='.github/workflows/operator-flow-consumer.yml'

def require(value,reason):
    if not value:raise ValueError(reason)

def live_producer_identity(source,executable,*,approval):
    from tools.ci.operator_flow_producer_pr import live_identity
    return live_identity(source,executable,approval)

def prepare_native_documents(root,executable,window,nonce_sha256):
    from tools.ci.p5_human_signing_pack import prepare,DOCUMENTS,FIXTURES
    from lightyear_factory.contracts import WorkOrder,canonical_hash
    from lightyear_execution.contracts import ExecutionPolicy
    from lightyear_execution.tower_drill_admission import _validate_drill_binding
    from lightyear_control_tower.factory_policy import validate_contract
    from lightyear_control_tower.decisions import canonical
    raw=prepare(root,executable,window,nonce_sha256)
    # All native input and formatter checks run before rebinding and signing.
    # A dedicated consumer workflow MUST already exist in exact E; no post-sign
    # source edit or mutable workflow selection is accepted.
    consumer=Path(root)/CONSUMER
    require(consumer.is_file() and not consumer.is_symlink()
        and consumer.stat().st_nlink==1 and consumer.stat().st_size<=262144,
        'producer-consumer-source-required')
    committed=subprocess.check_output(['git','--no-optional-locks','-C',str(root),'show',executable+':'+CONSUMER])
    require(consumer.read_bytes()==committed,'producer-consumer-source-changed')
    plan=json.loads(raw['plan.json']);contract=json.loads(raw['contract.json'])
    order=WorkOrder.load(Path(root)/(FIXTURES+'work-order.json'))
    policy=ExecutionPolicy.load(Path(root)/(DOCUMENTS+'execution-policy.json'))
    plan['drill_admission']['ci']['workflow_ref']=REPOSITORY+'/'+CONSUMER+'@'+executable
    plan['drill_admission']['ci']['job']='operator-consumer'
    _validate_drill_binding(plan['drill_admission'],order,policy)
    plan['content_sha256']=canonical_hash(plan,{'content_sha256'})
    contract['details']['request_seal']=plan['content_sha256']
    validate_contract(contract,check_evidence=False)
    return {'plan.json':canonical(plan),'contract.json':canonical(contract)}
