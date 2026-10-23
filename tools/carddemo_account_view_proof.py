"""Source-bound account-view projection scope; no whole-screen completion claim."""
import argparse,json,re
from hashlib import sha256
from pathlib import Path
import xml.etree.ElementTree as ET
from tools.carddemo_java_proof import summarize
from tools.carddemo_proof_profiles import baseline_pom, profile_pom
SCOPE='spec/modernization/carddemo-screens/idiomatic-account-view-scope.json'
JAVA='factory/carddemo-web/service/src/main/java/ai/lightyear/carddemo/'
CLASSES=('AccountViewRendering',)
def digest(text):return sha256(text.replace('\r\n','\n').encode()).hexdigest()
SERVICE_ORACLE='factory/carddemo-web/service/supplemental-tests/account-view/java/ai/lightyear/carddemo/AccountViewProjectionOracle.java'

def check_service_oracle(text,expected):
    for after,before in [('class AccountViewProjectionOracle ','class AccountViewService '),('public AccountViewProjectionOracle(','public AccountViewService(')]:
        if text.count(after)!=1:raise ValueError('view-service-oracle-name')
        text=text.replace(after,before)
    if digest(text)!=expected:raise ValueError('view-service-oracle-changed')

def check_scope(root,scope=None):
    root=Path(root);scope=scope or json.loads((root/SCOPE).read_bytes())
    if scope['whole_screen_idiomatic'] is not False or scope['retired_paragraphs']!=[]:raise ValueError('view-claim')
    if scope['required_mutation_classes']!=list(CLASSES) or scope['independent_full_slice_required'] is not True:raise ValueError('view-proof-scope')
    source=scope['source']
    if source['path']!='spec/modernization/carddemo-screens/upstream/app/cbl/COACTVWC.cbl':raise ValueError('view-source-path')
    raw=(root/source['path']).read_text(encoding='utf-8')
    if digest(raw)!=source['sha256']:raise ValueError('view-source-hash')
    labels=[dict(name=line[7:72].strip()[:-1],line=i+1) for i,line in enumerate(raw.splitlines())
        if len(line)>7 and line[6]!='*' and line[7]!=' ' and re.fullmatch('[A-Z0-9][A-Z0-9-]*[.]',line[7:72].strip())]
    if len(labels)!=38 or labels!=source['inventory']:raise ValueError('view-inventory')
    if [p['line'] for p in labels if p['name']=='0000-MAIN-EXIT']!=[408,411]:raise ValueError('view-duplicate-occurrences')
    procedures=labels[3:]
    if len(procedures)!=35 or scope.get('procedure_inventory')!=procedures:raise ValueError('view-procedure-inventory')
    accounting=dict(source_label_occurrences=38,metadata_labels=3,procedure_occurrences=35,
        complete_paragraph_retirements=0,partial_projection_paragraph='1200-SETUP-SCREEN-VARS')
    if scope.get('retirement_accounting')!=accounting:raise ValueError('view-retirement-accounting')
    code=(root/JAVA/'AccountViewRendering.java').read_text(encoding='utf-8')
    moves=re.findall(r'move\(frame,"([A-Z0-9]+)",Field\.([A-Z0-9_]+),(account|customer)\);',code)
    expected=[(target,field.replace('-','_'),'account' if field.startswith('ACCT-') else 'customer') for field,target in scope['source_moves']]
    if len(expected)!=27 or moves!=expected:raise ValueError('view-moves')
    if 'ssn.substring(0,3)+"-"+ssn.substring(3,5)+"-"+ssn.substring(5,9)' not in code:raise ValueError('view-ssn-slices')
    if '@CobolSource(program="COACTVWC", paragraph="1200-SETUP-SCREEN-VARS", lines="460-535")' not in code:raise ValueError('view-annotation')
    if 'account_view_projection' in code or re.search(r'\b(?:JsonNode|SourceEdits)\b',code):raise ValueError('view-generic-route')
    service=(root/JAVA/'AccountViewService.java').read_text(encoding='utf-8')
    if service.count('@CobolSource(program="COACTVWC", paragraph="0000-MAIN", lines="262-393")')!=1:raise ValueError('view-service-annotation')
    replacements=[('private final AccountViewRendering projection','private final ScreenProjection projection'),
                  ('projection=new AccountViewRendering(bindings)','projection=new ScreenProjection(bindings)'),
                  ('projection.apply(frame,rows.get("acctdata"),rows.get("custdata"))','projection.apply(frame,bindings.root.path("account_view_projection"),rows)')]
    for after,before in replacements:
        if service.count(after)!=1:raise ValueError('view-service-route')
        service=service.replace(after,before)
    service=re.sub(r'^    @CobolSource\(program="COACTVWC", paragraph="0000-MAIN", lines="262-393"\)\n','',service,flags=re.M)
    if digest(service)!=scope['service_original_sha256']:raise ValueError('view-control-flow-changed')
    check_service_oracle((root/SERVICE_ORACLE).read_text(encoding='utf-8'),scope['service_original_sha256'])
    if digest((root/JAVA/'ScreenProjection.java').read_text(encoding='utf-8'))!=scope['oracle_sha256']:raise ValueError('view-oracle-changed')
    base=baseline_pom(root)
    expected=re.sub(r'<targetClasses>.*?</targetClasses>','<targetClasses><param>ai.lightyear.carddemo.AccountViewRendering*</param></targetClasses>',base,flags=re.S)
    expected=re.sub(r'<targetTests>.*?</targetTests>','<targetTests><param>ai.lightyear.carddemo.AccountViewRenderingTest</param></targetTests>',expected,flags=re.S)
    plugin='<plugin><groupId>org.codehaus.mojo</groupId><artifactId>build-helper-maven-plugin</artifactId><version>3.6.2</version>\n    <executions><execution><id>account-view-supplemental-tests</id><phase>generate-test-sources</phase><goals><goal>add-test-source</goal></goals>\n      <configuration><sources><source>${project.basedir}/supplemental-tests/account-view/java</source></sources></configuration>\n    </execution></executions></plugin>'
    expected=expected.replace('<build><plugins>','<build><plugins>'+plugin,1)
    if profile_pom(root, 'account-view')!=expected:raise ValueError('view-pom')
    return dict(source_label_occurrences=38,paragraph_occurrences=35,whole_screen_idiomatic=False,source_sha256=source['sha256'],independent_full_slice_required=True)

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
