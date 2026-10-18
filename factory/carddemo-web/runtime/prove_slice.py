"""CI-only six-screen differential sessions from raw pinned COBOL.

Every interaction compares values, effective attributes, cursor, message and
every PostgreSQL table. Expected record writes come from the reference store;
the shared data-plan/codec projection is explicitly disclosed in the receipt.
Unsupported reference semantics fail the gate and remain in its denominator.
"""
import argparse,json,urllib.request,traceback
from copy import deepcopy
from itertools import count
from datetime import date,datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from lightyear_data.carddemo.reference_control import Unsupported
from lightyear_data.carddemo.reference_signon import SignonReference
from lightyear_data.carddemo.reference_menu import MenuReference
from lightyear_data.carddemo.reference_screens import AccountViewReference,AccountUpdateReference,AuthorizationListReference,AuthorizationDetailReference
from lightyear_data.carddemo.reference_fixture import load
from lightyear_data.carddemo.plan import build
from lightyear_data.carddemo.store import Store
from snapshot import snapshot

PROGRAMS=['COSGN00C','COMEN01C','COACTVWC','COACTUPC','COPAUS0C','COPAUS1C']
def canonical(value):
    if isinstance(value,bool) or value is None:return value
    if isinstance(value,(int,float,Decimal)):return {'$number':format(Decimal(str(value)).normalize(),'f')}
    if isinstance(value,bytes):return '\\x'+value.hex()
    if isinstance(value,(datetime,date)):return value.isoformat()
    if isinstance(value,dict):return {k:canonical(v) for k,v in sorted(value.items())}
    if isinstance(value,list):return [canonical(v) for v in value]
    return value
def digest(value):return sha256(json.dumps(canonical(value),sort_keys=True,separators=(',',':')).encode()).hexdigest()
def attributes(frame):
    result=deepcopy(frame['attributes'])
    for value in result.values():
        value.setdefault('intensity','BRIGHT' if 'BRT' in value['basic'] else 'DARK' if value['hidden'] else 'NORMAL')
        value.setdefault('autoskip','ASKIP' in value['basic'])
    return result
def compare_frame(actual,expected):
    assert actual['program']==expected['program'],(actual['program'],expected['program'])
    if expected.get('outside_slice'):
        assert actual['endpoint']=='/not-in-this-slice';return
    if expected['ended']:
        assert actual['message']==expected['screen']['message'];return
    for part in ('values','cursor','message'):
        assert actual[part]==expected['screen'][part],dict(part=part,actual=actual[part],expected=expected['screen'][part])
    assert attributes(actual)==attributes(expected['screen']),'effective BMS attributes differ'

class Engine:
    def __init__(self,fixture):
        root=Path('spec/modernization/carddemo-screens/upstream');self.signon=SignonReference(root);self.menu=MenuReference(root)
        self.adapters={c.program_name:c(root) for c in (AccountViewReference,AccountUpdateReference,AuthorizationListReference,AuthorizationDetailReference)}
        self.store=load(fixture,list(self.adapters.values()),Path('spec/modernization/carddemo-data/upstream'))
        for adapter in self.adapters.values():adapter.store=self.store
        for record in self.store.records:
            if record['table']=='usrsec':
                m=self.signon.storage();m.write('SEC-USER-DATA',record['raw'].decode('cp037'));self.signon.users[m.read('SEC-USR-ID')]=record['raw']
        self.common=self.signon.storage().descriptor('CARDDEMO-COMMAREA')[1]['length'];self.reset()
    def reset(self):self.program='COSGN00C';self.area=None;self.frame=None;self.faulted=False
    def step(self,aid,fields):
        if self.faulted:raise Unsupported('continuation after raw source fault is unproved')
        for depth in range(8):
            previous=self.program
            if previous=='COSGN00C':result=self.signon.interact(aid,fields)
            elif previous=='COMEN01C':
                try:result=self.menu.interact(aid,fields,self.area)
                except Unsupported as failure:
                    # The pinned source SENDs the validation error, then indexes an
                    # invalid option. Retain the actual emitted image and trace;
                    # this session MUST end at the source fault, without inventing
                    # a next COMMAREA or a successful COBOL RETURN.
                    if not str(failure).startswith(('reference storage absent/ambiguous: CDEMO-MENU-OPT-USRTYPE[','nonnumeric reference subscript: CDEMO-MENU-OPT-USRTYPE')) or self.menu.frame is None:raise
                    result=dict(program=previous,screen=self.menu.frame,ended=False,trace=self.menu.trace,commarea=self.area,source_fault=str(failure))
            else:result=self.adapters[previous].interact(aid,fields,self.area,self.frame)
            self.faulted=bool(result.get('source_fault'));self.area=result['commarea'];self.frame=result.get('screen')
            if result['program']==previous or result['ended']:return result
            self.program=result['program']
            if self.program not in PROGRAMS:
                # A documented slice boundary, never a claim to implement that program.
                result['outside_program']=self.program;self.program=previous;result['program']=previous;result['outside_slice']=True;return result
            if not {previous,self.program}<= {'COPAUS0C','COPAUS1C'}:self.area=self.area[:self.common*2]
            aid='INITIAL';fields={}
        raise Unsupported('reference XCTL depth')

