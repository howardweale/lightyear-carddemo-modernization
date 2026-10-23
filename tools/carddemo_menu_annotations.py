"""Exact menu source annotations; no new behavior or equivalence claim."""
import argparse,json,re
from hashlib import sha256
from pathlib import Path
SCOPE='spec/modernization/carddemo-screens/menu-annotations-scope.json'
def digest(text):return sha256(text.replace('\r\n','\n').encode()).hexdigest()
def check_scope(root,scope=None):
    root=Path(root);scope=scope or json.loads((root/SCOPE).read_bytes())
    if scope['annotations_only'] is not True or scope['whole_screen_idiomatic'] is not False or scope['independent_full_slice_required'] is not True:raise ValueError('menu-claim')
    source=scope['source']
    if source['path']!='spec/modernization/carddemo-screens/upstream/app/cbl/COMEN01C.cbl':raise ValueError('menu-source-path')
    raw=(root/source['path']).read_text();lines=raw.splitlines()
    if digest(raw)!=source['sha256']:raise ValueError('menu-source-hash')
    labels=[dict(name=line[7:72].strip()[:-1],line=i+1) for i,line in enumerate(lines)
        if len(line)>7 and line[6]!='*' and line[7]!=' ' and re.fullmatch('[A-Z0-9][A-Z0-9-]*[.]',line[7:72].strip())]
    if len(labels)!=7 or labels!=source['inventory']:raise ValueError('menu-inventory')
    expected=scope['bindings']
    if len(expected)!=7 or {b['paragraph'] for b in expected}!={p['name'] for p in labels}:raise ValueError('menu-bindings')
    ranges={}
    for i,item in enumerate(labels):
        first=item['line'];stop=labels[i+1]['line']-1 if i+1<len(labels) else len(lines)
        active=[n for n in range(first,stop+1) if len(lines[n-1])>7
                and lines[n-1][6] not in ('*','/') and lines[n-1][7:72].strip()]
        ranges[item['name']]=(first,active[-1])
    observed=[]
    for path,bound_hash in scope['executable_sha256'].items():
        if path not in ('factory/carddemo-web/service/src/main/java/ai/lightyear/carddemo/MenuService.java','factory/carddemo-web/service/src/main/java/ai/lightyear/carddemo/ScreenFrame.java'):raise ValueError('menu-java-path')
        code=(root/path).read_text()
        for match in re.finditer(r'@CobolSource\(program="COMEN01C", paragraph="([^"]+)", lines="([^"]+)"\)',code):
            paragraph,span=match.groups();first,last=map(int,span.split('-'))
            if (first,last)!=ranges.get(paragraph):raise ValueError('menu-range')
            tail=re.sub(r'^\s*(?:@CobolSource\([^\n]+\)\s*)+','',code[match.end():])
            method=re.match(r'\s*(?:(?:public|private|protected|static|final)\s+)*[\w<>?,.\[\]]+\s+(\w+)\s*\(',tail)
            if not method:raise ValueError('menu-method')
            observed.append(dict(paragraph=paragraph,lines=span,file=path,method=method[1],source_span_sha256=digest('\n'.join(lines[first-1:last])+'\n')))
        plain=re.sub(r'^    @CobolSource\(program="COMEN01C",[^\n]+\n','',code,flags=re.M)
        if digest(plain)!=bound_hash:raise ValueError('menu-executable-change')
    if sorted(observed,key=lambda b:b['paragraph'])!=sorted(expected,key=lambda b:b['paragraph']):raise ValueError('menu-binding-mismatch')
    return dict(annotations=7,annotations_only=True,whole_screen_idiomatic=False,independent_full_slice_required=True)
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=Path('.'));p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    value=check_scope(a.root);a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(value,indent=2)+'\n');return 0
if __name__=='__main__':raise SystemExit(main())
