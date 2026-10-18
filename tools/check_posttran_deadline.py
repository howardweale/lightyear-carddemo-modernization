"""Evaluate the live UTC deadline; optional issue maintenance is CI-only."""
import argparse
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from tools.check_posttran_handoff import check, timing, deadline, READINESS

MARKER = '<!-- posttran-sign-and-launch-deadline -->'

def withdrawn(root, ready):
    """Only an explicit hash-bound withdrawal retires the active warning."""
    root=Path(root)
    expected=sha256((root/READINESS).read_bytes()).hexdigest()
    for path in (root/'docs/factory').glob('posttran-phase2-readiness-supersession-*.json'):
        row=json.loads(path.read_bytes())
        if row.get('schema') != 'posttran-readiness-supersession/1': continue
        if row.get('supersedes_sha256') != expected: continue
        if date.fromisoformat(row['prepared_on']) <= date.fromisoformat(ready['prepared_on']):
            raise ValueError('deadline-supersession-date')
        if row.get('withdrawn') is True: return True
    return False


def consumed(repository, plan_sha, run=subprocess.check_output):
    # A read-only ref lookup. This tool never creates a consumption tag.
    result=json.loads(run(['gh','api','repos/'+repository+'/git/matching-refs/tags/posttran-phase2-consumed-'+plan_sha]))
    return any(r['ref']=='refs/tags/posttran-phase2-consumed-'+plan_sha for r in result)


def evaluate(root, now=None, *, was_consumed=False):
    ready = check(root)
    value=timing(ready, now)
    state='consumed' if was_consumed else 'superseded' if withdrawn(root,ready) else 'expired' if value['expired'] else 'warning' if value['warning'] else 'open'
    value.update(state=state,terminal=state in {'consumed','superseded','expired'},execution_authorized=False)
    return ready, value

def issue_body(ready, value):
    if value['terminal']:
        detail={'expired':'expired - fresh preparation required','consumed':'attempt consumed; warning closed',
                'superseded':'readiness superseded; warning closed'}[value['state']]
        return (MARKER+'\n<!-- posttran-deadline-state:'+value['state']+' -->\nPOSTTRAN: '+detail
                +'. Window end: '+deadline(ready)+'. No signing or execution authorized.')
    return (MARKER + '\nPOSTTRAN: sign and launch before ' + deadline(ready)
            + ' (exclusive). Evaluated at ' + value['evaluated_at']
            + '. The reserve authorization check must start before the window ends; queued jobs can miss it.'
            + '\nNo signing, execution, retry or attempt consumption is authorized by this issue.')

def upsert_issue(repository, body, run=subprocess.check_output, *, terminal=False):
    prefix = 'repos/' + repository
    rows = []
    for page in range(1, 101):
        batch = json.loads(run(['gh', 'api', prefix + f'/issues?state=all&per_page=100&page={page}']))
        rows.extend(batch)
        if len(batch) < 100: break
    else: raise ValueError('deadline-issue-pagination-bound')
    matches = [r for r in rows if 'pull_request' not in r and MARKER in (r.get('body') or '')]
    if len(matches) > 1: raise ValueError('deadline-issue-ambiguous')
    if terminal and not matches and 'posttran-deadline-state:expired' not in body:
        return None
    if terminal and matches and matches[0].get('state')=='closed' and matches[0].get('body')==body:
        return matches[0]
    route = prefix + '/issues' + ('/' + str(matches[0]['number']) if matches else '')
    payload = dict(title='POSTTRAN: handoff window closed' if terminal else 'POSTTRAN: sign and launch deadline approaching', body=body, state='closed' if terminal else 'open')
    result=json.loads(run(['gh','api',route,'--method','PATCH' if matches else 'POST','--input','-'], input=json.dumps(payload).encode()))
    if terminal and not matches:
        result=json.loads(run(['gh','api',prefix+'/issues/'+str(result['number']),'--method','PATCH','--input','-'],
                              input=json.dumps(dict(state='closed')).encode()))
    return result

def main(argv=None, now=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=Path('.'))
    p.add_argument('--issue-repository')
    args=p.parse_args(argv)
    ready=check(args.root)
    was_consumed=consumed(args.issue_repository,ready['plan_sha256']) if args.issue_repository else False
    ready,value=evaluate(args.root,now,was_consumed=was_consumed)
    print(json.dumps(value))
    if value['terminal']:
        message=issue_body(ready,value); print(message)
        if args.issue_repository: upsert_issue(args.issue_repository,message,terminal=True)
        return 0
    if value['warning']:
        message=issue_body(ready,value)
        print('POSTTRAN DEADLINE WARNING: '+message)
        if args.issue_repository: upsert_issue(args.issue_repository,message)
        return 1
    return 0

if __name__ == '__main__': raise SystemExit(main())
