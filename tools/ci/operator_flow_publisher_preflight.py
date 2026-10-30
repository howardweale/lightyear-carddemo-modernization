"""Read-only external publication preflight; no remote publisher or authority.

Requires separately prepared independent E/M and public trust. Historical
review success cannot replace original current native proof/trust/runtime
verification. No clock, verifier, API, old-claim or context injection.
"""
import hashlib,json,re,sys,types
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
from tools import check_java_quality_fence as java_fence
from tools import check_intcalc_m1_triage as posttran
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

def _expected_protection(protection_sha256,rules_sha256):
    require(all(type(x) is str and re.fullmatch('[0-9a-f]{64}',x)
        for x in (protection_sha256,rules_sha256)),'publisher-independent-protection-digests')
    return protection_sha256,rules_sha256

def _protection_digest(value):
    # Canonical JSON preserves Boolean/integer and list-order distinctions.
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),
        ensure_ascii=False,allow_nan=False).encode('utf-8')).hexdigest()

def _check_repository_protection(protection,rules,protection_sha256,rules_sha256):
    expected=_expected_protection(protection_sha256,rules_sha256)
    require(type(protection) is dict and type(rules) is list,'publisher-native-protection-shapes')
    actual=(_protection_digest(protection),_protection_digest(rules))
    require(actual==expected,'publisher-main-protection-or-rules-changed')
    # Relationship check only: expected digests must be independently reviewed.
    return actual

def _protection_snapshot(protection_sha256,rules_sha256):
    _expected_protection(protection_sha256,rules_sha256)
    api=_GitHubAPI()
    protection=api.request('GET','/repos/'+REPOSITORY+'/branches/main/protection')
    rules=api.request('GET','/repos/'+REPOSITORY+'/rules/branches/main')
    return _check_repository_protection(protection,rules,protection_sha256,rules_sha256)

def _fence_source(root,executable,base):
    relative='tools/check_java_quality_fence.py';path=root/relative
    require(type(java_fence) is types.ModuleType
        and all(type(value) is str and Path(value)==path and Path(value).is_absolute()
            for value in (getattr(java_fence,'__file__',None),getattr(getattr(java_fence,'__spec__',None),'origin',None))),
        'publisher-fence-source-origin')
    raw=_source_bytes(path)
    for revision in (executable,base):
        require(type(revision) is str and re.fullmatch('[0-9a-f]{40}',revision),'publisher-fence-source-revision')
        ref=revision+':'+relative;size=git(root,'cat-file','-s',ref).decode().strip()
        require(re.fullmatch('[1-9][0-9]{0,7}',size) and int(size)<=LIMIT,'publisher-fence-source-size')
        committed=git(root,'show',ref)
        require(len(committed)==int(size) and raw==committed,'publisher-fence-source-bytes')
    return hashlib.sha256(raw).hexdigest()

def _raw_fence(root,base,head,expected_sha256):
    require(type(expected_sha256) is str and re.fullmatch('[0-9a-f]{64}',expected_sha256),
        'publisher-independent-raw-fence-digest')
    require(all(type(value) is str and re.fullmatch('[0-9a-f]{40}',value) for value in (base,head)),
        'publisher-raw-fence-revisions')
    report=java_fence.inspect(root,base,head)
    require(report['schema']=='java-quality-fence/1' and report['base']==base and report['head']==head
        and report['fence_sha256']==expected_sha256,'publisher-raw-fence-binding')
    require(report['automatic_expiry'] is False and report['blocked_paths']==[]
        and report['merge_permitted'] is True,'publisher-raw-fence-blocked')
    # Original report remains a path check, never publication/merge authority.
    return report

# Five public paths retained by the original 192-path preservation record,
# beyond the original current-plan derivation. No caller-supplied omission list.
POSTTRAN_RETAINED=(
    '.github/workflows/posttran-key-change-proof.yml',
    '.github/workflows/posttran-review.yml',
    'docs/factory/factory-authority.public.pem',
    'tests/test_posttran_review.py',
    'tools/check_posttran_key_change.py',
)
POSTTRAN_HISTORY_ANCHOR='f267fc9ee8d1329529debf4b5edd72bb026b63a5'
POSTTRAN_APPROVED_ARCHIVE_MAIN='253fb9daf389b5f2b853918cb62fc3eb4a4f7e0c'
POSTTRAN_APPROVED_ARCHIVE_PATHS=frozenset((
    '.github/workflows/posttran-key-change-proof.yml','tools/check_posttran_key_change.py'))

