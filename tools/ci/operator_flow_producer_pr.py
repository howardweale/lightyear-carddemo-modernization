"""Proposed CI-only disposable producer gate; no publication or admission authority.

Configuration is an externally reviewed job-start snapshot, not live revocation.
Pure relationships authenticate nothing. The live entry constructs the native API.
"""
import hashlib, os, re, stat, subprocess, sys
from pathlib import Path
from tools.ci.operator_flow_handoff import require, strict_json, REPOSITORY

WORKFLOW = '.github/workflows/operator-flow-producer.yml'
JOB = 'operator-producer'
LABEL = 'operator-rehearsal-producer'
CONFIG = 'OPERATOR_PRODUCER_APPROVAL_JSON'


def parse_approval(raw):
    require(type(raw) is str and 0 < len(raw) <= 8192, 'producer-fixture-config-size')
    value = strict_json(raw.encode('utf-8'))
    require(type(value) is dict and set(value) == {
        'executable', 'expected_main', 'validation_run_id', 'pr_number',
        'fixture_only', 'scope', 'trigger_label'}, 'producer-fixture-config-fields')
    require(value['fixture_only'] is True
        and value['scope'] == 'disposable-producer-only'
        and value['trigger_label'] == LABEL, 'producer-fixture-config-scope')
    require(all(type(value[k]) is str and re.fullmatch('[0-9a-f]{40}', value[k])
        for k in ('executable', 'expected_main')), 'producer-fixture-config-heads')
    require(all(type(value[k]) is int and 0 < value[k] < 10**20
        for k in ('validation_run_id', 'pr_number')), 'producer-fixture-config-ids')
    return value


def read_approval():
    return parse_approval(os.environ.get(CONFIG, ''))


def relationships(event, run, job, live, approval, run_id):
    # Untrusted record relationships only; never passed context or authority.
    head = approval['executable']; number = approval['pr_number']
    require(type(event) is dict and event.get('action') == 'labeled'
        and event.get('label', {}).get('name') == LABEL, 'producer-pr-event')
    require(type(event.get('number')) is int and event['number'] == number
        and event.get('repository', {}).get('full_name') == REPOSITORY,
        'producer-pr-number')
    for value in (event.get('pull_request', {}), live):
        require(type(value) is dict and type(value.get('number')) is int
            and value['number'] == number and value.get('state') == 'open'
            and value.get('head', {}).get('sha') == head
            and value.get('head', {}).get('repo', {}).get('full_name') == REPOSITORY
            and value.get('base', {}).get('repo', {}).get('full_name') == REPOSITORY,
            'producer-live-pr-at-E')
    require(type(run_id) is int and 0 < run_id < 10**20
        and type(run.get('id')) is int and run['id'] == run_id
        and run.get('event') == 'pull_request' and run.get('status') == 'in_progress'
        and type(run.get('run_attempt')) is int and run['run_attempt'] == 1
        and run.get('head_repository', {}).get('full_name') == REPOSITORY
        and type(run.get('workflow_id')) is int and run['workflow_id'] > 0,
        'producer-original-pr-run')
    # Original service values must match. Never normalize merge revisions to E.
    require(run.get('head_sha') == head and job.get('head_sha') == head,
        'producer-service-head')
    require(type(job.get('id')) is int and job['id'] > 0
        and type(job.get('run_id')) is int and job['run_id'] == run_id
        and job.get('name') == JOB and job.get('status') == 'in_progress'
        and ('run_attempt' not in job or type(job['run_attempt']) is int
            and job['run_attempt'] == 1), 'producer-original-pr-job')


def _event_bytes(path):
    require(path.is_absolute() and not any(p.is_symlink() or p.is_junction()
        for p in (path, *path.parents)), 'producer-event-path')
    before = path.stat()
    require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
        and 0 < before.st_size <= 1048576, 'producer-event-file')
    with path.open('rb') as stream:
        opened = os.fstat(stream.fileno()); raw = stream.read(1048577)
        after = os.fstat(stream.fileno())
    def identity(s):
        return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    require(identity(before) == identity(opened) == identity(after) == identity(path.stat())
        and len(raw) == before.st_size, 'producer-event-changed')
    return raw


def check_source(root, executable, revision):
    require(all(type(x) is str and re.fullmatch('[0-9a-f]{40}', x)
        for x in (executable, revision)), 'producer-source-revisions')
    def git(*args):
        return subprocess.check_output(['git', '--no-optional-locks', '-C', str(root), *args],
            stderr=subprocess.DEVNULL)
    require(git('rev-parse', 'HEAD').decode().strip() == executable
        and not git('status', '--porcelain=v1', '--untracked-files=all'), 'producer-clean-E')
    original = git('show', executable+':'+WORKFLOW)
    require(0 < len(original) <= 262144 and git('show', revision+':'+WORKFLOW) == original,
        'producer-actual-workflow-bytes')
    return hashlib.sha256(original).hexdigest()


