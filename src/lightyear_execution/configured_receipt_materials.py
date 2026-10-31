"""Read only signed public signer/key-id sources; never provision or read keys."""
from hashlib import sha256
import re,subprocess
from lightyear_factory.authorship import FACTORY_EMAIL
from lightyear_factory.model_admission import _bounded_regular_bytes
from lightyear_factory.process_environment import _without_provider_credentials
from .contracts import ExecutionContractError
from .configured_receipt_admission import verify_configured_receipt_plan

_ROOT='docs/factory/p5-human-clean-control/configured-build-control/'
SIGNERS=_ROOT+'receipt-allowed-signers.txt'
KEY_ID=_ROOT+'receipt-encryption-key-id.txt'


def validate_public_material_bytes(signers,key_id):
    if (type(signers) is not bytes or type(key_id) is not bytes
            or len(signers)>4096 or len(key_id)>129):
        raise ExecutionContractError('configured-receipt-public-material-shape')
    try:
        trust=signers.decode('ascii');identity=key_id.decode('ascii')
    except UnicodeError:
        raise ExecutionContractError('configured-receipt-public-material-encoding') from None
    if (not re.fullmatch(re.escape(FACTORY_EMAIL)+r' ssh-ed25519 [A-Za-z0-9+/]+={0,2}\n',trust)
            or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\n',identity)):
        raise ExecutionContractError('configured-receipt-public-material-format')
    return identity[:-1]


def _committed_public_bytes(admission,path):
    # Paths are fixed by this module, never arbitrary key-path arguments.
    if path not in (SIGNERS,KEY_ID):raise ExecutionContractError('configured-receipt-public-path')
    raw=_bounded_regular_bytes(admission.root/path,4096,'configured-receipt-public-material')
    command=['git','--no-optional-locks','-C',str(admission.root)]
    oid=subprocess.check_output(command+['rev-parse','--verify','HEAD:'+path], env=_without_provider_credentials()).decode().strip()
    if not re.fullmatch('[0-9a-f]{40}|[0-9a-f]{64}',oid):
        raise ExecutionContractError('configured-receipt-public-object')
    size=int(subprocess.check_output(command+['cat-file','-s',oid], env=_without_provider_credentials()))
    if size!=len(raw) or not 0<size<=4096:
        raise ExecutionContractError('configured-receipt-public-size')
    if subprocess.check_output(command+['cat-file','blob',oid], env=_without_provider_credentials())!=raw:
        raise ExecutionContractError('configured-receipt-public-not-committed')
    return raw


def review_receipt_public_materials(admission,order,policy,manifest):
    review=verify_configured_receipt_plan(admission,order,policy)
    plan=admission._committed_json(admission.paths[0])
    contract=admission._committed_json(admission.paths[2])
    if type(manifest) is not dict or any(path in manifest for path in (SIGNERS,KEY_ID)):
        raise ExecutionContractError('configured-receipt-public-material-worker-exclusion')
    result={}
    for path in (SIGNERS,KEY_ID):
        raw=_committed_public_bytes(admission,path);digest=sha256(raw).hexdigest()
        rows=[row for row in contract['sources'] if row['path']==path]
        if rows!=[dict(path=path,sha256=digest,commit=plan['executable_commit'])]:
            raise ExecutionContractError('configured-receipt-public-material-not-signed')
        result[path]=dict(sha256=digest,raw=raw.decode('ascii'))
    result['key_id']=validate_public_material_bytes(result[SIGNERS]['raw'].encode('ascii'),result[KEY_ID]['raw'].encode('ascii'))
    for path in (SIGNERS,KEY_ID):
        if _committed_public_bytes(admission,path).decode('ascii')!=result[path]['raw']:
            raise ExecutionContractError('configured-receipt-public-material-changed')
    if verify_configured_receipt_plan(admission,order,policy)!=review:
        raise ExecutionContractError('configured-receipt-public-material-proof-changed')
    return result
