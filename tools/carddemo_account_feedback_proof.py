"""J1 scope and supplemental mutation proof; original full-slice gates remain required."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from tools.carddemo_java_proof import summarize
from tools.carddemo_proof_profiles import baseline_pom, profile_pom

SCOPE='spec/modernization/carddemo-screens/idiomatic-account-feedback-scope.json'
JAVA='factory/carddemo-web/service/src/main/java/ai/lightyear/carddemo/'
CLASSES=('AccountValidationFeedback','AccountFeedbackState')
ANNOTATIONS={
    'AccountValidationFeedback':[['1215-EDIT-MANDATORY','1824-1854'],['1225-EDIT-ALPHA-REQD','1898-1950'],['1215-EDIT-MANDATORY','1836-1844']],
    'AccountFeedbackState':[['1215-EDIT-MANDATORY','1838-1843'],['1215-EDIT-MANDATORY','1836-1843'],['1215-EDIT-MANDATORY','1838-1838']]}


def check_scope(root,scope=None):
    root=Path(root);scope=scope or json.loads((root/SCOPE).read_bytes())
    if scope['required_mutation_classes']!=list(CLASSES) or scope['annotations']!=ANNOTATIONS:
        raise ValueError('feedback-required-scope')
    if scope['whole_screen_idiomatic'] is not False or scope['newly_retired_paragraphs']!=[]:
        raise ValueError('feedback-scope-claim')
    source=scope['source']
    if source['path']!='spec/modernization/carddemo-screens/upstream/app/cbl/COACTUPC.cbl':
        raise ValueError('feedback-source-path')
    raw=(root/source['path']).read_bytes().replace(b'\r\n',b'\n')
    if sha256(raw).hexdigest()!=source['sha256']:raise ValueError('feedback-source-hash')
    lines=raw.decode().splitlines()
    labels=[dict(name=line[7:72].strip()[:-1],line=i+1) for i,line in enumerate(lines)
        if len(line)>7 and line[6]!='*' and line[7]!=' ' and re.fullmatch('[A-Z0-9][A-Z0-9-]*[.]',line[7:72].strip())]
    if len(labels)!=88 or labels!=source['paragraphs']:raise ValueError('feedback-paragraph-inventory')
    starts={p['name']:p['line'] for p in labels}
    for name in CLASSES:
        code=(root/JAVA/(name+'.java')).read_text()
        found=[list(pair) for pair in re.findall(r'@CobolSource\(program="COACTUPC", paragraph="([^"]+)", lines="([^"]+)"\)',code)]
        if found!=ANNOTATIONS[name]:raise ValueError('feedback-annotations')
        for paragraph,span in found:
            start,end=map(int,span.split('-'))
            if not starts[paragraph]<=start<=end<=starts[paragraph+'-EXIT']+2:
                raise ValueError('feedback-physical-range')
    code=(root/JAVA/'AccountValidationFeedback.java').read_text()
    if re.search(r'\b(?:SourceEdits|JsonNode|ObjectNode|execute)\b',code):raise ValueError('feedback-untyped-engine')
    expected_fields={'INPUT_FLAG':'WS-INPUT-FLAG','MESSAGE':'WS-RETURN-MSG','LABEL':'WS-EDIT-VARIABLE-NAME'}
    if scope['field_storage']!=expected_fields or any(k+'("'+v+'")' not in code for k,v in expected_fields.items()):
        raise ValueError('feedback-field-binding')
    source_edits=(root/JAVA/'SourceEdits.java').read_text()
    if 'AccountValidationFeedback.error(new AccountFeedbackState(this),reason)' not in source_edits:
        raise ValueError('feedback-production-route')
    base=baseline_pom(root)
    expected=re.sub(r'<targetClasses>.*?</targetClasses>','<targetClasses>'+''.join('<param>ai.lightyear.carddemo.'+n+'*</param>' for n in CLASSES)+'</targetClasses>',base,flags=re.S)
    expected=re.sub(r'<targetTests>.*?</targetTests>','<targetTests><param>ai.lightyear.carddemo.AccountFeedbackTest</param></targetTests>',expected,flags=re.S)
    expected=expected.replace('<build><plugins>','<build><plugins>'+'<plugin><groupId>org.codehaus.mojo</groupId><artifactId>build-helper-maven-plugin</artifactId><version>3.6.2</version>\n    <executions><execution><id>feedback-supplemental-tests</id><phase>generate-test-sources</phase><goals><goal>add-test-source</goal></goals>\n      <configuration><sources><source>${project.basedir}/supplemental-tests/feedback/java</source></sources></configuration>\n    </execution></executions></plugin>',1)
    if profile_pom(root, 'feedback')!=expected:
        raise ValueError('feedback-mutation-pom')
    return dict(paragraphs=88,newly_retired_paragraphs=[],whole_screen_idiomatic=False,
        classes=list(CLASSES),source_sha256=source['sha256'],scope_sha256=sha256((root/SCOPE).read_bytes()).hexdigest())


def evaluate(path):
    path=Path(path)
    classes=summarize(ET.parse(path).getroot().findall('mutation') if path.exists() else [],CLASSES)
    return dict(schema='carddemo-j1-mutation/1',passed=all(c['passed'] for c in classes.values()),classes=classes,
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