def live_identity(source, executable, approval):
    env = os.environ
    require(sys.platform == 'win32' and env.get('RUNNER_ENVIRONMENT') == 'github-hosted'
        and env.get('GITHUB_ACTIONS') == 'true' and env.get('GITHUB_EVENT_NAME') == 'pull_request'
        and env.get('GITHUB_REPOSITORY') == REPOSITORY and env.get('GITHUB_JOB') == JOB
        and env.get('GITHUB_RUN_ATTEMPT') == '1'
        and env.get('GITHUB_WORKFLOW_REF', '').startswith(REPOSITORY+'/'+WORKFLOW+'@'),
        'producer-original-pr-environment')
    config_raw = env.get(CONFIG, '')
    require(parse_approval(config_raw) == approval and executable == approval['executable'],
        'producer-fixture-config-changed')
    require(env.get('GITHUB_REF') == 'refs/pull/'+str(approval['pr_number'])+'/merge',
        'producer-original-pr-ref')
    merge = env.get('GITHUB_SHA', ''); revision = env.get('GITHUB_WORKFLOW_SHA', '')
    run_text = env.get('GITHUB_RUN_ID', '')
    require(all(re.fullmatch('[0-9a-f]{40}', s) for s in (executable, merge, revision))
        and re.fullmatch('[1-9][0-9]{0,19}', run_text), 'producer-original-revisions')
    # These are original observations, never reassigned GITHUB_* variables.
    env_names = ('GITHUB_REF', 'GITHUB_SHA', 'GITHUB_WORKFLOW_SHA', 'GITHUB_RUN_ID', 'GITHUB_EVENT_PATH',
        'GITHUB_WORKFLOW_REF', 'GITHUB_JOB', 'GITHUB_RUN_ATTEMPT', 'GITHUB_EVENT_NAME',
        'GITHUB_REPOSITORY', 'GITHUB_ACTIONS', 'RUNNER_ENVIRONMENT')
    snapshot = {k: env.get(k) for k in env_names}
    root = Path(source)
    require(root.is_absolute() and not any(x.lower() == 'onedrive' for x in root.parts)
        and not any(p.is_symlink() or p.is_junction() for p in (root, *root.parents)),
        'producer-source-path')
    metadata = root/'.git'
    require(metadata.is_dir() and not metadata.is_symlink() and not metadata.is_junction()
        and not any((metadata/p).exists() for p in
            ('commondir', 'objects/info/alternates', 'objects/info/http-alternates')),
        'producer-independent-git')
    workflow_sha = check_source(root, executable, revision)
    event_path = Path(env['GITHUB_EVENT_PATH']); raw = _event_bytes(event_path)
    event = strict_json(raw)
    from lightyear_execution.tower_drill_reservation import _GitHubAPI
    api = _GitHubAPI(); prefix = '/repos/'+REPOSITORY; run_id = int(run_text)
    def observe():
        run = api.request('GET', prefix+'/actions/runs/'+run_text)
        require(type(run.get('workflow_id')) is int and run['workflow_id'] > 0,
            'producer-original-workflow-id')
        workflow = api.request('GET', prefix+'/actions/workflows/'+str(run['workflow_id']))
        require(type(workflow.get('id')) is int and workflow['id'] == run['workflow_id']
            and workflow.get('path') == WORKFLOW, 'producer-original-workflow')
        listed = api.request('GET', prefix+'/actions/runs/'+run_text+'/attempts/1/jobs?per_page=100')
        rows = listed.get('jobs')
        require(type(rows) is list and type(listed.get('total_count')) is int
            and listed['total_count'] == len(rows) == 1 and type(rows[0]) is dict,
            'producer-complete-single-job')
        job = rows[0]
        live = api.request('GET', prefix+'/pulls/'+str(approval['pr_number']))
        relationships(event, run, job, live, approval, run_id)
        return dict(repository=REPOSITORY, executable=executable, run_id=run_id,
            run_attempt=1, job_id=job['id'], workflow_id=run['workflow_id'], workflow_path=WORKFLOW)
    identity = observe()
    require(observe() == identity and check_source(root, executable, revision) == workflow_sha
        and _event_bytes(event_path) == raw and env.get(CONFIG, '') == config_raw
        and {k: env.get(k) for k in env_names} == snapshot, 'producer-original-observations-changed')
    return identity
