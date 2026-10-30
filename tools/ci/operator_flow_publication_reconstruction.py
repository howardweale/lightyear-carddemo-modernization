"""Reconstruct original handoff metadata objects in memory; no publisher.

Caller owes authenticated original handoff, independently reviewed E/M/epoch,
native proof/current trust, full fresh guards and exact publication authority.
This function only checks byte/summary consistency, with read-only local Git.
It never creates objects, refs, files, signatures, reservations or API requests.
"""
from hashlib import sha256
from pathlib import Path
import re,subprocess
from tools.ci.operator_flow_handoff import LIMITS,strict_json
from tools.ci.operator_flow_metadata import PREFIX,prepare_candidate,require
from tools.ci.operator_flow_publication_objects import object_requests


def reconstruct_publication_objects(root,files,*,expected_executable,expected_candidate,commit_epoch):
    require(all(type(v) is str and re.fullmatch('[0-9a-f]{40}',v)
        for v in (expected_executable,expected_candidate)),'reconstruction-independent-heads')
    require(type(commit_epoch) is int and 1<=commit_epoch<10**11,'reconstruction-independent-epoch')
    require(type(files) is dict and set(files)==set(LIMITS)
        and all(type(raw) is bytes and 0<len(raw)<=LIMITS[name] for name,raw in files.items()),
        'reconstruction-exact-bounded-handoff')
    report=strict_json(files['producer.json'])
    require(type(report) is dict,'reconstruction-report')
    hashes=report.get('public_handoff_hashes')
    require(type(hashes) is dict and set(hashes)==set(LIMITS)-{'producer.json'}
        and all(hashes[name]==sha256(files[name]).hexdigest() for name in hashes),
        'reconstruction-original-byte-hashes')
    summary=report.get('metadata_candidate')
    require(type(summary) is dict and summary.get('parent')==expected_executable
        and summary.get('commit')==expected_candidate
        and type(summary.get('commit_epoch')) is int and summary['commit_epoch']==commit_epoch,
        'reconstruction-reported-heads-epoch')
    metadata={PREFIX+name:files[name] for name in ('plan.json','contract.json','proof.json')}
    # Original builder enforces CI-only, exact clean E, independent source paths,
    # three NEW metadata paths and native read-only object hash checks.
    candidate=prepare_candidate(root,expected_executable,metadata,commit_epoch)
    require(candidate['commit']==expected_candidate,'reconstruction-candidate-mismatch')
    for field in ('base_tree','tree','files'):
        require(summary.get(field)==candidate[field],'reconstruction-candidate-summary')
    root=Path(root)
    def git(*args):
        result=subprocess.run(['git','--no-optional-locks','-C',str(root),*args],
            capture_output=True,timeout=45)
        require(result.returncode==0,'reconstruction-read-only-git')
        return result.stdout
    base={}
    for prefix in ('','docs/','docs/factory/',PREFIX):
        revision=expected_executable+(':'+prefix.rstrip('/') if prefix else '^{tree}')
        oid=git('rev-parse',revision).decode('ascii').strip()
        require(re.fullmatch('[0-9a-f]{40}',oid),'reconstruction-base-tree-id')
        size=git('cat-file','-s',oid).decode('ascii').strip()
        require(size.isdecimal() and 0<int(size)<=2*1024*1024,'reconstruction-base-tree-size')
        raw=git('cat-file','tree',oid)
        require(len(raw)==int(size),'reconstruction-base-tree-bytes')
        base[prefix]=(oid,raw)
    requests=object_requests(candidate,metadata,base,
        expected_executable=expected_executable,expected_candidate=expected_candidate)
    require(git('rev-parse','HEAD').decode().strip()==expected_executable
        and not git('status','--porcelain=v1','--untracked-files=all'),'reconstruction-final-clean-E')
    # Preserve the original builder's false authority/readiness flags. A report
    # asserting native verification cannot convert this reconstruction to proof.
    return candidate,requests
