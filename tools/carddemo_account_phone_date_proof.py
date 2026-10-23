"""Additional phone/date scope and per-class proof; never replaces frozen slice evidence."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from tools.carddemo_java_proof import summarize
from tools.carddemo_render_route import check_render_route

SCOPE='spec/modernization/carddemo-screens/idiomatic-account-phone-date-scope.json'
JAVA='factory/carddemo-web/service/src/main/java/ai/lightyear/carddemo/'
CLASSES=('AccountPhoneRules','AccountDateRules','AccountEditState','AccountPhoneDateModel')
RANGES={'1260-EDIT-US-PHONE-NUM':'AccountPhoneRules','EDIT-DATE-CCYYMMDD':'AccountDateRules','EDIT-DATE-OF-BIRTH':'AccountDateRules'}

def check_service_route(root, service):
    argument='bindings.root.path("account_update").path("validation")'
    if 'AccountPhoneDateModel.retire('+argument+')' in service:return
    # J5 composes the existing retirement. Bind the complete reviewed adapter,
    # so a missing call, changed input, discarded result or decoy is refused.
    if 'AccountRenderModel.retire('+argument+')' in service:
        check_render_route(root,service);return
    model=Path(root)/JAVA/'AccountMapModel.java'
    if 'AccountMapModel.retire('+argument+')' not in service or not model.is_file():
        raise ValueError('phone-date-service-routing')
    if sha256(model.read_bytes().replace(b'\r\n',b'\n')).hexdigest()!='8944014de4abdca25cbfcb812536dc3b7a8a1230d1c26aac0aa1b1fb370b50ae':
        raise ValueError('phone-date-composed-model-binding')


def check_scope(root, scope=None):
    root=Path(root);scope=scope or json.loads((root/SCOPE).read_bytes())
    if scope['retired_ranges']!=RANGES or scope['required_mutation_classes']!=list(CLASSES):raise ValueError('phone-date-required-scope')
    if scope['whole_screen_idiomatic'] is not False or 'COACTUPC' not in scope['remaining_statement_engine_programs']:raise ValueError('phone-date-whole-screen-claim')
    expected_sources=['spec/modernization/carddemo-screens/upstream/app/cbl/COACTUPC.cbl','spec/modernization/carddemo-screens/upstream/app/cpy/CSUTLDPY.cpy']
    if [s['path'] for s in scope['sources']]!=expected_sources:raise ValueError('phone-date-source-set')
    for source in scope['sources']:
        raw=(root/source['path']).read_bytes().replace(b'\r\n',b'\n')
        if sha256(raw).hexdigest()!=source['sha256']:raise ValueError('phone-date-source-hash')
        labels=[dict(name=line[7:72].strip()[:-1],line=i+1) for i,line in enumerate(raw.decode().splitlines())
            if len(line)>7 and line[6]!='*' and line[7]!=' ' and re.fullmatch('[A-Z0-9][A-Z0-9-]*[.]',line[7:72].strip())]
        if labels!=source['paragraphs']:raise ValueError('phone-date-paragraph-inventory')
    labels=[{p['name']:p['line'] for p in source['paragraphs']} for source in scope['sources']]
    ranges={'1260-EDIT-US-PHONE-NUM':(labels[0]['1260-EDIT-US-PHONE-NUM'],labels[0]['1260-EDIT-US-PHONE-NUM-EXIT']+2),
            'EDIT-DATE-CCYYMMDD':(labels[1]['EDIT-DATE-CCYYMMDD'],labels[1]['EDIT-DATE-CCYYMMDD-EXIT']+2),
            'EDIT-DATE-OF-BIRTH':(labels[1]['EDIT-DATE-OF-BIRTH'],labels[1]['EDIT-DATE-OF-BIRTH-EXIT']+2)}
    for paragraph,owner in RANGES.items():
        start,end=ranges[paragraph]
        annotation='@CobolSource(program="COACTUPC", paragraph="'+paragraph+'", lines="'+str(start)+'-'+str(end)+'")'
        if annotation not in (root/JAVA/(owner+'.java')).read_text():raise ValueError('phone-date-physical-range')
    for filename in ('AccountPhoneRules.java','AccountDateRules.java'):
        code=(root/JAVA/filename).read_text()
        if re.search(r'\b(?:SourceEdits|JsonNode|ObjectNode|execute|run)\b',code):raise ValueError('phone-date-statement-engine')
        for name,owner in RANGES.items():
            if owner+'.java'==filename and 'paragraph="'+name+'"' not in code:raise ValueError('phone-date-range-annotation')
    service=(root/JAVA/'AccountUpdateService.java').read_text()
    check_service_route(root,service)
    adapter=(root/JAVA/'AccountPhoneDateModel.java').read_text()
    if any('"'+name+'","'+owner+'"' not in adapter for name,owner in RANGES.items()):raise ValueError('phone-date-retirement-routing')
    base=(root/'factory/carddemo-web/service/pom.xml').read_text()
    additional=(root/'factory/carddemo-web/service/phone-date-proof.pom.xml').read_text()
    expected=re.sub(r'<targetClasses>.*?</targetClasses>','<targetClasses>'+''.join('<param>ai.lightyear.carddemo.'+name+'*</param>' for name in CLASSES)+'</targetClasses>',base,flags=re.S)
    expected=re.sub(r'<targetTests>.*?</targetTests>','<targetTests><param>ai.lightyear.carddemo.AccountPhoneDateRulesTest</param></targetTests>',expected,flags=re.S)
    expected=expected.replace('<build><plugins>','<build><plugins>'+'<plugin><groupId>org.codehaus.mojo</groupId><artifactId>build-helper-maven-plugin</artifactId><version>3.6.2</version>\n    <executions><execution><id>phone-date-supplemental-tests</id><phase>generate-test-sources</phase><goals><goal>add-test-source</goal></goals>\n      <configuration><sources><source>${project.basedir}/supplemental-tests/phone-date/java</source></sources></configuration>\n    </execution></executions></plugin>',1)
    if additional!=expected:raise ValueError('phone-date-additional-pom-scope')
    return dict(source_paragraphs={s['path']:len(s['paragraphs']) for s in scope['sources']},retired_ranges=RANGES,
        whole_screen_idiomatic=False,scope_sha256=sha256((root/SCOPE).read_bytes()).hexdigest())

def evaluate(path):
    path=Path(path);nodes=ET.parse(path).getroot().findall('mutation') if path.exists() else []
    classes=summarize(nodes,CLASSES)
    return dict(schema='carddemo-phone-date-mutation/1',passed=all(c['passed'] for c in classes.values()),
        classes=classes,threshold=90,denominator='all generated mutants per required class; KILLED only; no timeout/error/no-coverage credit',
        report_sha256=sha256(path.read_bytes()).hexdigest() if path.exists() else None,
        independent_full_slice_required=True,whole_screen_idiomatic=False)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=Path('.'));p.add_argument('--mutation',type=Path);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();value=dict(scope=check_scope(a.root))
    if a.mutation:value['mutation']=evaluate(a.mutation)
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(value,indent=2)+'\n')
    return 0 if not a.mutation or value['mutation']['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
