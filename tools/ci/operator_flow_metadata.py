"""Deterministic CI-only metadata object construction; NEVER publication authority.

Input provenance, native proof/current trust, complete CI and all fresh guards
must be verified by the full publication route. This module constructs objects
in memory only. It never writes Git objects, index, refs or worktree files,
calls a service, signs, sets variables, or invokes a consumer. No push entry.
"""
from hashlib import sha1,sha256
import os,re,subprocess
from pathlib import Path

PREFIX='docs/factory/p5-human-clean-control/'
LIMITS={PREFIX+'plan.json':1048576,PREFIX+'contract.json':1048576,PREFIX+'proof.json':2097152}
MESSAGE='Bind disposable CI operator rehearsal metadata\n\nExact public fixture plan, contract and proof only; no real-case authority.\n'

def require(value,reason):
    if not value:raise ValueError(reason)

def object_id(kind,body):
    require(kind in ('blob','tree','commit') and type(body) is bytes,'metadata-object-shape')
    return sha1(kind.encode()+b' '+str(len(body)).encode()+b'\0'+body).hexdigest()

def prepare_candidate(root,executable,metadata,commit_epoch):
    require(os.environ.get('GITHUB_ACTIONS')=='true','metadata-builder-ci-only')
    require(type(executable) is str and re.fullmatch('[0-9a-f]{40}',executable),'metadata-executable')
    require(type(commit_epoch) is int and 1<=commit_epoch<10**11,'metadata-prepared-commit-epoch')
    require(type(metadata) is dict and set(metadata)==set(LIMITS),'metadata-exact-three-paths')
    require(all(type(raw) is bytes and 0<len(raw)<=LIMITS[path] for path,raw in metadata.items()),'metadata-bounded-original-bytes')
    root=Path(root)
    require(root.is_absolute() and root.resolve(strict=True)==root,'metadata-absolute-root')
    for path in (root,*root.parents):
        require(not path.is_symlink() and not getattr(path.lstat(),'st_file_attributes',0)&0x400
            and 'onedrive' not in str(path).lower(),'metadata-source-path')
    require((root/'.git').is_dir() and not (root/'.git').is_symlink()
        and not (root/'.git/commondir').exists()
        and not (root/'.git/objects/info/alternates').exists()
        and not (root/'.git/objects/info/http-alternates').exists(),'metadata-independent-git')
    def git(*args,data=None):
        completed=subprocess.run(['git','--no-optional-locks','-C',str(root),*args],input=data,capture_output=True,timeout=45)
        require(completed.returncode==0,'metadata-read-only-git-failed')
        return completed.stdout
    def clean():
        require(git('rev-parse','HEAD').decode().strip()==executable
            and not git('status','--porcelain=v1','--untracked-files=all'),'metadata-exact-clean-E')
    clean();objects={};changes=[]
    def remember(kind,body):
        oid=object_id(kind,body)
        # No -w: Git independently validates encoding/hash without storing it.
        require(git('hash-object','-t',kind,'--stdin',data=body).decode().strip()==oid,'metadata-object-encoding')
        require(oid not in objects or objects[oid]==(kind,body),'metadata-object-collision')
        objects[oid]=(kind,body)
        return oid
    blobs={path:remember('blob',raw) for path,raw in metadata.items()}
    def tree(oid,prefix=''):
        raw=git('ls-tree','-z',oid)
        require(len(raw)<=2*1024*1024,'metadata-tree-size')
        entries={}
        for row in raw.split(b'\0'):
            if not row:continue
            meta,name=row.split(b'\t',1);mode,kind,child=meta.decode('ascii').split()
            require(name not in entries,'metadata-duplicate-tree-entry')
            entries[name]=(mode.lstrip('0'),kind,child)
        for path,blob in blobs.items():
            if not path.startswith(prefix):continue
            suffix=path[len(prefix):]
            if '/' not in suffix:
                name=suffix.encode()
                require(name not in entries,'metadata-retained-path-already-exists')
                entries[name]=('100644','blob',blob)
                changes.append(dict(path=path,before=None,git_blob=blob,sha256=sha256(metadata[path]).hexdigest()))
        for name,(mode,kind,child) in list(entries.items()):
            # Only ancestors of the three fixed ASCII paths need decoding.
            path_bytes=prefix.encode()+name+b'/'
            if any(path.encode().startswith(path_bytes) for path in blobs):
                require(kind=='tree' and mode=='40000','metadata-ancestor-not-directory')
                entries[name]=(mode,kind,tree(child,path_bytes.decode('ascii')))
        ordered=sorted(entries.items(),key=lambda row:row[0]+(b'/' if row[1][1]=='tree' else b''))
        body=b''.join(mode.encode()+b' '+name+b'\0'+bytes.fromhex(child) for name,(mode,kind,child) in ordered)
        return remember('tree',body)
    base_tree=git('rev-parse',executable+'^{tree}').decode().strip()
    candidate_tree=tree(base_tree)
    require(len(changes)==3 and {row['path'] for row in changes}==set(LIMITS),'metadata-existing-parent-paths-required')
    identity='Codex <codex@openai.com> '+str(commit_epoch)+' +0000'
    commit=('tree '+candidate_tree+'\nparent '+executable+'\nauthor '+identity+'\ncommitter '+identity+'\n\n'+MESSAGE).encode()
    candidate=remember('commit',commit);clean()
    return dict(parent=executable,base_tree=base_tree,tree=candidate_tree,commit=candidate,
        commit_epoch=commit_epoch,files=sorted(changes,key=lambda row:row['path']),objects=objects,
        native_proof_verified=False,full_guards_passed=False,publish_ready=False,publication_authorized=False,
        full_route_passed=False,real_pack_ready=False)
