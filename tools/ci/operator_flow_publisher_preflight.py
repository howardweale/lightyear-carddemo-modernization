"""Read-only external publication preflight; no remote publisher or authority.

Requires separately prepared independent E/M and public trust. Historical
review success cannot replace original current native proof/trust/runtime
verification. No clock, verifier, API, old-claim or context injection.
"""
import hashlib,re,sys,types
from pathlib import Path
from lightyear_factory.contracts import WorkOrder
from lightyear_factory.model_admission import FactoryModelAdmission,_bounded_regular_bytes
from lightyear_execution.contracts import ExecutionPolicy
from lightyear_execution.tower_drill_admission import verify_human_drill_plan
from lightyear_execution.tower_drill_reservation import _GitHubAPI
from tools.ci.operator_flow_completed_review import read_reviewed_publication,_snapshot
from tools.ci.operator_flow_publication_review import _independent_expectations,_prepared_trust
from tools.ci.operator_flow_review_source import check_review_source,_source_bytes,LIMIT
from tools.ci.operator_flow_review_cli import SCALARS
from tools.ci.operator_flow_review_workflow import _trust_bytes
from tools.ci.operator_flow_handoff import _original_producer
from tools.ci.operator_flow_consumer import clean_root,git,check_metadata,check_native_review,METADATA
from tools.ci.operator_flow_metadata import PREFIX,object_id,require
from tools.ci import operator_flow_tree_guards as tree_guards
from tools.ci.operator_flow_native_inputs import REPOSITORY

EXTRA_SOURCES=(
    ('tools.ci.operator_flow_review_cli','tools/ci/operator_flow_review_cli.py'),
    ('tools.ci.operator_flow_review_workflow','tools/ci/operator_flow_review_workflow.py'),
    ('tools.ci.operator_flow_completed_review','tools/ci/operator_flow_completed_review.py'),
    ('tools.ci.operator_flow_publisher_preflight','tools/ci/operator_flow_publisher_preflight.py'),
)

def _source_snapshot(root,executable):
    observed=check_review_source(root,executable)
    for name,relative in EXTRA_SOURCES:
        module=sys.modules.get(name);path=root/relative
        require(type(module) is types.ModuleType,'publisher-source-module')
        spec=getattr(module,'__spec__',None)
        require(all(type(v) is str and Path(v)==path and Path(v).is_absolute()
            for v in (getattr(module,'__file__',None),getattr(spec,'origin',None))),
            'publisher-source-origin')
        raw=_source_bytes(path);ref=executable+':'+relative
        size=git(root,'cat-file','-s',ref).decode().strip()
        require(re.fullmatch('[1-9][0-9]{0,7}',size) and int(size)<=LIMIT,'publisher-source-size')
        committed=git(root,'show',ref)
        require(len(committed)==int(size) and raw==committed,'publisher-source-bytes')
        observed[name]=hashlib.sha256(raw).hexdigest()
    clean_root(root);require(git(root,'rev-parse','HEAD').decode().strip()==executable,'publisher-source-head')
    return observed

def _metadata_files(candidate,values):
    require(type(candidate) is dict and candidate.get('parent')==values['executable']
        and candidate.get('commit')==values['metadata_head'],'publisher-exact-candidate')
    require(all(candidate.get(k) is False for k in ('native_proof_verified','full_guards_passed',
        'publish_ready','publication_authorized','full_route_passed','real_pack_ready')),'publisher-no-authority')
    rows=candidate.get('files');objects=candidate.get('objects')
    require(type(rows) is list and len(rows)==3 and all(type(row) is dict for row in rows)
        and {row.get('path') for row in rows}==set(METADATA.values()) and type(objects) is dict,
        'publisher-original-metadata-inventory')
    result={}
    for name,path in METADATA.items():
        row=next(row for row in rows if row['path']==path)
        require(row.get('before') is None,'publisher-new-metadata-only')
        value=objects.get(row.get('git_blob'))
        require(type(value) is tuple and len(value)==2 and value[0]=='blob'
            and type(value[1]) is bytes and 0<len(value[1])<=2097152,'publisher-original-metadata-blob')
        require(object_id(*value)==row['git_blob'] and hashlib.sha256(value[1]).hexdigest()==row.get('sha256'),
            'publisher-original-metadata-digests')
        result[name]=value[1]
    return result

def _public_materials(executable_root,metadata_root,trust_path,values):
    trust_path=Path(trust_path)
    require(trust_path.is_absolute() and trust_path.name=='trust.json','publisher-external-public-path')
    public=_bounded_regular_bytes(trust_path.parent/'public.pem',65536,'publisher-public-key-bytes')
    require(hashlib.sha256(public).hexdigest()==values['public_key_sha256'],'publisher-independent-public-key')
    files={'public.pem':public,'trust.json':_trust_bytes(values['journal_head_sha256'])}
    _prepared_trust(executable_root,metadata_root,trust_path,files)
    return files

