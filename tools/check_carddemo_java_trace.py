"""Check structured source ranges and required rule coverage for the scoped Java."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re

SCOPE='spec/modernization/carddemo-screens/idiomatic-java-scope.json'
JAVA='factory/carddemo-web/service/src/main/java/ai/lightyear/carddemo'
METHOD=r'(?:public|private|protected)\s+(?:static\s+)?[\w<>., ?]+\s+(\w+)\s*\('
ANNOTATION=re.compile(r'@CobolSource\(program="([^"]+)", paragraph="([^"]+)", lines="(\d+)-(\d+)"\)\s*'+METHOD)


def check(root, scope_path=SCOPE):
    root=Path(root);scope=json.loads((root/scope_path).read_bytes())
    source=(root/scope['source']['path']).read_bytes().replace(b'\r\n',b'\n')
    if sha256(source).hexdigest()!=scope['source']['sha256']:raise ValueError('java-trace-source-hash')
    lines=source.decode().splitlines();mapped=set();methods=set();rows=[];loc=0
    for filename in scope['java_files']:
        text=(root/JAVA/filename).read_text(encoding='utf-8');loc+=sum(bool(line.strip()) for line in text.splitlines())
        if re.search(r'\bSourceEdits\b|\b(?:update_edits|view_render|auth_render)\b',text):
            raise ValueError('java-trace-statement-engine')
        annotated={m.group(5) for m in ANNOTATION.finditer(text)}
        declared=set(re.findall(METHOD,text))
        if declared!=annotated:raise ValueError('java-trace-unmapped-method:'+repr(declared^annotated))
        for match in ANNOTATION.finditer(text):
            program,paragraph,start,end,method=match.groups();start=int(start);end=int(end)
            if program!=scope['program'] or not 1<=start<=end<=len(lines):raise ValueError('java-trace-range')
            markers=[i+1 for i,line in enumerate(lines) if line[6:7]!='*' and line[7:72].strip()==paragraph+'.']
            if len(markers)!=1 or start<markers[0]:raise ValueError('java-trace-paragraph')
            # A method cannot claim another paragraph's implementation range.
            following=[i+1 for i,line in enumerate(lines) if i+1>markers[0] and line[7:8] not in {'',' '} and re.fullmatch(r'[A-Z0-9][A-Z0-9-]*\.',line[7:72].strip()) and line[6:7]!='*']
            if following and end>=min(following):raise ValueError('java-trace-paragraph-range')
            mapped.add(paragraph);methods.add(method)
            rows.append(dict(file=filename,method=method,program=program,paragraph=paragraph,lines=[start,end]))
    if not set(scope['validation_paragraphs'])<=mapped:raise ValueError('java-trace-unmapped-validation-paragraph')
    if not set(scope['rule_methods'])<=methods:raise ValueError('java-trace-unmapped-rule')
    return dict(schema='carddemo-java-trace/1',program=scope['program'],rules=len(scope['rule_methods']),
                handwritten_nonblank_lines=loc,methods=rows,source=scope['source'],
                remaining_statement_engine_programs=scope['remaining_statement_engine_programs'])


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=Path('.'));p.add_argument('--out',type=Path)
    p.add_argument('--scope',default=SCOPE)
    args=p.parse_args();value=check(args.root,args.scope);text=json.dumps(value,indent=2)+'\n'
    if args.out:args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(text,encoding='utf-8')
    print(text)

if __name__=='__main__':main()
