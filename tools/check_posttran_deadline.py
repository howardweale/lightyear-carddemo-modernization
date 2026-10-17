"""Evaluate the live UTC deadline; optional issue maintenance is CI-only."""
import argparse
import json
from pathlib import Path
import subprocess
from tools.check_posttran_handoff import check, timing, deadline

MARKER = '<!-- posttran-sign-and-launch-deadline -->'

def evaluate(root, now=None):
    ready = check(root)
    return ready, timing(ready, now)

def issue_body(ready, value):
    return (MARKER + '\nPOSTTRAN: sign and launch before ' + deadline(ready)
            + ' (exclusive). Evaluated at ' + value['evaluated_at']
            + '. The reserve authorization check must start before the window ends; queued jobs can miss it.'
            + '\nNo signing, execution, retry or attempt consumption is authorized by this issue.')

def upsert_issue(repository, body, run=subprocess.check_output):
    prefix = 'repos/' + repository
    rows = []
    for page in range(1, 101):
        batch = json.loads(run(['gh', 'api', prefix + f'/issues?state=all&per_page=100&page={page}']))
        rows.extend(batch)
        if len(batch) < 100: break
    else: raise ValueError('deadline-issue-pagination-bound')
    matches = [r for r in rows if 'pull_request' not in r and MARKER in (r.get('body') or '')]
    if len(matches) > 1: raise ValueError('deadline-issue-ambiguous')
    route = prefix + '/issues' + ('/' + str(matches[0]['number']) if matches else '')
    payload = dict(title='POSTTRAN: sign and launch deadline approaching', body=body, state='open')
    return json.loads(run(['gh','api',route,'--method','PATCH' if matches else 'POST','--input','-'], input=json.dumps(payload).encode()))

def main(argv=None, now=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=Path('.'))
    p.add_argument('--issue-repository')
    args=p.parse_args(argv)
    ready,value=evaluate(args.root,now)
    print(json.dumps(value))
    if value['warning']:
        message=issue_body(ready,value)
        print('POSTTRAN DEADLINE WARNING: '+message)
        if args.issue_repository: upsert_issue(args.issue_repository,message)
        return 1
    return 0

if __name__ == '__main__': raise SystemExit(main())