def _main_identity(row,expected):
    require(type(expected) is str and re.fullmatch('[0-9a-f]{40}',expected),'publisher-main-expectation')
    require(type(row) is dict and row.get('ref')=='refs/heads/main'
        and type(row.get('object')) is dict and row['object'].get('type')=='commit'
        and row['object'].get('sha')==expected,'publisher-current-main-changed')
    return expected

def _publication_tree(root,values,base,files):
    require(type(files) is dict and set(files)==set(METADATA),'publisher-tree-original-metadata')
    return tree_guards.check_tree_composition(root,values['executable'],values['metadata_head'],base,
        {path:files[name] for name,path in METADATA.items()})

def _tree_source(root,executable):
    relative='tools/ci/operator_flow_tree_guards.py';path=root/relative
    require(type(tree_guards) is types.ModuleType
        and all(type(value) is str and Path(value)==path and Path(value).is_absolute()
            for value in (getattr(tree_guards,'__file__',None),getattr(getattr(tree_guards,'__spec__',None),'origin',None))),
        'publisher-tree-source-origin')
    raw=_source_bytes(path);ref=executable+':'+relative
    size=git(root,'cat-file','-s',ref).decode().strip()
    require(re.fullmatch('[1-9][0-9]{0,7}',size) and int(size)<=LIMIT,'publisher-tree-source-size')
    committed=git(root,'show',ref)
    require(len(committed)==int(size) and raw==committed,'publisher-tree-source-bytes')
    return hashlib.sha256(raw).hexdigest()

def preflight_publication(executable_root,metadata_root,trust_path,*,reviewer_run_id,reviewer_job_id,
        pr_number,base,tested_merge,values):
    require(type(values) is dict and set(values)==set(SCALARS),'publisher-independent-values')
    _independent_expectations(**values)
    executable_root=Path(executable_root);metadata_root=Path(metadata_root)
    clean_root(executable_root);clean_root(metadata_root)
    require(not executable_root.is_relative_to(metadata_root) and not metadata_root.is_relative_to(executable_root),
        'publisher-independent-prepared-checkouts')
    for root,head in ((executable_root,values['executable']),(metadata_root,values['metadata_head'])):
        require(not (root/'.git/commondir').exists() and not (root/'.git/objects/info/http-alternates').exists()
            and git(root,'rev-parse','HEAD').decode().strip()==head,'publisher-prepared-E-M')
    source=_source_snapshot(executable_root,values['executable'])
    tree_source=_tree_source(executable_root,values['executable'])
    _main_identity(_GitHubAPI().request('GET','/repos/'+REPOSITORY+'/git/ref/heads/main'),base)
    materials=_public_materials(executable_root,metadata_root,trust_path,values)
    candidate,requests,observed=read_reviewed_publication(executable_root,reviewer_run_id=reviewer_run_id,
        reviewer_job_id=reviewer_job_id,pr_number=pr_number,base=base,tested_merge=tested_merge,values=values)
    files=_metadata_files(candidate,values)
    check_metadata(metadata_root,values,files)
    tree=_publication_tree(metadata_root,values,base,files)
    order=WorkOrder.load(metadata_root/'tests/fixtures/p5_public/human-clean-control/work-order.json')
    policy=ExecutionPolicy.load(metadata_root/(PREFIX+'execution-policy.json'))
    admission=FactoryModelAdmission.from_external_trust(metadata_root,PREFIX+'plan.json',PREFIX+'proof.json',
        PREFIX+'contract.json',trust_path)
    review=verify_human_drill_plan(admission,order,policy)
    check_native_review(values,review)
    plan=admission._committed_json(PREFIX+'plan.json')
    runtime=admission.verify_runtime(order,source_root=metadata_root,
        input_paths={key:metadata_root/row['path'] for key,row in plan['bound_inputs'].items()},policy=policy)
    require(plan['executable_commit']==values['executable'] and runtime['executable_commit']==values['metadata_head'],
        'publisher-native-E-M')
    api=_GitHubAPI()
    expected={k:observed[k] for k in ('run','job','pr','executable','base','tested_merge')}
    service={k:v for k,v in observed.items() if k not in ('log_sha256','identity','producer')}
    require(_snapshot(api,expected)==service,'publisher-reviewer-changed')
    handoff={k:values[k] for k in ('executable','producer_run_id','artifact_id','archive_sha256')}
    require(_original_producer(api,handoff)==observed['producer'],'publisher-producer-changed')
    check_metadata(metadata_root,values,files)
    require(_public_materials(executable_root,metadata_root,trust_path,values)==materials,'publisher-public-trust-changed')
    require(verify_human_drill_plan(admission,order,policy)==review,'publisher-current-native-trust-changed')
    require(_source_snapshot(executable_root,values['executable'])==source,'publisher-source-changed')
    require(_tree_source(executable_root,values['executable'])==tree_source,'publisher-tree-source-changed')
    require(_publication_tree(metadata_root,values,base,files)==tree,'publisher-tree-changed')
    _main_identity(api.request('GET','/repos/'+REPOSITORY+'/git/ref/heads/main'),base)
    # Native proof verification is not controller admission. Original false
    # publication flags stay false; exact full guards and approval remain owed.
    return candidate,requests,observed
