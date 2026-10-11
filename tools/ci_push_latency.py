"""Read-only final-head PR gate timing; exact push time only from PushEvent."""
import argparse,json,subprocess
from datetime import datetime,timezone
from pathlib import Path

REPO='howardweale/lightyear-carddemo-modernization'

def api(path):return json.loads(subprocess.check_output(['gh','api','repos/'+REPO+'/'+path],text=True))

def pages(path,key=None):
    rows=[]
    for n in range(1,101):
        data=api(path+('&' if '?' in path else '?')+f'per_page=100&page={n}');page=data[key] if key else data
        rows.extend(page)
        if len(page)<100:return rows
    raise RuntimeError('pagination bound')

def elapsed(start,end):return (datetime.fromisoformat(end.replace('Z','+00:00'))-datetime.fromisoformat(start.replace('Z','+00:00'))).total_seconds()

def summarize(pr,runs,push_events):
    head=pr['head']['sha']; latest={}
    for r in runs:
        if r['head_sha']!=head or r['event']!='pull_request' or not any(x['number']==pr['number'] for x in r.get('pull_requests',[])):continue
        path=r['path'].split('@')[0]
        if r['id']>latest.get(path,{}).get('id',-1):latest[path]=r
    green=bool(latest) and '.github/workflows/required-ci.yml' in latest and all(r['status']=='completed' and r['conclusion']=='success' for r in latest.values())
    pushes=[e['created_at'] for e in push_events if e.get('type')=='PushEvent' and e.get('payload',{}).get('head')==head and e['payload'].get('ref')=='refs/heads/'+pr['head']['ref']]
    pushed=min(pushes) if pushes else None
    earliest=min((r['created_at'] for r in latest.values()),default=None)
    completed=max((r['updated_at'] for r in latest.values()),default=None) if green else None
    return dict(pr=pr['number'],head=head,green=green,push_at=pushed,push_time_source='GitHub PushEvent' if pushed else 'exact push event unavailable',
        all_workflows_green_at=completed,push_to_green_seconds=elapsed(pushed,completed) if pushed and completed else None,
        earliest_workflow_created_at=earliest,workflow_creation_to_green_seconds=elapsed(earliest,completed) if earliest and completed else None,
        workflow_proxy_is_not_push_time=True,workflows=[{k:r.get(k) for k in ('id','path','status','conclusion','created_at','updated_at')} for r in latest.values()])

def collect(numbers):
    # GitHub repository Events is retention-limited; never replace a missing push
    # timestamp with a commit author timestamp or claim the proxy is exact.
    events=pages('events');rows=[]
    for number in numbers:
        pr=api(f'pulls/{number}');runs=pages('actions/runs?head_sha='+pr['head']['sha']+'&event=pull_request','workflow_runs')
        rows.append(summarize(pr,runs,events))
    queued=pages('actions/runs?status=queued','workflow_runs');active=pages('actions/runs?status=in_progress','workflow_runs')
    return dict(schema='pr-push-gate-latencies/1',checked_at=datetime.now(timezone.utc).isoformat(),prs=rows,
                queued_workflows=len(queued),active_workflows=len(active),post_merge_latency=False)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--prs',nargs='+',type=int,default=[311,312,313,314,315]);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();result=collect(a.prs)
    if a.output.exists():result['delivered_notifications']=json.loads(a.output.read_bytes()).get('delivered_notifications',[])
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n')