def _posttran_inventory(root,base,expected_sha256):
    require(type(expected_sha256) is str and re.fullmatch('[0-9a-f]{64}',expected_sha256),
        'publisher-independent-posttran-digest')
    require(type(base) is str and re.fullmatch('[0-9a-f]{40}',base),'publisher-posttran-base')
    ref=base+':'+posttran.PLAN;size=git(root,'cat-file','-s',ref).decode().strip()
    require(re.fullmatch('[1-9][0-9]{0,7}',size) and int(size)<=LIMIT,'publisher-posttran-plan-size')
    raw=git(root,'show',ref);require(len(raw)==int(size),'publisher-posttran-plan-size')
    names=git(root,'ls-tree','-rz','--name-only',base).decode('utf-8').split('\0')
    require(names[-1]=='','publisher-posttran-tree-termination')
    protected=posttran.posttran_paths(json.loads(raw),names[:-1])|set(POSTTRAN_RETAINED)
    ordered=sorted(protected)
    require(len(ordered)==235 and hashlib.sha256(json.dumps(ordered,separators=(',',':')).encode()).hexdigest()
        ==expected_sha256,'publisher-posttran-exact-inventory')
    return frozenset(protected)

def _protected_history(root,base,head,protected):
    require(all(type(x) is str and re.fullmatch('[0-9a-f]{40}',x) for x in (base,head)),
        'publisher-protected-history-revisions')
    require(type(protected) is frozenset and protected and all(type(x) is str and posttran.safe_path(x)==x for x in protected),
        'publisher-protected-history-paths')
    git(root,'merge-base','--is-ancestor',base,head)
    # Full history and per-parent merge diffs retain changes later reverted.
    raw=git(root,'log','--full-history','-m','--format=','--no-renames','--name-only','-z',base+'..'+head)
    touched=set(raw.decode('utf-8').split('\0'))-{''}
    endpoint=set(git(root,'diff','--no-renames','--name-only','-z',base,head).decode('utf-8').split('\0'))-{''}
    return frozenset(protected.intersection(touched|endpoint))

# Exact already-approved main-sync import; never a caller-supplied exemption.
POSTTRAN_APPROVED_SYNC='ca8b302737d6fb0924ec982320bc0fa89c1b434e'
POSTTRAN_APPROVED_SYNC_PARENT='9431fe67cf289fa19c817502d13f5bc01ef23283'

def _approved_sync_import(root,commit,parent,parents,protected,relevant):
    # Only these immutable edges import existing anchor/archive entries.
    # New commits with identical trees or messages receive no exemption.
    old_paths=POSTTRAN_APPROVED_ARCHIVE_PATHS|frozenset(
        'docs/factory/posttran-key-change-2026-10-23/'+name for name in
        ('README.md','amendment.json','authority.public.pem','seven-bindings-not-adopted.json','unsigned-request.json'))
    imports={
        (POSTTRAN_APPROVED_SYNC,POSTTRAN_APPROVED_SYNC_PARENT):
            ([POSTTRAN_APPROVED_SYNC_PARENT,POSTTRAN_APPROVED_ARCHIVE_MAIN],POSTTRAN_APPROVED_ARCHIVE_MAIN,POSTTRAN_APPROVED_ARCHIVE_PATHS),
        ('5f32004b1383385890335864d734a7653b066b52','f5190ccac950803389552ea7d2b646611debe414'):
            (['f5190ccac950803389552ea7d2b646611debe414','929bff1dfb746ea27da5c302ebdb05be2d853389'],POSTTRAN_HISTORY_ANCHOR,old_paths),
        ('1d773a3841e933fbf03675f56183b56a59b28e62','aa3aa6988bbee28c87aa8089969076d1fb232f75'):
            ([POSTTRAN_HISTORY_ANCHOR,'aa3aa6988bbee28c87aa8089969076d1fb232f75'],POSTTRAN_HISTORY_ANCHOR,old_paths),
    }
    inherited=imports.get((commit,parent))
    if inherited is None:
        return False
    expected_parents,source,expected_paths=inherited
    require(parents==expected_parents,'publisher-approved-sync-parents')
    require(relevant==expected_paths and len(protected)==235
        and hashlib.sha256(json.dumps(sorted(protected),separators=(',',':')).encode()).hexdigest()
        =='ea2b22bfb7465d3dee5b0286d7770a60df4cf62869d3cb7f9c84c6708810d27d',
        'publisher-approved-sync-inventory')
    inventories=[]
    for revision in (source,commit):
        rows=git(root,'ls-tree','-rz',revision).decode('utf-8').split('\0')
        require(rows[-1]=='','publisher-approved-sync-tree-termination')
        inventory={}
        for row in rows[:-1]:
            entry,path=row.split('\t',1)
            require(path not in inventory,'publisher-approved-sync-duplicate-path')
            inventory[path]=entry
        require(protected<=inventory.keys(),'publisher-approved-sync-missing-path')
        inventories.append({path:inventory[path] for path in protected})
    require(inventories[0]==inventories[1],'publisher-approved-sync-original-blobs-modes')
    return True

