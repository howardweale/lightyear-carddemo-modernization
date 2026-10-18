"""CI-only raw sign-on/menu comparisons; the other four screens remain unproved."""
import argparse,json,urllib.request
from pathlib import Path
from hashlib import sha256
from lightyear_data.carddemo.reference_signon import SignonReference
from lightyear_data.carddemo.reference_menu import MenuReference
from snapshot import snapshot


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);parser.add_argument('--url',default='http://127.0.0.1:8080');args=parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    source=Path('spec/modernization/carddemo-screens/upstream');reference=SignonReference(source);memory=reference.storage()
    data=Path('spec/modernization/carddemo-data/upstream/app/data/EBCDIC/AWS.M2.CARDDEMO.USRSEC.PS').read_bytes()
    width=memory.descriptor('SEC-USER-DATA')[1]['length'];assert len(data)%width==0
    users={}
    for at in range(0,len(data),width):
        raw=data[at:at+width];memory.write('SEC-USER-DATA',raw.decode('cp037'));users[memory.read('SEC-USR-ID')]=raw
    reference.users=users;user=next(iter(users));memory.write('SEC-USER-DATA',users[user].decode('cp037'))
    password=memory.read('SEC-USR-PWD');missing='ZZZZZZZZ';assert missing not in users
    wrong='WRONGPWD' if password!='WRONGPWD' else 'DIFFERNT'
    cases=[dict(id='blank-user',aid='ENTER',fields={}),dict(id='blank-password',aid='ENTER',fields={'USERID':user}),
           dict(id='not-found',aid='ENTER',fields={'USERID':missing,'PASSWD':password}),
           dict(id='wrong-password',aid='ENTER',fields={'USERID':user,'PASSWD':wrong}),dict(id='invalid-aid',aid='PF1',fields={})]
    rows=[];baseline=snapshot(args.out/'database')
    def request(token,aid,fields):
        raw=json.dumps(dict(token=token,aid=aid,fields=fields)).encode()
        with urllib.request.urlopen(urllib.request.Request(args.url+'/api/interaction',raw,{'Content-Type':'application/json'}),timeout=30) as response:return json.load(response)
    def compare(actual,expected):
        assert actual['screen']['program']==expected['program']
        assert actual['ended']==expected['ended']
        for part in ('values','attributes','cursor','message'):
            assert actual['screen'][part]==expected['screen'][part],dict(part=part,actual=actual['screen'][part],expected=expected['screen'][part])
        after=snapshot(args.out/'database');assert after['tables']==baseline['tables'],'Sign-on changed PostgreSQL after-state'
        return after
    try:
        for case in cases:
            expected_initial=reference.interact('INITIAL');initial=request(None,'INITIAL',{})
            initial_state=compare(initial,expected_initial)
            expected=reference.interact(case['aid'],case['fields']);actual=request(initial['token'],case['aid'],case['fields'])
            after=compare(actual,expected)
            rows.append(dict(case,initial=expected_initial,expected=expected,database_after=after,initial_database=initial_state))
        menu=MenuReference(source)
        regular=None
        for name,raw in users.items():
            memory.write('SEC-USER-DATA',raw.decode('cp037'))
            if memory.read('SEC-USR-TYPE')=='U':
                regular=dict(USERID=name,PASSWD=memory.read('SEC-USR-PWD'));break
        assert regular is not None,'Public regular-user fixture absent'
        for aid,fields in [('PF1',{'OPTION':'11'}),('PF24',{})]:
            expected_signon=reference.interact('INITIAL');initial=request(None,'INITIAL',{});initial_state=compare(initial,expected_signon)
            transfer=reference.interact('ENTER',regular);assert transfer['program']=='COMEN01C'
            expected_initial=menu.interact('INITIAL',commarea=transfer['commarea']);logged_in=request(initial['token'],'ENTER',regular)
            login_state=compare(logged_in,expected_initial)
            expected=menu.interact(aid,fields,expected_initial['commarea']);actual=request(logged_in['token'],aid,fields);after=compare(actual,expected)
            rows.append(dict(id='menu-'+aid.lower(),aid=aid,fields=fields,login=regular,signon=expected_signon,
                initial=expected_initial,expected=expected,database_after=after,initial_database=initial_state,login_database=login_state))
        summary=dict(schema='carddemo-screen-comparison/1',passed=True,baseline='raw pinned COSGN00C and COMEN01C interpreter with explicit CICS adapters',
            programs_compared=['COSGN00C','COMEN01C'],required_programs=6,interactions_compared=sum(3 if 'login' in row else 2 for row in rows),cases_compared=len(rows),
            all_fields_attributes_cursor_message=True,postgres_after_state='all tables unchanged after every interaction',
            source_sha256={reference.program_name:sha256(reference.raw).hexdigest(),menu.program_name:sha256(menu.raw).hexdigest()},fixture_sha256=sha256(data).hexdigest(),
            full_slice_screen_equivalence=False,screen_handler_mutation_gate=False,remaining=['Four screen adapters','Complete success/update/conflict journeys','Screen-handler mutation denominator','Pinned menu indexes an invalid option after displaying the error; reference fails closed at the invalid subscript'])
        (args.out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    finally:
        (args.out/'cases.json').write_text(json.dumps(rows,indent=2)+'\n')

if __name__=='__main__':main()