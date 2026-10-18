"""CI-only API comparisons against raw COSGN00C; five other screens unproved."""
import argparse,json,urllib.request
from pathlib import Path
from hashlib import sha256
from lightyear_data.carddemo.reference_signon import SignonReference
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
        summary=dict(schema='carddemo-screen-comparison/1',passed=True,baseline='raw pinned COSGN00C interpreter with explicit CICS adapter',
            programs_compared=['COSGN00C'],required_programs=6,interactions_compared=2*len(rows),cases_compared=len(rows),
            all_fields_attributes_cursor_message=True,postgres_after_state='all tables unchanged after every interaction',
            source_sha256=sha256(reference.raw).hexdigest(),fixture_sha256=sha256(data).hexdigest(),
            full_slice_screen_equivalence=False,screen_handler_mutation_gate=False,remaining=['Five screen adapters','Complete success/update/conflict journeys','Screen-handler mutation denominator'])
        (args.out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    finally:
        (args.out/'cases.json').write_text(json.dumps(rows,indent=2)+'\n')

if __name__=='__main__':main()