"""CI patch producer for an exact unfenced Java scope; no write-back or merge authority."""
import argparse
from hashlib import sha256
import json
from pathlib import Path,PurePosixPath
import subprocess
from tools.check_java_quality_fence import derive, safe_path, violations
import xml.etree.ElementTree as ET

SCOPE=Path('tools/java-format/unfenced-scope.json')
def git(root,*args):
    return subprocess.run(['git','-C',str(root),*args],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE).stdout
def inventory(root):
    paths=git(root,'ls-files','-z').decode().split('\0')
    result={}
    for name in filter(None,paths):
        path=root/name
        if path.is_symlink() or not path.is_file():raise ValueError('format-nonregular-tracked-file')
        result[name]=sha256(path.read_bytes()).hexdigest()
    return result
def selected(scope):
    rows=scope['selected'];names=[r['path'] for r in rows]
    if len(names)!=len(set(names)) or not names:raise ValueError('format-scope-inventory')
    for name in names:
        safe_path(name)
        p=PurePosixPath(name)
        if p.is_absolute() or '..' in p.parts or not name.startswith('factory/carddemo-web/service/src/main/') or not name.endswith('.java'):
            raise ValueError('format-unsafe-path')
        if '/authorization/' in name or 'Authorization' in p.name or p.name=='SourceEdits.java' or any(x in name.upper() for x in ('COPAU00','COPAU01','COPAUS2C')):raise ValueError('format-reserved-source')
    return names
def verify(before,after,allowed):
    if set(before)!=set(after):raise ValueError('format-inventory-changed')
    changed=sorted(p for p in before if before[p]!=after[p])
    if set(changed)-set(allowed):raise ValueError('format-outside-scope')
    return changed
def combined_fence(read, names):
    fence=derive(read,names)
    plan_path='docs/factory/posttran-phase2-plan-2026-10-16.json'
    plan=json.loads(read(plan_path))
    if not isinstance(plan['bound_files'],dict) or len(plan['bound_files'])!=182 or not isinstance(plan['candidate_files'],dict) or len(plan['candidate_files'])!=2:
        raise ValueError('format-posttran-inventory')
    extra={safe_path(p) for p in (*plan['bound_files'],*plan['candidate_files'])}
    extra.update(p for p in names if p.startswith(('docs/factory/posttran-','spec/mainframe/posttran-independent/')))
    fence['paths']=sorted(set(fence['paths'])|extra|{plan_path})
    return fence

def check_scope_fence(root, base, names):
    base=git(root,'rev-parse','--verify',base+'^{commit}').decode().strip()
    tracked=git(root,'ls-tree','-r','--name-only',base).decode().splitlines()
    fence=combined_fence(lambda p:git(root,'show',base+':'+p),tracked)
    if violations(fence,names):raise ValueError('format-fenced-selection')
    return dict(base=base,sha256=sha256(json.dumps(fence,sort_keys=True,separators=(',',':')).encode()).hexdigest(),paths=len(fence['paths']),prefixes=len(fence['prefixes']))

def require_clean(changed):
    if changed:raise ValueError("format-not-clean")

def main():
    p=argparse.ArgumentParser();p.add_argument('phase',choices=('capture','report'));p.add_argument('--root',type=Path,default=Path('.'));p.add_argument('--out',type=Path,required=True);p.add_argument('--base',required=True);p.add_argument('--require-clean',action='store_true');a=p.parse_args()
    root=a.root.resolve();scope=json.loads((root/SCOPE).read_bytes());names=selected(scope)
    fence=check_scope_fence(root,a.base,names)
    ns={'m':'http://maven.apache.org/POM/4.0.0'};pom=ET.parse(root/'java-format-unfenced.pom.xml').getroot()
    if [x.text for x in pom.findall('.//m:java/m:includes/m:include',ns)]!=names:raise ValueError('format-pom-scope')
    current=inventory(root);a.out.mkdir(parents=True,exist_ok=True)
    if a.phase=='capture':
        for row in scope['selected']:
            original=git(root,'show',scope['base_commit']+':'+row['path'])
            if sha256(original).hexdigest()!=row['sha256'] or current[row['path']]!=row['sha256']:raise ValueError('format-source-changed')
        snapshot=dict(fence=fence,head=git(root,'rev-parse','HEAD').decode().strip(),files=current,scope_sha256=sha256((root/SCOPE).read_bytes()).hexdigest())
        with (a.out/'before.json').open('x',encoding='utf-8') as f:json.dump(snapshot,f,indent=2)
        return
    before=json.loads((a.out/'before.json').read_bytes())
    if before['fence']!=fence:raise ValueError('format-fence-changed')
    if before['head']!=git(root,'rev-parse','HEAD').decode().strip():raise ValueError('format-head-changed')
    if before['scope_sha256']!=sha256((root/SCOPE).read_bytes()).hexdigest():raise ValueError('format-scope-changed')
    changed=verify(before['files'],current,names)
    if git(root,'diff','--summary','HEAD','--').strip():raise ValueError('format-mode-or-inventory-change')
    patch=git(root,'diff','--binary','--no-ext-diff','HEAD','--',*names)
    if bool(changed)!=bool(patch):raise ValueError('format-patch-mismatch')
    (a.out/'format.patch').write_bytes(patch)
    record=dict(fence=fence,idiomatic_index_change=0,schema='java-unfenced-format-patch/1',head=before['head'],base_commit=scope['base_commit'],scope_sha256=before['scope_sha256'],
        patch_sha256=sha256(patch).hexdigest(),patch_bytes=len(patch),changed_files=len(changed),
        files=[dict(path=p,before_sha256=before['files'][p],after_sha256=current[p]) for p in changed],
        proof_complete=False,merge_authorized=False,stage='review-patch-before-format-only-commit')
    (a.out/'manifest.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    if a.require_clean:require_clean(changed)
if __name__=='__main__':main()
