"""CI-only full Git tree and actual merge checks on the independent clone.

The caller supplies a separately reviewed expected main commit. Original GET
reads check current main; these are observations, never approval. This is only
one part of the required publication guards. No remote mutation, signer, nonce,
protected-history exception, or original-checkout operation exists here.
"""
from hashlib import sha256
from pathlib import Path
import os,re,subprocess
from tools.ci.operator_flow_consumer import clean_root
from tools.ci.operator_flow_metadata import LIMITS,object_id,require
from tools.ci.operator_flow_native_inputs import REPOSITORY

def current_main(expected):
    require(os.environ.get('GITHUB_ACTIONS')=='true'
        and os.environ.get('GITHUB_REPOSITORY')==REPOSITORY
        and os.environ.get('GITHUB_JOB')=='operator-producer','tree-main-producer-ci-only')
    require(type(expected) is str and re.fullmatch('[0-9a-f]{40}',expected),'tree-exact-main-required')
    from lightyear_execution.tower_drill_reservation import _GitHubAPI
    row=_GitHubAPI().request('GET','/repos/'+REPOSITORY+'/git/ref/heads/main')
    require(type(row) is dict and row.get('ref')=='refs/heads/main'
        and type(row.get('object')) is dict and row['object'].get('type')=='commit'
        and row['object'].get('sha')==expected,'tree-current-main-changed')
    return expected

def check_tree_composition(root,executable,head,main,metadata=None):
    require(os.environ.get('GITHUB_ACTIONS')=='true','tree-check-ci-only')
    require(all(type(x) is str and re.fullmatch('[0-9a-f]{40}',x) for x in (executable,head,main)),
        'tree-exact-commits-required')
    root=Path(root);temp=Path(os.environ['RUNNER_TEMP']).resolve(strict=True)
    workspace=Path(os.environ['GITHUB_WORKSPACE']).resolve(strict=True)
    require(root.is_absolute() and root.is_relative_to(temp) and root!=temp
        and root!=workspace and not root.is_relative_to(workspace),'tree-independent-temporary-clone')
    return _checked_tree_composition(root,executable,head,main,metadata)

def _checked_tree_composition(root,executable,head,main,metadata):
    """Original complete-tree/actual-merge kernel, not an environment guard.

    CI entry retains its original checks. Actual-host caller must supply its
    independently prepared clone, live originals, native authentication and
    complete guards. This kernel never grants publication permission.
    """
    clean_root(root)
    require(not (root/'.git/objects/info/http-alternates').exists(),'tree-no-http-alternates')
    def git(*args):
        result=subprocess.run(['git','--no-optional-locks','-C',str(root),*args],capture_output=True,timeout=60)
        require(result.returncode==0,'tree-git-or-merge-refused')
        return result.stdout
    require(git('rev-parse','HEAD').decode().strip()==head,'tree-exact-checked-out-head')
    for commit in (executable,head,main):
        require(git('cat-file','-t',commit).strip()==b'commit','tree-commit-type')
    def inventory(commit):
        # Keep raw path bytes: comparison covers every mode/type/blob and does
        # not silently ignore unusual filenames, deletions, links or gitlinks.
        raw=git('ls-tree','-rz','--full-tree',commit)
        require(len(raw)<=32*1024*1024,'tree-inventory-size')
        rows={}
        for item in raw.split(b'\0'):
            if not item:continue
            fields,path=item.split(b'\t',1)
            require(path not in rows,'tree-duplicate-path')
            rows[path]=fields
        return rows,sha256(raw).hexdigest()
    before,before_hash=inventory(executable);expected=dict(before)
    if metadata is None:
        require(head==executable,'tree-presign-exact-E')
    else:
        require(type(metadata) is dict and set(metadata)==set(LIMITS)
            and all(type(v) is bytes and 0<len(v)<=LIMITS[k] for k,v in metadata.items()),'tree-three-original-metadata-bytes')
        require(git('rev-list','--parents','-n','1',head).decode().split()==[head,executable],
            'tree-sole-parent-E')
        for path,raw in metadata.items():
            encoded=path.encode('ascii')
            require(encoded not in before,'tree-existing-metadata-refused')
            expected[encoded]=('100644 blob '+object_id('blob',raw)).encode('ascii')
    actual,actual_hash=inventory(head)
    require(actual==expected,'tree-complete-inventory-mismatch')
    tree=git('rev-parse',head+'^{tree}').decode().strip()
    # Git can write merge objects, exclusively in this independent CI clone.
    # A conflict or a clean merge that adds main changes both refuse. Source E
    # and the sealed wrapper checkout are never changed by this operation.
    merged=git('merge-tree','--write-tree',main,head).decode().strip()
    require(re.fullmatch('[0-9a-f]{40}',merged) and merged==tree,'tree-actual-main-merge-differs')
    clean_root(root)
    require(git('rev-parse','HEAD').decode().strip()==head,'tree-head-changed')
    return dict(executable=executable,metadata_head=head,expected_main=main,tree=tree,actual_merge_tree=merged,
        executable_inventory_sha256=before_hash,candidate_inventory_sha256=actual_hash,
        full_tree_and_merge_checked=True,full_publication_guards_passed=False,publication_authorized=False)