def _provenance_protected_history(root,base,head,protected):
    # Preserve the original full-history/endpoint detector and its refusals.
    raw_changes=_protected_history(root,base,head,protected)
    if not raw_changes:
        return raw_changes
    remaining=set()
    for row in git(root,'rev-list','--parents',base+'..'+head).decode().splitlines():
        commit,*parents=row.split()
        require(parents and all(re.fullmatch('[0-9a-f]{40}',x) for x in [commit]+parents),
            'publisher-main-history-edge')
        for parent in parents:
            names=set(git(root,'diff','--no-renames','--name-only','-z',parent,commit).decode('utf-8').split('\0'))-{''}
            relevant=protected.intersection(names)
            if relevant and not _approved_sync_import(root,commit,parent,parents,protected,relevant):
                remaining.update(relevant)
    endpoint=set(git(root,'diff','--no-renames','--name-only','-z',base,head).decode('utf-8').split('\0'))-{''}
    remaining.update(protected.intersection(endpoint))
    return frozenset(remaining)

def _posttran_guard(executable_root,metadata_root,base,head,expected_sha256):
    relative='tools/check_intcalc_m1_triage.py';path=executable_root/relative
    require(type(posttran) is types.ModuleType
        and all(type(value) is str and Path(value)==path and Path(value).is_absolute()
            for value in (getattr(posttran,'__file__',None),getattr(getattr(posttran,'__spec__',None),'origin',None))),
        'publisher-posttran-source-origin')
    raw=_source_bytes(path)
    executable=git(executable_root,'rev-parse','HEAD').decode().strip()
    for revision in (executable,base):
        require(type(revision) is str and re.fullmatch('[0-9a-f]{40}',revision),'publisher-posttran-source-revision')
        ref=revision+':'+relative;size=git(metadata_root,'cat-file','-s',ref).decode().strip()
        require(re.fullmatch('[1-9][0-9]{0,7}',size) and int(size)<=LIMIT,'publisher-posttran-source-size')
        committed=git(metadata_root,'show',ref)
        require(len(committed)==int(size) and committed==raw,'publisher-posttran-trusted-source')
    protected=_posttran_inventory(metadata_root,base,expected_sha256)
    require(_provenance_protected_history(metadata_root,POSTTRAN_HISTORY_ANCHOR,POSTTRAN_APPROVED_ARCHIVE_MAIN,protected)
        ==POSTTRAN_APPROVED_ARCHIVE_PATHS,'publisher-posttran-approved-history')
    require(not _provenance_protected_history(metadata_root,POSTTRAN_APPROVED_ARCHIVE_MAIN,base,protected),
        'publisher-posttran-later-main-history')
    require(not _protected_history(metadata_root,base,head,protected),'publisher-posttran-candidate-history')
    return expected_sha256

def _native_current_review(metadata_root,trust_path,values):
    """Original native proof/runtime sequence; no admission or publication authority.

    Callers own exact prepared metadata, external current trust, source/host
    guards, original reviewer/producer provenance and operation approval.
    No caller verifier, clock, API, provider, context or cached proof accepted.
    """
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
    return order,policy,admission,review,plan,runtime


def preflight_publication(executable_root,metadata_root,trust_path,*,reviewer_run_id,reviewer_job_id,
        pr_number,base,tested_merge,values,expected_main_protection_sha256=None,expected_main_rules_sha256=None,expected_java_fence_sha256=None,expected_posttran_inventory_sha256=None):
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
    fence_source=_fence_source(executable_root,values['executable'],base)
    fence=_raw_fence(metadata_root,base,values['metadata_head'],expected_java_fence_sha256)
    posttran_guard=_posttran_guard(executable_root,metadata_root,base,values['metadata_head'],expected_posttran_inventory_sha256)
    protection=_protection_snapshot(expected_main_protection_sha256,expected_main_rules_sha256)
    _main_identity(_GitHubAPI().request('GET','/repos/'+REPOSITORY+'/git/ref/heads/main'),base)
    materials=_public_materials(executable_root,metadata_root,trust_path,values)
    candidate,requests,observed=read_reviewed_publication(executable_root,reviewer_run_id=reviewer_run_id,
        reviewer_job_id=reviewer_job_id,pr_number=pr_number,base=base,tested_merge=tested_merge,values=values)
    files=_metadata_files(candidate,values)
    check_metadata(metadata_root,values,files)
    tree=_publication_tree(metadata_root,values,base,files)
    order,policy,admission,review,plan,runtime=_native_current_review(metadata_root,trust_path,values)
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
    require(_protection_snapshot(expected_main_protection_sha256,expected_main_rules_sha256)==protection,
        'publisher-repeated-protection-changed')
    require(_fence_source(executable_root,values['executable'],base)==fence_source,'publisher-fence-source-changed')
    require(_raw_fence(metadata_root,base,values['metadata_head'],expected_java_fence_sha256)==fence,
        'publisher-raw-fence-changed')
    require(_posttran_guard(executable_root,metadata_root,base,values['metadata_head'],expected_posttran_inventory_sha256)
        ==posttran_guard,'publisher-posttran-history-changed')
    # Native proof verification is not controller admission. Original false
    # publication flags stay false; exact full guards and approval remain owed.
    return candidate,requests,observed
