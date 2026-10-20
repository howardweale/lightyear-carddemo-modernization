"""Require completed green selected workflows on the exact PR head."""
import ast
import re
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import yaml

def selected(config, files):
    events = config.get('on', {})
    if isinstance(events, (str,list)):
        return 'pull_request' in events
    if 'pull_request' not in events:
        return False
    rule = events['pull_request'] or {}
    def matches(path, pattern):
        expr='';i=0
        while i<len(pattern):
            if pattern[i:i+3]=='**/': expr+='(?:.*/)?';i+=3
            elif pattern[i:i+2]=='**': expr+='.*';i+=2
            elif pattern[i]=='*': expr+='[^/]*';i+=1
            elif pattern[i]=='?': expr+='[^/]';i+=1
            else: expr+=re.escape(pattern[i]);i+=1
        return re.fullmatch(expr,path) is not None
    if 'paths' in rule:
        def included(path):
            include = False
            for pattern in rule['paths']:
                if matches(path, pattern.lstrip('!')):
                    include = not pattern.startswith('!')
            return include
        return any(included(path) for path in files)
    return any(not any(matches(p,q) for q in rule.get('paths-ignore',[])) for p in files)

def expected_workflows(files, directory=Path('.github/workflows'), *, head=None):
    if head is not None:
        names = subprocess.check_output(['git','ls-tree','-r','--name-only',head,'--','.github/workflows'],text=True).splitlines()
        return {name for name in names if name.endswith('.yml') and Path(name).name != 'required-ci.yml'
                and selected(yaml.load(subprocess.check_output(['git','show',head+':'+name],text=True),Loader=yaml.BaseLoader),files)}
    return {p.as_posix() for p in directory.glob('*.yml') if p.name != 'required-ci.yml'
            and selected(yaml.load(p.read_text(),Loader=yaml.BaseLoader),files)}

def latest_runs(expected, runs, head, pr_number):
    """Actions lists one run with its latest attempt, not one row per attempt."""
    latest = {}
    for run in runs:
        if run['head_sha'] != head or run['event'] != 'pull_request':
            continue
        if not any(p['number'] == pr_number for p in run.get('pull_requests', [])):
            continue
        path = run['path'].split('@')[0]
        previous = latest.get(path)
        if path in expected and (previous is None or (run['id'], run.get('run_attempt', 1)) >
                                 (previous['id'], previous.get('run_attempt', 1))):
            latest[path] = run
    return latest


def evaluate(expected, runs, head, pr_number):
    latest = latest_runs(expected, runs, head, pr_number)
    failed = sorted(p for p,r in latest.items() if r['status'] == 'completed' and r['conclusion'] != 'success')
    waiting = sorted(p for p in expected if p not in latest or latest[p]['status'] != 'completed')
    return failed, waiting


class TerminalStability:
    """Give a requested but not yet registered rerun a bounded observation window.

    This cannot predict a rerun requested after acceptance. The final decision
    uses freshly read run IDs/attempts, then requires a stable terminal window.
    """
    def __init__(self, seconds=60):
        self.seconds = seconds
        self.snapshot = None
        self.since = None

    def ready(self, selected, waiting, now):
        if waiting:
            self.snapshot = self.since = None
            return False
        snapshot = tuple(sorted((path, r['id'], r.get('run_attempt',1), r['status'], r['conclusion'])
                                for path,r in selected.items()))
        if snapshot != self.snapshot:
            self.snapshot, self.since = snapshot, now
            return False
        return now-self.since >= self.seconds


def current_files(prefix, number, head):
    """Bind paginated files to live head/base/count; webhook counts can be stale."""
    before = api(f'{prefix}/pulls/{number}')
    rows = pages(f'{prefix}/pulls/{number}/files')
    after = api(f'{prefix}/pulls/{number}')
    identity = lambda p:(p['head']['sha'],p['base']['sha'],p['base']['ref'],p['changed_files'])
    if before['head']['sha'] != head or identity(before) != identity(after):
        raise SystemExit('PR head/base changed during file inventory; obsolete snapshot refused')
    files = [row['filename'] for row in rows]
    if len(files) != before['changed_files'] or len(set(files)) != len(files):
        raise SystemExit('Incomplete GitHub changed-file inventory; refuse gate')
    return files, identity(after)


def api(endpoint):
    return json.loads(subprocess.check_output(['gh','api',endpoint],text=True))

