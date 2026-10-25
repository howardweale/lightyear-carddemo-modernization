"""CI patch producer for the held formatting draft; no write-back or merge authority."""
import argparse
from hashlib import sha256
import json
from pathlib import Path,PurePosixPath
import subprocess
import xml.etree.ElementTree as ET

SCOPE=Path('tools/java-format/fenced-scope.json')
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
        p=PurePosixPath(name)
        if p.is_absolute() or '..' in p.parts or not name.startswith('factory/carddemo-web/service/src/') or not name.endswith('.java'):
            raise ValueError('format-unsafe-path')
        if '/authorization/' in name or 'Authorization' in p.name or p.name=='SourceEdits.java':raise ValueError('format-reserved-source')
    return names
def verify(before,after,allowed):
    if set(before)!=set(after):raise ValueError('format-inventory-changed')
    changed=sorted(p for p in before if before[p]!=after[p])
    if set(changed)-set(allowed):raise ValueError('format-outside-scope')
    return changed
def main():
    p=argparse.ArgumentParser();p.add_argument('phase',choices=('capture','report'));p.add_argument('--root',type=Path,default=Path('.'));p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    root=a.root.resolve();scope=json.loads((root/SCOPE).read_bytes());names=selected(scope)
    ns={'m':'http://maven.apache.org/POM/4.0.0'};pom=ET.parse(root/'java-format-fenced.pom.xml').getroot()
    if [x.text for x in pom.findall('.//m:java/m:includes/m:include',ns)]!=names:raise ValueError('format-pom-scope')
    current=inventory(root);a.out.mkdir(parents=True,exist_ok=True)
    if a.phase=='capture':
        for row in scope['selected']:
            original=git(root,'show',scope['base_commit']+':'+row['path'])
            if sha256(original).hexdigest()!=row['sha256'] or current[row['path']]!=row['sha256']:raise ValueError('format-source-changed')
        snapshot=dict(head=git(root,'rev-parse','HEAD').decode().strip(),files=current,scope_sha256=sha256((root/SCOPE).read_bytes()).hexdigest())
        with (a.out/'before.json').open('x',encoding='utf-8') as f:json.dump(snapshot,f,indent=2)
        return
    before=json.loads((a.out/'before.json').read_bytes())
    if before['head']!=git(root,'rev-parse','HEAD').decode().strip():raise ValueError('format-head-changed')
    if before['scope_sha256']!=sha256((root/SCOPE).read_bytes()).hexdigest():raise ValueError('format-scope-changed')
    changed=verify(before['files'],current,names)
    patch=git(root,'diff','--binary','--no-ext-diff','HEAD','--',*names)
    if bool(changed)!=bool(patch):raise ValueError('format-patch-mismatch')
    (a.out/'format.patch').write_bytes(patch)
    record=dict(schema='java-fenced-format-patch/1',head=before['head'],base_commit=scope['base_commit'],scope_sha256=before['scope_sha256'],
        patch_sha256=sha256(patch).hexdigest(),patch_bytes=len(patch),changed_files=len(changed),
        files=[dict(path=p,before_sha256=before['files'][p],after_sha256=current[p]) for p in changed],
        proof_complete=False,merge_authorized=False,stage='review-patch-before-format-only-commit')
    (a.out/'manifest.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
if __name__=='__main__':main()
