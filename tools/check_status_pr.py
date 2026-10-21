"""Reject generated status output changes in PRs; inputs remain editable."""
import json
import os
from pathlib import Path
import re
import subprocess

STATUS_FILES = frozenset(('docs/factory/current-status.json', 'docs/factory/current-status.md'))
BOT_ID = 41898282


def permitted_bot(pr, repository):
    user = pr.get('user', {})
    return (type(user.get('id')) is int and user['id'] == BOT_ID
            and user.get('login') == 'github-actions[bot]' and user.get('type') == 'Bot'
            and pr.get('head', {}).get('repo', {}).get('full_name') == repository
            and pr.get('base', {}).get('ref') == 'main'
            and re.fullmatch(r'codex/status-rebuild-[0-9a-f]{40}', pr.get('head', {}).get('ref', ''))
            and pr.get('title') == 'status: rebuild after ' + pr['head']['ref'].removeprefix('codex/status-rebuild-'))


def check(pr, paths, repository):
    changed = set(paths)
    forbidden = changed & STATUS_FILES
    if forbidden and not (permitted_bot(pr, repository) and changed <= STATUS_FILES):
        raise ValueError('Generated status is rebuilt on main after merge; edit the generator or input records, '
                         'not these PR outputs: ' + ', '.join(sorted(forbidden)))


def changed_paths(base, head, *, cwd=None):
    if not all(re.fullmatch(r'[0-9a-f]{40}', sha) for sha in (base, head)):
        raise ValueError('Expected exact base/head commits')
    # Disable rename detection so both deletion and addition are examined.
    raw = subprocess.check_output(['git', 'diff', '--no-renames', '--name-only', '-z',
                                   base + '...' + head, '--'], cwd=cwd)
    return [part.decode('utf-8') for part in raw.split(b'\0') if part]


def main():
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_bytes())
    pr = event.get('pull_request')
    if pr is None:
        print('Status output guard: no pull request diff on this event.')
        return
    check(pr, changed_paths(pr['base']['sha'], pr['head']['sha']), os.environ['GITHUB_REPOSITORY'])
    print('Status output guard passed.')


if __name__ == '__main__':
    main()
