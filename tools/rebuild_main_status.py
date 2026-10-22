"""CI-only status rendering followed by a draft PR, never a direct main push."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys

STATUS_FILES = ('docs/factory/current-status.json', 'docs/factory/current-status.md')
BRANCH_PREFIX = 'codex/status-rebuild-'
OPEN_PR_LIMIT = 6
BOT_ID = 41898282


def git(*args):
    return subprocess.check_output(['git', *args], text=True).strip()


def generate():
    subprocess.run([sys.executable, '-B', 'tools/build_factory_current_status.py'], check=True)
    subprocess.run([sys.executable, '-B', 'tools/build_factory_current_status.py', '--check'], check=True)


def github(route, payload=None):
    args = ['gh', 'api', 'repos/' + os.environ['GITHUB_REPOSITORY'] + '/' + route]
    if payload is not None:
        args += ['--method', 'POST', '--input', '-']
    else:
        args += ['--method', 'GET']
    # Ambiguous writes propagate. Never blindly repeat branch or PR creation.
    return json.loads(subprocess.check_output(
        args, input=json.dumps(payload) if payload is not None else None, text=True))


def list_prs(api, query):
    rows = []
    for page in range(1, 101):
        batch = api('pulls?' + query + f'&per_page=100&page={page}')
        if not isinstance(batch, list):
            raise ValueError('Expected a paginated pull request list')
        rows.extend(batch)
        if len(batch) < 100:
            return rows
    raise ValueError('Pull request pagination did not terminate')


def publication_gate(api, repository):
    prs = list_prs(api, 'state=open')
    status = [pr for pr in prs if pr['head']['ref'].startswith(BRANCH_PREFIX)]
    if status:
        # Leave an existing branch alone, including human edits and older sources.
        if len(status) != 1:
            raise ValueError('Multiple status PRs require human review')
        pr = status[0]
        source = pr['head']['ref'][len(BRANCH_PREFIX):]
        user = pr.get('user', {})
        if (not re.fullmatch(r'[0-9a-f]{40}', source)
                or type(user.get('id')) is not int or user['id'] != BOT_ID
                or user.get('login') != 'github-actions[bot]' or user.get('type') != 'Bot'
                or pr['head'].get('repo', {}).get('full_name') != repository
                or pr['base']['ref'] != 'main'
                or pr['title'] != 'status: rebuild after ' + source):
            raise ValueError('Existing status branch has unexpected ownership or target')
        return {'state': 'awaiting_existing_pr', 'pr': pr['number'], 'url': pr['html_url']}
    if len(prs) >= OPEN_PR_LIMIT:
        return {'state': 'awaiting_pr_slot', 'open_prs': len(prs), 'limit': OPEN_PR_LIMIT}
    return None


def rebuild(*, repository, command=git, render=generate, api=github, observe=None):
    """Create at most one source-bound draft; never update, approve, or merge it."""
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError('Expected owner/repository')
    if command('status', '--porcelain'):
        raise ValueError('Status rebuild requires a clean CI checkout')
    command('fetch', '--no-tags', 'origin', 'refs/heads/main')
    source = command('rev-parse', 'FETCH_HEAD')
    if not re.fullmatch(r'[0-9a-f]{40}', source):
        raise ValueError('Main must resolve to an exact commit')
    command('checkout', '--detach', source)
    if observe is not None:
        observe(source, api)
    render()
    changed = command('diff', '--name-only').splitlines()
    if (set(changed) - set(STATUS_FILES) or command('diff', '--cached', '--name-only')
            or command('ls-files', '--others', '--exclude-standard')
            or command('diff', '--name-only', '--diff-filter=D')
            or command('diff', '--summary')):
        raise ValueError('Renderer changed paths or modes outside regular status output edits')
    if not changed:
        return {'state': 'unchanged', 'changed': False, 'source': source}
    gate = publication_gate(api, repository)
    if gate:
        return dict(gate, changed=True, source=source, published_to_main=False)
    branch = BRANCH_PREFIX + source
    owner = repository.split('/')[0]
    if list_prs(api, 'state=all&head=' + owner + ':' + branch):
        raise ValueError('This source already has a historical PR; human review required')
    if command('ls-remote', 'origin', 'refs/heads/' + branch):
        raise ValueError('Status branch already exists; inspect any ambiguous previous publication')

    def current_main():
        remote = command('ls-remote', 'origin', 'refs/heads/main').split()
        if remote != [source, 'refs/heads/main']:
            raise ValueError('Main advanced; refuse stale status publication and rerun from current main')

    command('diff', '--check')
    current_main()
    command('add', '--', *STATUS_FILES)
    command('-c', 'user.name=github-actions[bot]',
            '-c', 'user.email=41898282+github-actions[bot]@users.noreply.github.com',
            '-c', 'commit.gpgsign=false', 'commit', '-m', 'status: rebuild after ' + source)
    commit = command('rev-parse', 'HEAD')
    if not re.fullmatch(r'[0-9a-f]{40}', commit) or commit == source:
        raise ValueError('Expected an exact new status commit')
    if command('show', '-s', '--format=%P', commit) != source:
        raise ValueError('Status commit must have exactly the rendered main as its parent')
    if (set(command('diff', '--name-only', source, commit).splitlines()) != set(changed)
            or command('status', '--porcelain')):
        raise ValueError('Unexpected committed status scope')
    gate = publication_gate(api, repository)
    if gate:
        return dict(gate, changed=True, source=source, published_to_main=False)
    current_main()
    command('push', 'origin', commit + ':refs/heads/' + branch)
    if command('ls-remote', 'origin', 'refs/heads/' + branch).split() != [commit, 'refs/heads/' + branch]:
        raise ValueError('Published branch did not resolve to the exact status commit')
    current_main()
    gate = publication_gate(api, repository)
    if gate:
        # Retain the branch for inspection; never delete it or exceed a known cap.
        return dict(gate, changed=True, source=source, branch=branch, published_to_main=False)
    payload = {
        'title': 'status: rebuild after ' + source, 'head': branch, 'base': 'main', 'draft': True,
        'body': ('Rebuild only the two generated status outputs from main `' + source + '`.\n\n'
                 'Generated and freshness-checked in CI. No inputs or dated evidence changed.\n\n'
                 'A maintainer must approve the GitHub-token-triggered workflows to run, '
                 'then review all checks on this exact head. This draft is not a green receipt.\n\n'
                 'Howard must approve the exact final-green commit before merge. '
                 'The status bot never approves workflows, reviews, or merges.')}
    pr = api('pulls', payload)
    if (type(pr.get('number')) is not int or not pr.get('draft')
            or pr.get('state') != 'open' or pr.get('base', {}).get('ref') != 'main'
            or pr.get('head', {}).get('sha') != commit
            or pr['head'].get('ref') != branch
            or pr['head'].get('repo', {}).get('full_name') != repository):
        raise ValueError('PR creation outcome unresolved; inspect existing branch and PR before retrying')
    return {'state': 'draft_created', 'changed': True, 'source': source, 'commit': commit,
            'branch': branch, 'pr': pr['number'], 'url': pr['html_url'], 'published_to_main': False}


def main():
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_bytes())
    if (os.environ.get('GITHUB_ACTIONS') != 'true'
            or os.environ.get('GITHUB_EVENT_NAME') not in ('push', 'workflow_dispatch')
            or os.environ.get('GITHUB_REF') != 'refs/heads/main'
            or event.get('repository', {}).get('full_name') != os.environ.get('GITHUB_REPOSITORY')
            or (os.environ['GITHUB_EVENT_NAME'] == 'push' and event.get('ref') != 'refs/heads/main')):
        raise ValueError('Status publication requires a main GitHub Actions event')
    # One read-only observation is shared by generation and --check. The
    # ephemeral input stays outside the checkout; its data is in both outputs.
    import tempfile
    from tools.release_status_records import collect_live_status
    with tempfile.TemporaryDirectory(prefix='factory-live-status-', dir=os.environ['RUNNER_TEMP']) as temporary:
        snapshot = Path(temporary)/'snapshot.json'
        def observe(source, api):
            snapshot.write_text(json.dumps(collect_live_status(api, source), sort_keys=True)+'\n', encoding='utf-8')
        previous = os.environ.get('LIGHTYEAR_FACTORY_LIVE_STATUS')
        os.environ['LIGHTYEAR_FACTORY_LIVE_STATUS'] = str(snapshot)
        try:
            result = rebuild(repository=os.environ['GITHUB_REPOSITORY'], observe=observe)
        finally:
            if previous is None:
                os.environ.pop('LIGHTYEAR_FACTORY_LIVE_STATUS', None)
            else:
                os.environ['LIGHTYEAR_FACTORY_LIVE_STATUS'] = previous
    print(json.dumps(result, sort_keys=True))
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a', encoding='utf-8') as stream:
            stream.write('## Generated status handoff\n\n```json\n' + json.dumps(result, indent=2)
                         + '\n```\n\nNo direct main publication. Drafts need workflow approval, '
                         'successful exact-head CI, review and Howard’s merge approval. '
                         'Existing PRs and full capacity are deferred, not deployment acceptance.\n')


if __name__ == '__main__':
    main()
