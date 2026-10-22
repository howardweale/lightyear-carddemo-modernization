"""J5 exact retirement inventory and strict supplemental mutation gate."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from tools.carddemo_java_proof import summarize

SCOPE='spec/modernization/carddemo-screens/idiomatic-account-map-scope.json'
JAVA='factory/carddemo-web/service/src/main/java/ai/lightyear/carddemo/'
CLASSES=('AccountMapRules','AccountMapStorage','AccountMapModel','AccountMapState')
RETIRED=['1100-RECEIVE-MAP','1200-EDIT-MAP-INPUTS','1205-COMPARE-OLD-NEW','1210-EDIT-ACCOUNT']
ANNOTATIONS=[['1100-RECEIVE-MAP','1039-1428'],['1210-EDIT-ACCOUNT','1783-1822'],
             ['1205-COMPARE-OLD-NEW','1681-1779'],['1200-EDIT-MAP-INPUTS','1429-1680']]


def check_scope(root,scope=None):
    root=Path(root);scope=scope or json.loads((root/SCOPE).read_bytes())
    if scope['required_mutation_classes']!=list(CLASSES) or scope['annotations']!=ANNOTATIONS:
        raise ValueError('map-required-scope')
    if scope['whole_screen_idiomatic'] is not False or scope['newly_retired_paragraphs']!=RETIRED:
        raise ValueError('map-retirement-claim')
    if scope['independent_full_slice_required'] is not True:raise ValueError('map-independent-proof')
    source=scope['source']
    if source['path']!='spec/modernization/carddemo-screens/upstream/app/cbl/COACTUPC.cbl':
        raise ValueError('map-source-path')
    raw=(root/source['path']).read_bytes().replace(b'\r\n',b'\n')
    if sha256(raw).hexdigest()!=source['sha256']:raise ValueError('map-source-hash')
    labels=[dict(name=line[7:72].strip()[:-1],line=i+1) for i,line in enumerate(raw.decode().splitlines())
        if len(line)>7 and line[6]!='*' and line[7]!=' ' and re.fullmatch('[A-Z0-9][A-Z0-9-]*[.]',line[7:72].strip())]
    if len(labels)!=88 or labels!=source['paragraphs']:raise ValueError('map-paragraph-inventory')
    code=(root/JAVA/'AccountMapRules.java').read_text()
    found=[list(p) for p in re.findall(r'@CobolSource\(program="COACTUPC", paragraph="([^"]+)", lines="([^"]+)"\)',code)]
    if found!=ANNOTATIONS:raise ValueError('map-annotations')
    starts={p['name']:p['line'] for p in labels}
    for paragraph,span in found:
        first,last=map(int,span.split('-'))
        if first!=starts[paragraph] or last!=starts[paragraph+'-EXIT']+2:raise ValueError('map-source-range')
    if re.search(r'\b(?:SourceEdits|JsonNode|ObjectNode|execute)\b',code):raise ValueError('map-untyped-engine')
    model=(root/JAVA/'AccountMapModel.java').read_text()
    native=re.findall(r'"([^"]+)","AccountMapRules"',model)
    if native!=RETIRED or 'AccountPhoneDateModel.retire(original)' not in model or 'paragraphs.remove(rule.getKey())' not in model:
        raise ValueError('map-retirement-route')
    service=(root/JAVA/'AccountUpdateService.java').read_text()
    edits=(root/JAVA/'SourceEdits.java').read_text()
    if 'AccountMapModel.retire(' not in service or 'AccountMapState.bind(this)' not in edits:raise ValueError('map-production-route')
    for method in ('receive','validate','compare','account'):
        if 'AccountMapRules.'+method+'(state)' not in edits:raise ValueError('map-production-dispatch')
    base=(root/'factory/carddemo-web/service/pom.xml').read_text()
    expected=re.sub(r'<targetClasses>.*?</targetClasses>','<targetClasses>'+''.join('<param>ai.lightyear.carddemo.'+n+'*</param>' for n in CLASSES)+'</targetClasses>',base,flags=re.S)
    expected=re.sub(r'<targetTests>.*?</targetTests>','<targetTests><param>ai.lightyear.carddemo.AccountMapRulesTest</param></targetTests>',expected,flags=re.S)
    plugin='<plugin><groupId>org.codehaus.mojo</groupId><artifactId>build-helper-maven-plugin</artifactId><version>3.6.2</version>\n    <executions><execution><id>map-supplemental-tests</id><phase>generate-test-sources</phase><goals><goal>add-test-source</goal></goals>\n      <configuration><sources><source>'+chr(36)+'{project.basedir}/supplemental-tests/map/java</source></sources></configuration>\n    </execution></executions></plugin>'
    expected=expected.replace('<build><plugins>','<build><plugins>'+plugin,1)
    if (root/'factory/carddemo-web/service/map-proof.pom.xml').read_text()!=expected:raise ValueError('map-proof-pom')
    return dict(paragraphs=88,newly_retired_paragraphs=RETIRED,whole_screen_idiomatic=False,classes=list(CLASSES),
        source_sha256=source['sha256'],scope_sha256=sha256((root/SCOPE).read_bytes()).hexdigest())


def evaluate(path):
    path=Path(path)
    classes=summarize(ET.parse(path).getroot().findall('mutation') if path.exists() else [],CLASSES)
    return dict(schema='carddemo-j5-mutation/1',passed=all(c['passed'] for c in classes.values()),classes=classes,
        threshold=90,denominator='all generated mutants per class; KILLED only; no timeout/error/no-coverage credit',
        report_sha256=sha256(path.read_bytes()).hexdigest() if path.exists() else None,independent_full_slice_required=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=Path('.'))
    p.add_argument('--mutation',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    value=dict(scope=check_scope(a.root))
    if a.mutation:value['mutation']=evaluate(a.mutation)
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(value,indent=2)+'\n')
    return 0 if not a.mutation or value['mutation']['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
