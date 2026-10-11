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

def expected_workflows(files, directory=Path('.github/workflows')):
    return {p.as_posix() for p in directory.glob('*.yml') if p.name != 'required-ci.yml'
            and selected(yaml.load(p.read_text(),Loader=yaml.BaseLoader),files)}

def evaluate(expected,runs,head,pr_number):
    latest={}
    for run in runs:
        if run['head_sha'] != head or run['event'] != 'pull_request':
            continue
        if not any(p['number']==pr_number for p in run.get('pull_requests',[])):
            continue
        path=run['path'].split('@')[0]
        if path in expected and run['id'] > latest.get(path,{}).get('id',-1):
            latest[path]=run
    failed=sorted(p for p,r in latest.items() if r['status']=='completed' and r['conclusion']!='success')
    waiting=sorted(p for p in expected if p not in latest or latest[p]['status']!='completed')
    return failed,waiting

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
    files=[f['filename'] for f in pages(f'{prefix}/pulls/{number}/files')]
    if len(files)!=pr['changed_files']:
        raise SystemExit('Incomplete GitHub changed-file inventory; refuse gate')
    expected=expected_workflows(files)
    print('Required workflows:',sorted(expected),flush=True)
    deadline=time.monotonic()+3600
    while time.monotonic()<deadline:
        if api(f'{prefix}/pulls/{number}')['head']['sha']!=head:
            raise SystemExit('PR head changed; obsolete gate refused')
        runs=pages(f'{prefix}/actions/runs?head_sha={head}&event=pull_request','workflow_runs')
        failed,waiting=evaluate(expected,runs,head,number)
        if failed:
            raise SystemExit('Required workflow failed/cancelled/skipped: '+', '.join(failed))
        if not waiting:
            print('All selected final-head workflows completed green.',flush=True)
            return
        print('Waiting:',', '.join(waiting),flush=True)
        time.sleep(30)
    raise SystemExit('CI timed out; missing/queued/running is not acceptance')

def lint():
    for p in Path('.github/workflows').glob('*.yml'):
        d=yaml.load(p.read_text(),Loader=yaml.BaseLoader)
        assert 'on' in d and 'jobs' in d,p
        assert not re.search(r'\b(?:ubuntu|windows|macos)-latest\b',p.read_text()),p
        assert "github.ref != 'refs/heads/main'" in d['concurrency']['cancel-in-progress'],p
        assert 'github.run_id' in d['concurrency']['group'],p
    files=subprocess.check_output(['git','diff','--name-only','--diff-filter=ACMR',os.environ['BASE_SHA'],'HEAD'],text=True).splitlines()
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