def pages(endpoint,key=None):
    result=[]
    for page in range(1,101):
        d=api(endpoint+('&' if '?' in endpoint else '?')+f'per_page=100&page={page}')
        rows=d[key] if key else d
        result.extend(rows)
        if len(rows)<100:
            return result
    raise RuntimeError('API pagination bound exceeded')

def gate():
    if os.environ['LINT_RESULT']!='success':
        raise SystemExit('documentation/lint did not pass')
    event=json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    if 'pull_request' not in event:
        print('Main push: individual workflow results remain authoritative; no PR merge authorized.')
        return
    pr=event['pull_request']; number=pr['number']; head=pr['head']['sha']
    prefix='repos/'+os.environ['GITHUB_REPOSITORY']
    files, identity = current_files(prefix, number, head)
    expected=expected_workflows(files, head=head)
    print('Required workflows:',sorted(expected),flush=True)
    stability = TerminalStability()
    deadline=time.monotonic()+12600
    while time.monotonic()<deadline:
        current = api(f'{prefix}/pulls/{number}')
        if (current['head']['sha'],current['base']['sha'],current['base']['ref'],current['changed_files']) != identity:
            raise SystemExit('PR head/base changed; obsolete gate refused')
        runs=pages(f'{prefix}/actions/runs?head_sha={head}&event=pull_request','workflow_runs')
        selected_runs = latest_runs(expected, runs, head, number)
        failed,waiting=evaluate(expected,list(selected_runs.values()),head,number)
        if not waiting:
            # A list response can lag registration of a rerun. Read each run's
            # latest attempt directly before either green or terminal failure.
            fresh = [api(f"{prefix}/actions/runs/{run['id']}") for run in selected_runs.values()]
            selected_runs = latest_runs(expected, fresh, head, number)
            failed,waiting=evaluate(expected,fresh,head,number)
        terminal = stability.ready(selected_runs, waiting, time.monotonic())
        if terminal and failed:
            raise SystemExit('Required workflow failed/cancelled/skipped: '+', '.join(failed))
        if terminal and not failed:
            # A new run ID can also arrive while direct reads were in flight.
            final = latest_runs(expected, pages(f'{prefix}/actions/runs?head_sha={head}&event=pull_request','workflow_runs'), head, number)
            _, final_waiting = evaluate(expected,list(final.values()),head,number)
            if not stability.ready(final, final_waiting, time.monotonic()):
                continue
            current = api(f'{prefix}/pulls/{number}')
            if (current['head']['sha'],current['base']['sha'],current['base']['ref'],current['changed_files']) != identity:
                raise SystemExit('PR head/base changed before acceptance; obsolete gate refused')
            print('All selected final-head workflows completed green.',flush=True)
            return
        print('Waiting:',', '.join(waiting),'Completed failures:',', '.join(failed),flush=True)
        time.sleep(30)
    raise SystemExit('CI timed out; missing/queued/running is not acceptance')

def lint():
    for p in Path('.github/workflows').glob('*.yml'):
        d=yaml.load(p.read_text(),Loader=yaml.BaseLoader)
        assert 'on' in d and 'jobs' in d,p
        assert not re.search(r'\b(?:ubuntu|windows|macos)-latest\b',p.read_text()),p
        if p.name=='posttran-phase2.yml':
            # One reservation and comparison at a time; cancelling an admitted run
            # would consume its only attempt without finishing the evidence.
            assert d['concurrency']=={'group':'posttran-phase2-attempt-1','cancel-in-progress':'false'},p
        else:
            assert (p.name=='factory-systematic-review.yml' and d['concurrency']['cancel-in-progress']=='false') or "github.ref != 'refs/heads/main'" in d['concurrency']['cancel-in-progress'],p
            assert 'github.run_id' in d['concurrency']['group'],p
    files=subprocess.check_output(['git','diff','--name-only','--diff-filter=ACMR',os.environ['BASE_SHA'],'HEAD'],text=True).splitlines()
    from tools.check_source_lf import check_paths
    check_paths(Path.cwd(), files)
    for name in files:
        p=Path(name)
        if not p.is_file(): continue
        if p.suffix=='.py': ast.parse(p.read_bytes(),filename=name)
        if p.suffix in ('.md','.yml','.yaml'):
            if any(line.startswith(('<<<<<<< ','=======','>>>>>>> ')) for line in p.read_text(encoding='utf-8').splitlines()):
                raise ValueError('merge marker in '+name)
    print('Workflow policy, changed Python syntax and text conflict checks passed.')

if __name__=='__main__':
    {'gate':gate,'lint':lint}[sys.argv[1]]()
