"""Load pinned public VSAM bytes and explicit synthetic IMS demo fixtures.

Only the disposable Compose database is supported. Layouts, SQL and encodings
come from the source compilers; field assignments below are test data, not maps.
No Factory request, key, signature, activation or native system is accessed.
"""
import json, os
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
import psycopg
from lightyear_data.carddemo.plan import build
from lightyear_data.carddemo.web_bindings import build as web_build
from lightyear_data.carddemo.schema import ddl
from lightyear_data.carddemo.codec import split_fixed, project, encode_field
from lightyear_data.carddemo.store import Store

ROOT=Path('spec/modernization/carddemo-data')

def field(mapping,name):
    matches=[f for f in mapping['fields'] if f['path'].split('.')[-1]==name]
    if len(matches)!=1:raise ValueError('ambiguous fixture field: '+name)
    return matches[0]

def value(layout,mapping,raw,name):
    return project(layout,mapping,raw)['values'][field(mapping,name)['path']]

def fixture(layout,mapping,values):
    raw=bytearray(b'\x40'*layout.record_length)
    for f in mapping['fields']:
        if f['filler']:continue
        name=f['path'].split('.')[-1]
        v=values.get(name,Decimal(0) if f['digits'] else ' ')
        if not f['digits']:v=str(v).ljust(f['length'])
        encoded=encode_field(f,v,{},'cp037');raw[f['offset']:f['offset']+f['length']]=encoded
    return bytes(raw)

def main():
    dsn=os.environ['CARDDEMO_DSN']
    if dsn!='postgresql://carddemo:disposable-public-demo@postgres/carddemo':raise ValueError('disposable Compose database only')
    plan,entries=build(ROOT);bindings=web_build(Path('spec/modernization/carddemo-screens'))
    identity=sha256((plan['content_sha256']+json.dumps(bindings,sort_keys=True)+Path(__file__).read_text()).encode()).hexdigest()
    public={};reference_records=[]
    def capture(m,raw,ordinal,parent=None):
        reference_records.append(dict(table=m['table'],identity=m['table']+':'+str(ordinal),raw=raw.hex(),
            keys=[dict(length=k['key_length'],offset=k['key_offset'],value=raw[k['key_offset']:k['key_offset']+k['key_length']].hex()) for k in m['keys']],
            segment=m.get('segment',{}).get('name'),parent=parent))
    for item,layout,mapping in entries:
        if not item.get('synthetic'):
            raw=(ROOT/'upstream'/item['data']).read_bytes()
            public[mapping['table']]=list(split_fixed(raw,layout.record_length))
    lookup={m['table']:(layout,m) for _,layout,m in entries}
    xl,xm=lookup['cardxref'];xref=public['cardxref'][0]
    account=str(value(xl,xm,xref,'XREF-ACCT-ID')).zfill(11)
    customer=str(value(xl,xm,xref,'XREF-CUST-ID')).zfill(9)
    card=str(value(xl,xm,xref,'XREF-CARD-NUM'))
    ul,um=lookup['usrsec']
    user=next(r for r in public['usrsec'] if value(ul,um,r,'SEC-USR-TYPE')=='U')
    receipt=dict(schema='carddemo-compose-fixture/1',identity=identity,account=account,customer=customer,card=card,
        user=value(ul,um,user,'SEC-USR-ID').strip(),password=value(ul,um,user,'SEC-USR-PWD').strip(),
        public_records={k:len(v) for k,v in public.items()},synthetic_authorizations=7,
        scope='Public VSAM records plus generated IMS fixtures; not an IMS unload or native execution',
        screen_equivalence_verified=False)
    with psycopg.connect(dsn) as db:
        db.execute('CREATE TABLE IF NOT EXISTS slice_fixture_identity (identity text PRIMARY KEY)')
        previous=db.execute('SELECT identity FROM slice_fixture_identity').fetchall()
        if previous:
            if previous!=[(identity,)]:raise ValueError('existing fixture differs; use a separate disposable Compose project')
        else:
            for _,_,m in entries:db.execute(ddl(m))
            db.execute(bindings['fraud']['postgres_ddl'])
            for item,layout,m in entries:
                if item.get('synthetic'):continue
                store=Store(db,m,layout)
                for ordinal,raw in enumerate(public[m['table']],1):
                    store.load_one(raw,ordinal,quarantine=False);capture(m,raw,ordinal)
            sl,sm=lookup['pautsum0'];dl,dm=lookup['pautdtl1']
            summary=fixture(sl,sm,{'PA-ACCT-ID':account,'PA-CUST-ID':customer,'PA-APPROVED-AUTH-CNT':7,'PA-APPROVED-AUTH-AMT':'86.38'})
            parent=Store(db,sm,sl).load_one(summary,1,twin_seq=1,quarantine=False)['path_key'];capture(sm,summary,1)
            for i in range(1,8):
                detail=fixture(dl,dm,{'PA-AUTH-DATE-9C':99999-26000-i,'PA-AUTH-TIME-9C':999999999-123456000-i,
                    'PA-AUTH-ORIG-DATE':'261017','PA-AUTH-ORIG-TIME':'123456','PA-CARD-NUM':card,
                    'PA-AUTH-TYPE':'AUTH','PA-CARD-EXPIRY-DATE':'2912','PA-AUTH-RESP-CODE':'00',
                    'PA-AUTH-RESP-REASON':'0000','PA-TRANSACTION-AMT':'12.34','PA-APPROVED-AMT':'12.34',
                    'PA-MERCHANT-CATAGORY-CODE':'1234','PA-ACQR-COUNTRY-CODE':'840','PA-MERCHANT-ID':str(i),
                    'PA-MERCHANT-NAME':'PUBLIC DEMO '+str(i),'PA-MERCHANT-CITY':'SEATTLE','PA-MERCHANT-STATE':'WA',
                    'PA-MERCHANT-ZIP':'981010000','PA-TRANSACTION-ID':str(i),'PA-MATCH-STATUS':'P','PA-AUTH-FRAUD':' '})
                Store(db,dm,dl).load_one(detail,i,parent_path=parent,twin_seq=i,quarantine=False);capture(dm,detail,i,'pautsum0:1')
            db.execute('INSERT INTO slice_fixture_identity VALUES (%s)',(identity,))
    if reference_records:Path('/fixture/reference-fixture.json').write_text(json.dumps(dict(schema='carddemo-raw-proof-fixture/1',records=reference_records,plan=plan),indent=2)+'\n')
    Path('/fixture/fixture.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({k:v for k,v in receipt.items() if k not in ('password','user')}))

if __name__=='__main__':main()
