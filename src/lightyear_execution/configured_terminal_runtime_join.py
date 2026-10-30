"""Join terminal evidence to original validated runtime inputs; no proof reentry.

The same-process reader supplies its origin-bound context runtime. The parent
supplies only the runtime obtained by its original prelaunch native preflight.
Mappings alone grant no authority; no current proof, reservation or retry occurs.
"""
from lightyear_factory.contracts import ContractError,canonical_hash


def _require(ok,reason):
    if not ok:raise ContractError('configured-terminal-runtime-'+reason)


def match_terminal_runtime(receipt,admission,identity,runtime):
    for value in (receipt,admission,identity):
        _require(type(value) is dict and value.get('content_sha256')==
            canonical_hash(value,{'content_sha256'}),'record-digest')
    _require(type(runtime) is dict and runtime.get('schema')=='factory-model-admission/1'
        and runtime.get('provider_verified') is False,'shape')
    for name in ('plan_sha256','decision_sha256','trusted_journal_head','work_order_sha256'):
        _require(name in runtime and runtime[name]==admission.get(name),'admission-field')
    _require(runtime['work_order_sha256']==receipt.get('work_order_sha256')
        ==identity.get('work_order_sha256')
        and identity.get('admission_receipt_sha256')==admission['content_sha256'],'identity')
    manifest=runtime.get('workspace_read_manifest')
    _require(type(manifest) is dict and bool(manifest)
        and canonical_hash(manifest)==identity.get('workspace_inventory_sha256'),'workspace')
    digest=canonical_hash(runtime)
    _require(admission.get('runtime_binding_sha256')==digest,'admission-digest')
    if 'factory_build_receipt' in receipt:
        build=receipt['factory_build_receipt']
        _require(type(build) is dict and build.get('current_admission_sha256')==digest,'build-digest')
    # Early native refusals can lack a build verdict; no absent verdict created.
    return None
