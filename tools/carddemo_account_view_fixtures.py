"""CI-only fixtures from original COACTVWC statements, never candidate outputs.

Scope: record projection inside 1200, not whole-screen or whole-working-storage
Java equivalence. Complete reference storage is retained for independent audit.
"""
import argparse,copy,json
from datetime import datetime,timezone
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from lightyear_data.carddemo.reference_screens import AccountViewReference
from lightyear_data.carddemo.reference_control import Machine
from lightyear_data.carddemo.reference_values import Values
SCOPE='spec/modernization/carddemo-screens/idiomatic-account-view-scope.json'
MONEY=('ACCT-CURR-BAL','ACCT-CREDIT-LIMIT','ACCT-CASH-CREDIT-LIMIT','ACCT-CURR-CYC-CREDIT','ACCT-CURR-CYC-DEBIT')

def generate(root):
    root=Path(root);scope=json.loads((root/SCOPE).read_bytes())
    source=root/scope['source']['path'];raw=source.read_text()
    if sha256(raw.encode()).hexdigest()!=scope['source']['sha256']:raise ValueError('view-reference-source-hash')
    adapter=AccountViewReference(root/'spec/modernization/carddemo-screens/upstream',datetime(2026,10,22,12,tzinfo=timezone.utc))
    baseline=adapter.storage()
    for field in ('ACCT-OPEN-DATE','ACCT-EXPIRAION-DATE','ACCT-REISSUE-DATE','CUST-DOB-YYYY-MM-DD'):
        baseline.write(field,'2026-10-22')
    targets=[target for _,target in scope['source_moves']]+['ACSTSSN']
    if len(targets)!=28 or len(set(targets))!=28:raise ValueError('view-reference-targets')
    cases=[]
    def capture(identity,account,customer,field=None,value=None,source_lines=None):
        memory=copy.deepcopy(baseline)
        memory.write('EIBCALEN',1)
        memory.write('WS-ACCOUNT-MASTER-READ-FLAG','1' if account else ' ')
        memory.write('WS-CUST-MASTER-READ-FLAG','1' if customer else ' ')
        if field:memory.write(field,value)
        # Seed physical bytes, including numeric-edited output fields, without numeric conversion.
        for target in targets:memory.write_slice(target+'O',0,None,'STALE-'+target)
        before=[bytes(region).hex() for region in memory.regions]
        account_raw=memory.raw('ACCOUNT-RECORD');customer_raw=memory.raw('CUSTOMER-RECORD')
        machine=Machine(adapter.program,Values(memory,clock=adapter.clock))
        machine.run('1200-SETUP-SCREEN-VARS','1200-SETUP-SCREEN-VARS-EXIT')
        if memory.raw('ACCOUNT-RECORD')!=account_raw or memory.raw('CUSTOMER-RECORD')!=customer_raw:
            raise ValueError('view-reference-record-mutated')
        cases.append(dict(id=identity,source_lines=source_lines or '471-523',
            account=account_raw.hex() if account or customer else None,
            customer=customer_raw.hex() if customer else None,
            expected={target:memory.raw(target+'O').decode('cp037') for target in targets},
            reference_before=before,reference_after=[bytes(region).hex() for region in memory.regions],
            statement_trace=[dict(source=Path(path).relative_to(root).as_posix(),line=line) for path,line in machine.trace]))
    # 471-493: account output also runs when customer was found; preserve the
    # explicit initialized-account assumption already present in the service.
    for account in (False,True):
        for customer in (False,True):capture('presence-'+str(int(account))+str(int(customer)),account,customer)
    for field,_ in scope['source_moves']:
        _,definition=baseline.descriptor(field)
        for variant in range(2):
            if field in ('ACCT-OPEN-DATE','ACCT-EXPIRAION-DATE','ACCT-REISSUE-DATE','CUST-DOB-YYYY-MM-DD'):
                value=('2000-02-29','2026-10-22')[variant]
            elif definition['digits']:value=Decimal(0 if variant==0 else 123)
            else:value=' '*definition['length'] if variant==0 else ('aB'*definition['length'])[:definition['length']]
            capture('move-'+field+'-'+str(variant),True,True,field,value)
    # 475-486: sign and magnitude independently vary all five money moves.
    for field in MONEY:
        for value in ('0.00','0.01','-0.01','1234567.89','-1234567.89','999999999.99'):
            capture('money-'+field+'-'+value,True,True,field,Decimal(value),'475-486')
    # 497-504: the original STRING uses three source reference modifications.
    for value in ('0','1','12345678','123456789','987654321'):
        capture('ssn-'+value,True,True,'CUST-SSN',Decimal(value),'497-504')
    if len(cases)!=93 or len({case['id'] for case in cases})!=93:raise ValueError('view-reference-case-inventory')
    reference_paths=sorted((root/'src/lightyear_data/carddemo').glob('reference_*.py'))
    reference_paths += [root/'src/lightyear_data/carddemo/screens.py',root/'tools/carddemo_account_view_fixtures.py',root/SCOPE]
    source_bindings={path.relative_to(root).as_posix():sha256(path.read_bytes()).hexdigest() for path in reference_paths}
    return dict(schema='carddemo-view-source-fixtures/1',source_bindings=source_bindings,source_sha256=scope['source']['sha256'],
        source_path=scope['source']['path'],case_count=len(cases),projection_only=True,
        whole_storage_java_equivalence=False,cases=cases)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=Path('.'));p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    value=generate(a.root.resolve());a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(value,sort_keys=True,separators=(',',':'))+'\n',encoding='utf-8')
    return 0
if __name__=='__main__':raise SystemExit(main())
