"""Compose API smoke, not the independent screen-equivalence gate."""
import argparse,json,time,urllib.request,urllib.error
from pathlib import Path
from snapshot import snapshot

parser=argparse.ArgumentParser();parser.add_argument('--fixture',type=Path,required=True);parser.add_argument('--url',default='http://127.0.0.1:8080');parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
fixture=json.loads(args.fixture.read_bytes());token=None;current=None;frames=[];previous_state=None
def step(aid,fields=None,program=None):
    global token,current,previous_state
    body=json.dumps(dict(token=token,aid=aid,fields=fields or {})).encode()
    request=urllib.request.Request(args.url+'/api/interaction',body,{'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=30) as response:result=json.load(response)
    token=result['token'];current=result['screen']
    if program:assert current['program']==program,(aid,current['program'],program)
    assert set(current['values'])==set(current['attributes'])
    for field in current['model']['fields']:
        if field['name']:assert len(current['values'][field['name']])==field['length'],field['name']
    after=snapshot(args.out/'database')
    if previous_state is not None:
        changed={t for t,h in after['tables'].items() if h!=previous_state['tables'].get(t)}
        expected={'pautdtl1','authfrds'} if aid=='PF5' and current['program']=='COPAUS1C' else set()
        assert changed==expected,dict(aid=aid,changed=sorted(changed),expected=sorted(expected))
    previous_state=after
    frames.append(dict(aid=aid,screen=current,ended=result['ended'],source_hash=result['sourceHash'],database_after=after))
    return current

def inputs():return {k:v.rstrip(' ') for k,v in current['values'].items() if not current['attributes'][k]['protected']}

args.out.mkdir(parents=True,exist_ok=True)
try:
    for attempt in range(120):
        try:step('INITIAL',program='COSGN00C');break
        except (urllib.error.URLError,TimeoutError):
            if attempt==119:raise
            time.sleep(2)
    step('ENTER',{},'COSGN00C');assert current['cursor']=='USERID'
    step('ENTER',{'USERID':fixture['user'],'PASSWD':'WRONG'},'COSGN00C');assert current['cursor']=='PASSWD'
    step('ENTER',{'USERID':fixture['user'],'PASSWD':fixture['password']},'COMEN01C')
    step('ENTER',{'OPTION':'1'},'COACTVWC');step('ENTER',{'ACCTSID':fixture['account']},'COACTVWC')
    assert not current['message'],current['message']
    step('PF3',program='COMEN01C');step('ENTER',{'OPTION':'2'},'COACTUPC')
    step('ENTER',{'ACCTSID':fixture['account']},'COACTUPC')
    assert not current['message'],current['message']
    step('ENTER',inputs(),'COACTUPC')
    step('PF3',program='COMEN01C');step('ENTER',{'OPTION':'11'},'COPAUS0C')
    step('ENTER',{'ACCTID':fixture['account']},'COPAUS0C')
    assert not current['message'],current['message']
    step('PF8',inputs(),'COPAUS0C');step('PF7',inputs(),'COPAUS0C')
    selections=[f['name'] for f in current['model']['fields'] if f['name'] and f['length']==1 and not current['attributes'][f['name']]['protected']]
    assert selections,'authorization selection absent'
    data=inputs();data[selections[0]]='S';step('ENTER',data,'COPAUS1C')
    step('PF5',inputs(),'COPAUS1C');assert current['message']=='AUTH MARKED FRAUD...',current['message']
    step('PF5',inputs(),'COPAUS1C');assert current['message']=='AUTH FRAUD REMOVED...',current['message']
    step('PF8',inputs(),'COPAUS1C');step('PF3',program='COPAUS0C')
    step('PF3',program='COMEN01C');step('ENTER',{'OPTION':'3'},'COMEN01C');assert current['endpoint']=='/not-in-this-slice'
    step('PF3',program='COSGN00C');step('PF3',program='COSGN00C');assert token is None
    (args.out/'summary.json').write_text(json.dumps(dict(passed=True,interactions=len(frames),programs=sorted({f['screen']['program'] for f in frames}),screen_equivalence_verified=False,baseline='runtime smoke assertions only'),indent=2)+'\n')
finally:
    (args.out/'frames.json').write_text(json.dumps(frames,indent=2)+'\n')