class Proof:
    def __init__(self,args):
        self.args=args;self.out=args.out;self.out.mkdir(parents=True,exist_ok=True)
        self.fixture=json.loads(args.fixture.read_bytes());self.raw_fixture=json.loads(args.raw_fixture.read_bytes());self.engine=Engine(self.raw_fixture)
        state=snapshot(self.out/'database');self.initial=json.loads((self.out/'database'/state['path']).read_bytes())
        self.engine.store.fraud=deepcopy(self.initial['authfrds']);self.entries={m['table']:(l,m) for _,l,m in build(Path('spec/modernization/carddemo-data'))[1]}
        self.rows=[];self.cases=[];self.token=None;self.current=None;self.failures=[];self.validated_fields=set();self.case_id='';self.seen=set();self.sessions=count(1);self.session=0;self.quirks=[]
    def expected_state(self):
        state=deepcopy(self.initial)
        for record in self.engine.store.records:
            table=record['table'];layout,mapping=self.entries[table];ordinal=int(record['identity'].split(':')[1]);old=next(r for r in state[table] if r['source_ordinal']==ordinal)
            def raw(value):return bytes.fromhex(value[2:]) if value is not None else None
            row,children=Store(None,mapping,layout).project_rows(record['raw'],ordinal,parent_path=raw(old.get('parent_path_key')),twin_seq=old.get('twin_seq'),position=old.get('rba',old.get('slot')))
            for (child_table,child_ordinal),child in children.items():
                target=next(v for v in state[child_table] if v['source_ordinal']==ordinal and v['ordinal']==child_ordinal);target.update(child)
            old.update(row)
        state['authfrds']=deepcopy(self.engine.store.fraud)
        for row in state['authfrds']:
            row['auth_ts']=datetime.fromisoformat(row['auth_ts']).isoformat()
        return {table:sorted([canonical(row) for row in rows],key=lambda r:json.dumps(r,sort_keys=True)) for table,rows in state.items()}
    def step(self,aid,fields=None):
        fields=fields or {};before=self.engine.program
        expected=self.engine.step(aid,fields);self.seen.add(before);self.seen.add(expected['program']);state=self.expected_state()
        row=dict(case=self.case_id,session=self.session,aid=aid,fields=fields,expected=expected,database=state)
        # SEND TEXT has no BMS map: compare its complete text and ended state,
        # and disclose that there are zero BMS fields in this terminal response.
        if expected['ended']:row['terminal_text_only']=True
        if expected.get('outside_slice'):row['navigation_boundary_only']=True
        if not self.args.reference_only:
            body=json.dumps(dict(token=self.token,aid=aid,fields=fields)).encode()
            with urllib.request.urlopen(urllib.request.Request(self.args.url+'/api/interaction',body,{'Content-Type':'application/json'}),timeout=30) as response:actual=json.load(response)
            self.token=actual['token'];compare_frame(actual['screen'],expected);assert actual['ended']==expected['ended']
            observed=snapshot(self.out/'database');data=json.loads((self.out/'database'/observed['path']).read_bytes())
            for item in data['authfrds']:item['auth_ts']=datetime.fromisoformat(item['auth_ts']).isoformat()
            data={table:sorted([canonical(r) for r in rows],key=lambda r:json.dumps(r,sort_keys=True)) for table,rows in data.items()}
            assert data==state,dict(reason='PostgreSQL after-state differs',tables=[t for t in state if state[t]!=data.get(t)])
            row['actual']=actual['screen'];row['database_after_sha256']=digest(data)
        self.current=expected['screen'];self.rows.append(row);return expected
    def inputs(self):return {k:v.rstrip(' ') for k,v in self.current['values'].items() if not self.current['attributes'][k]['protected']}
    def start(self,case,option=None):
        self.case_id=case;self.session=next(self.sessions);self.engine.reset();self.token=None;self.step('INITIAL')
        self.step('ENTER',dict(USERID=self.fixture['user'],PASSWD=self.fixture['password']))
        if option:self.step('ENTER',{'OPTION':option})
    def case(self,name,body):
        begin=len(self.rows);self.case_id=name
        try:body();self.cases.append(dict(id=name,status='passed',interactions=len(self.rows)-begin))
        except Exception as error:
            self.failures.append(dict(case=name,error=type(error).__name__+': '+str(error)))
            self.cases.append(dict(id=name,status='failed',interactions=len(self.rows)-begin,error=type(error).__name__+': '+str(error),traceback=traceback.format_exc()))
            raise
    def run(self):
        for label,fields in [('blank-user',{}),('blank-password',{'USERID':self.fixture['user']}),('wrong-password',{'USERID':self.fixture['user'],'PASSWD':'WRONG'}),('user-not-found',{'USERID':'ZZZZZZZZ','PASSWD':'WRONG'})]:
            def body(label=label,fields=fields):
                self.case_id=label;self.session=next(self.sessions);self.engine.reset();self.token=None
                self.step('INITIAL');self.step('ENTER',fields);self.step('PF3')
            self.case(label,body)
        for aid in ('PF1','PF24'):
            def body(aid=aid):self.start('menu-'+aid);self.step(aid,{'OPTION':'11'});self.step('PF3')
            self.case('menu-'+aid,body)
        for label,value in [('blank',''),('zero','0'),('nonnumeric','XX'),('past-end','99')]:
            def body(label=label,value=value):
                self.start('menu-'+label);result=self.step('ENTER',{'OPTION':value})
                assert result['screen']['message'],'invalid menu did not emit validation message'
            self.case('menu-'+label,body)
        for option in range(3,11):
            def body(option=option):
                self.start('menu-outside-'+str(option));result=self.step('ENTER',{'OPTION':str(option)})
                assert result.get('outside_slice') and result.get('outside_program') not in PROGRAMS
            self.case('menu-outside-'+str(option),body)
        # Source-shaped invalid search fields, not-found and PF3 at each screen.
        for option,field in [('1','ACCTSID'),('2','ACCTSID'),('11','ACCTID')]:
            for label,value in [('blank',''),('zero','00000000000'),('nonnumeric','XXXXXXXXXXX'),('not-found','99999999999')]:
                def body(option=option,field=field,label=label,value=value):
                    self.start(option+'-'+label,option);self.step('ENTER',{field:value});self.step('PF3')
                self.case(option+'-'+label,body)
        def account_view():
            self.start('account-view','1');self.step('ENTER',{'ACCTSID':self.fixture['account']});self.step('PF3')
        self.case('account-view',account_view)
        # The validated field inventory is the actual unprotected update image.
        self.start('account-update-inventory','2');self.step('ENTER',{'ACCTSID':self.fixture['account']})
        inputs=self.inputs();fields=sorted(k for k in inputs if k!='ACCTSID');self.validated_fields.update(fields)
        for field in fields:
            for invalid in ('','!'):
                def body(field=field,invalid=invalid):
                    self.start('update-'+field+'-'+('blank' if not invalid else 'invalid'),'2');self.step('ENTER',{'ACCTSID':self.fixture['account']})
                    edited=self.inputs();edited[field]=invalid;self.step('ENTER',edited);self.step('PF3')
                self.case('update-'+field+'-'+('blank' if not invalid else 'invalid'),body)
        def unchanged():
            self.start('update-no-change','2');self.step('ENTER',{'ACCTSID':self.fixture['account']});self.step('ENTER',self.inputs());self.step('PF3')
        self.case('update-no-change',unchanged)
        for label,date_fields in [('leap-day-invalid',{'DOBYEAR':'1990','DOBMON':'02','DOBDAY':'29'}),('leap-day-valid',{'DOBYEAR':'2000','DOBMON':'02','DOBDAY':'29'})]:
            def body(label=label,date_fields=date_fields):
                self.start(label,'2');self.step('ENTER',{'ACCTSID':self.fixture['account']});edited=self.inputs()
                assert set(date_fields)<=set(edited);edited.update(date_fields);self.step('ENTER',edited);self.step('PF3')
            self.case(label,body)
        def authorizations():
            self.start('authorization-pages-and-fraud','11');self.step('ENTER',{'ACCTID':self.fixture['account']})
            self.step('PF7',self.inputs());self.step('PF8',self.inputs());self.step('PF8',self.inputs());self.step('PF7',self.inputs())
            fields=self.inputs();selection=next(k for k,v in fields.items() if len(self.current['values'][k])==1)
            fields[selection]='X';self.step('ENTER',fields);fields=self.inputs();fields[selection]='S';self.step('ENTER',fields)
            self.step('PF5',self.inputs());self.step('PF5',self.inputs());self.step('PF8',self.inputs());self.step('PF3');self.step('PF3')
        self.case('authorization-pages-and-fraud',authorizations)
        def prepare(name,new_name):
            self.start(name,'2');self.step('ENTER',{'ACCTSID':self.fixture['account']})
            changed=self.inputs();assert 'ACSFNAM' in changed
            changed['ACSFNAM']=new_name;self.step('ENTER',changed)
            adapter=self.engine.adapters['COACTUPC']
            assert adapter.values.condition('ACUP-CHANGES-OK-NOT-CONFIRMED'),'source did not reach confirmation state'
        def committed():
            prepare('update-committed','PROOFALPHA');self.step('PF5',self.inputs())
            assert {e['dataset'] for e in self.engine.store.events if e['operation']=='REWRITE'}=={'ACCTDAT','CUSTDAT'}
            self.step('PF3')
        self.case('update-committed',committed)
        def cancelled():
            prepare('update-cancelled','PROOFBETA');self.step('PF12',self.inputs())
            assert not any(e['operation']=='REWRITE' for e in self.engine.store.events);self.step('PF3')
        self.case('update-cancelled',cancelled)
        def conflict():
            prepare('update-conflict-reader','PROOFGAMMA')
            saved=(self.session,self.token,self.engine.program,self.engine.area,deepcopy(self.current))
            prepare('update-conflict-writer','PROOFDELTA');self.step('PF5',self.inputs());self.step('PF3')
            self.session,self.token,self.engine.program,self.engine.area,self.current=saved;self.engine.frame=deepcopy(self.current)
            self.case_id='update-conflict-reader';self.step('PF5',self.inputs())
            assert self.engine.adapters['COACTUPC'].values.condition('DATA-WAS-CHANGED-BEFORE-UPDATE')
            assert not any(e['operation']=='REWRITE' for e in self.engine.store.events);self.step('PF3')
        self.case('update-conflict',conflict)
        assert self.seen==set(PROGRAMS),self.seen
        assert self.validated_fields,'empty validated-field denominator' 
    def save(self,passed):
        (self.out/'cases.json').write_text(json.dumps(self.rows,indent=2,default=str)+'\n')
        (self.out/'summary.json').write_text(json.dumps(dict(schema='carddemo-six-screen-proof/1',passed=passed,
            head=__import__('os').environ.get('GITHUB_SHA'),programs_compared=sorted(self.seen),required_programs=PROGRAMS,
            cases=self.cases,interactions_compared=len(self.rows),bms_interactions_compared=sum(not r.get('terminal_text_only') and not r.get('navigation_boundary_only') for r in self.rows),navigation_boundaries=[dict(case=r['case'],destination=r['expected']['outside_program']) for r in self.rows if r.get('navigation_boundary_only')],
            completed_case_count=len(self.cases),planned_case_count=len(self.cases) if passed else None,case_denominator_status='complete generated suite' if passed else 'not fully enumerated after failure; no completion claim',validated_fields=sorted(self.validated_fields),
            source_faults=[dict(case=r['case'],failure=r['expected']['source_fault'],trace=r['expected']['trace']) for r in self.rows if r['expected'].get('source_fault')],
            bounded_date_cases=['leap-day-invalid','leap-day-valid'],
            shared_dependencies=['BMS parser','physical data plan and typed projection codec'],
            full_slice_screen_equivalence=passed,terminal_text_contract='SEND TEXT compares complete message and ended state; no BMS fields exist in that source response',remaining=self.failures),indent=2)+'\n')

def main():
    p=argparse.ArgumentParser();p.add_argument('--fixture',type=Path,required=True);p.add_argument('--raw-fixture',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--url',default='http://127.0.0.1:8080');p.add_argument('--reference-only',action='store_true');a=p.parse_args()
    proof=Proof(a);passed=False
    try:proof.run();passed=True
    finally:proof.save(passed)
if __name__=='__main__':main()
