"""K5 account-view typed-forwarding binding, CI-only validation."""
import argparse,json,re
from hashlib import sha256
from pathlib import Path
import xml.etree.ElementTree as ET
from tools.carddemo_java_proof import summarize
JAVA='factory/carddemo-web/service/src/main/java/ai/lightyear/carddemo/'
BINDINGS={'Commarea.java': '4097f6a2cee072c67ec1d88e318ea43a72ce13e33d943bf842ebfc9c5e2cedf3', 'CommonArea.java': '7a3e062aca9f8b4932e91d8b811d07a2c2812439f8588940b978baecb24791db', 'AccountViewConstants.java': '53a6a426f6c1cf68a9b87df6afadb8374d5639a85a34dc8820f234802c283d31'}
REPLACEMENTS=[('private final AccountViewRendering projection;', 'private final AccountViewRendering projection;private final AccountViewConstants constants;'), ('projection=new AccountViewRendering(bindings);}', 'projection=new AccountViewRendering(bindings);constants=AccountViewConstants.load(bindings);CommonArea.validateLayout(bindings.root.path("program_commareas").path(PROGRAM));}'), ('        ScreenFrame frame=new ScreenFrame(bindings,PROGRAM);', '        CommonArea common=new CommonArea(area);\n        ScreenFrame frame=new ScreenFrame(bindings,PROGRAM);'), ('area.get("CDEMO-FROM-PROGRAM")', 'common.get(CommonArea.Field.PREVIOUS_PROGRAM)'), ('area.set("CDEMO-FROM-PROGRAM",', 'common.set(CommonArea.Field.PREVIOUS_PROGRAM,'), ('area.get("CDEMO-FROM-TRANID")', 'common.get(CommonArea.Field.PREVIOUS_TRANSACTION)'), ('area.set("CDEMO-FROM-TRANID",', 'common.set(CommonArea.Field.PREVIOUS_TRANSACTION,'), ('area.set("CDEMO-TO-PROGRAM",', 'common.set(CommonArea.Field.NEXT_PROGRAM,'), ('area.set("CDEMO-TO-TRANID",', 'common.set(CommonArea.Field.NEXT_TRANSACTION,'), ('area.set("CDEMO-USER-TYPE",', 'common.set(CommonArea.Field.USER_TYPE,'), ('area.set("CDEMO-PGM-CONTEXT",', 'common.set(CommonArea.Field.PROGRAM_CONTEXT,'), ('area.move("CDEMO-LAST-MAPSET",', 'common.move(CommonArea.Field.LAST_MAPSET,'), ('area.move("CDEMO-LAST-MAP",', 'common.move(CommonArea.Field.LAST_MAP,'), ('area.set("CDEMO-ACCT-ID",', 'common.set(CommonArea.Field.ACCOUNT_ID,'), ('area.set("CDEMO-CUST-ID",', 'common.set(CommonArea.Field.CUSTOMER_ID,'), ('area.set("CDEMO-CARD-NUM",', 'common.set(CommonArea.Field.CARD_NUMBER,'), ('bindings.program(PROGRAM).path("constants").path("LIT-MENUPGM").asText()', 'constants.menuProgram()'), ('bindings.program(PROGRAM).path("constants").path("LIT-MENUTRANID").asText()', 'constants.menuTransaction()'), ('bindings.program(PROGRAM).path("constants").path("LIT-THISMAPSET").asText()', 'constants.mapset()'), ('bindings.program(PROGRAM).path("constants").path("LIT-THISMAP").asText()', 'constants.map()')]
def restore_service(root,service):
    for name,expected in BINDINGS.items():
        raw=(Path(root)/JAVA/name).read_bytes().replace(b'\r\n',b'\n')
        if sha256(raw).hexdigest()!=expected:raise ValueError('common-area-adapter-binding')
    if re.search(r'"(?:CDEMO|ACUP)-',service):raise ValueError('common-area-string-key')
    for old,new in reversed(REPLACEMENTS):
        if new not in service:raise ValueError('common-area-service-route')
        service=service.replace(new,old)
    return service
def evaluate(path):
    path=Path(path)
    classes=summarize(ET.parse(path).getroot().findall('mutation') if path.exists() else [],('CommonArea','AccountViewConstants'))
    return dict(passed=all(c['passed'] for c in classes.values()),classes=classes,threshold=90,
        denominator='all generated mutants per class; KILLED only',merge_authorized=False)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--mutation',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    result=evaluate(a.mutation);a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(0 if result['passed'] else 1)
