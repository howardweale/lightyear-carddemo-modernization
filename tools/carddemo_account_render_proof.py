"""J5 rendering inventory and strict supplemental per-class mutation gate."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from tools.carddemo_java_proof import summarize

SCOPE='spec/modernization/carddemo-screens/idiomatic-account-render-scope.json'
JAVA='factory/carddemo-web/service/src/main/java/ai/lightyear/carddemo/'
CLASSES=('AccountRenderRules','AccountRenderStorage','AccountRenderModel','AccountRenderState')
RETIRED=['3200-SETUP-SCREEN-VARS', '3201-SHOW-INITIAL-VALUES', '3202-SHOW-ORIGINAL-VALUES', '3203-SHOW-UPDATED-VALUES', '3250-SETUP-INFOMSG', '3300-SETUP-SCREEN-ATTRS', '3310-PROTECT-ALL-ATTRS', '3320-UNPROTECT-FEW-ATTRS', '3390-SETUP-INFOMSG-ATTRS']
ANNOTATIONS=[['3200-SETUP-SCREEN-VARS', '2698-2729'], ['3201-SHOW-INITIAL-VALUES', '2731-2785'], ['3202-SHOW-ORIGINAL-VALUES', '2787-2869'], ['3203-SHOW-UPDATED-VALUES', '2870-2953'], ['3250-SETUP-INFOMSG', '2955-2985'], ['3300-SETUP-SCREEN-ATTRS', '2986-3439'], ['3310-PROTECT-ALL-ATTRS', '3441-3498'], ['3320-UNPROTECT-FEW-ATTRS', '3500-3564'], ['3390-SETUP-INFOMSG-ATTRS', '3566-3586']]


def check_scope(root,scope=None):
    root=Path(root);scope=scope or json.loads((root/SCOPE).read_bytes())
    if scope['required_mutation_classes']!=list(CLASSES) or scope['annotations']!=ANNOTATIONS:
        raise ValueError('render-required-scope')
    if scope['whole_screen_idiomatic'] is not False or scope['newly_retired_paragraphs']!=RETIRED:
        raise ValueError('render-retirement-claim')
    if scope['independent_full_slice_required'] is not True:raise ValueError('render-independent-proof')
    source=scope['source']
    if source['path']!='spec/modernization/carddemo-screens/upstream/app/cbl/COACTUPC.cbl':
        raise ValueError('render-source-path')
    raw=(root/source['path']).read_bytes().replace(b'\r\n',b'\n')
    if sha256(raw).hexdigest()!=source['sha256']:raise ValueError('render-source-hash')
    labels=[dict(name=line[7:72].strip()[:-1],line=i+1) for i,line in enumerate(raw.decode().splitlines())
        if len(line)>7 and line[6]!='*' and line[7]!=' ' and re.fullmatch('[A-Z0-9][A-Z0-9-]*[.]',line[7:72].strip())]
    if len(labels)!=88 or labels!=source['paragraphs']:raise ValueError('render-paragraph-inventory')
    code=(root/JAVA/'AccountRenderRules.java').read_text()
    found=[list(p) for p in re.findall(r'@CobolSource\(program="COACTUPC", paragraph="([^"]+)", lines="([^"]+)"\)',code)]
    if found!=ANNOTATIONS:raise ValueError('render-annotations')
    starts={p['name']:p['line'] for p in labels}
    for paragraph,span in found:
        first,last=map(int,span.split('-'))
        if first!=starts[paragraph] or last!=starts[paragraph+'-EXIT']+2:raise ValueError('render-source-range')
    if re.search(r'\b(?:SourceEdits|JsonNode|ObjectNode|execute)\b',code):raise ValueError('render-untyped-engine')
    model=(root/JAVA/'AccountRenderModel.java').read_text()
    native=re.findall(r'"([^"]+)","AccountRenderRules"',model)
    if native!=RETIRED or 'AccountMapModel.retire(original)' not in model or 'paragraphs.remove(rule.getKey())' not in model:
        raise ValueError('render-retirement-route')
    service=(root/JAVA/'AccountUpdateService.java').read_text()
    edits=(root/JAVA/'SourceEdits.java').read_text()
    if 'AccountRenderModel.retire(' not in service or 'AccountRenderState.bind(this)' not in edits:raise ValueError('render-production-route')
    for method in ('values', 'initial', 'original', 'updated', 'information', 'attributes', 'protect', 'unprotect', 'informationAttributes'):
        if 'AccountRenderRules.'+method+'(state)' not in edits:raise ValueError('render-production-dispatch')
    base=(root/'factory/carddemo-web/service/pom.xml').read_text()
    expected=re.sub(r'<targetClasses>.*?</targetClasses>','<targetClasses>'+''.join('<param>ai.lightyear.carddemo.'+n+'*</param>' for n in CLASSES)+'</targetClasses>',base,flags=re.S)
    expected=re.sub(r'<targetTests>.*?</targetTests>','<targetTests><param>ai.lightyear.carddemo.AccountRenderRulesTest</param></targetTests>',expected,flags=re.S)
    plugin='<plugin><groupId>org.codehaus.mojo</groupId><artifactId>build-helper-maven-plugin</artifactId><version>3.6.2</version>\n    <executions><execution><id>render-supplemental-tests</id><phase>generate-test-sources</phase><goals><goal>add-test-source</goal></goals>\n      <configuration><sources><source>'+chr(36)+'{project.basedir}/supplemental-tests/render/java</source></sources></configuration>\n    </execution></executions></plugin>'
    expected=expected.replace('<build><plugins>','<build><plugins>'+plugin,1)
    if (root/'factory/carddemo-web/service/render-proof.pom.xml').read_text()!=expected:raise ValueError('render-proof-pom')
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
