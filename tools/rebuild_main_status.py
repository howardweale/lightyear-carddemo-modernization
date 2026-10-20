"""CI-only bot rebuild of the two generated status files on main."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys

STATUS_FILES = ('docs/factory/current-status.json', 'docs/factory/current-status.md')


def git(*args):
    return subprocess.check_output(['git', *args], text=True).strip()


def generate():
    subprocess.run([sys.executable, '-B', 'tools/build_factory_current_status.py'], check=True)
    subprocess.run([sys.executable, '-B', 'tools/build_factory_current_status.py', '--check'], check=True)


def rebuild(*, command=git, render=generate, push=None, attempts=3):
    """Refresh main after concurrent advances; never force-push or reuse stale output."""
    if command('status', '--porcelain'):
        raise ValueError('Status rebuild requires a clean CI checkout')
    if push is None:
        push = lambda: subprocess.run(['git', 'push', 'origin', 'HEAD:refs/heads/main'], check=False).returncode
    for attempt in range(attempts):
        command('fetch', '--no-tags', 'origin', 'refs/heads/main')
        source = command('rev-parse', 'FETCH_HEAD')
        if not re.fullmatch(r'[0-9a-f]{40}', source):
            raise ValueError('Main must resolve to an exact commit')
        command('checkout', '--detach', source)
        render()
        # No extra files, staged changes, or deletions may ride the privileged push.
        changed = command('diff', '--name-only').splitlines()
        if (set(changed) - set(STATUS_FILES) or command('diff', '--cached', '--name-only')
                or command('ls-files', '--others', '--exclude-standard')
                or command('diff', '--name-only', '--diff-filter=D')):
            raise ValueError('Renderer changed files outside the two generated status outputs')
        if not changed:
            return {'changed': False, 'source': source}
        command('diff', '--check')
        command('add', '--', *STATUS_FILES)
        command('-c', 'user.name=github-actions[bot]',
                '-c', 'user.email=41898282+github-actions[bot]@users.noreply.github.com',
                '-c', 'commit.gpgsign=false', 'commit', '-m', 'status: rebuild after ' + source)
        commit = command('rev-parse', 'HEAD')
        if push() == 0:
            return {'changed': True, 'source': source, 'commit': commit}
        remote = command('ls-remote', 'origin', 'refs/heads/main').split()
        if not remote or remote[0] == source:
            raise RuntimeError('Status push rejected without a main advance; check repository bot permissions')
    raise RuntimeError('Main kept advancing during bounded status publication; no force push attempted')


def main():
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_bytes())
    if (os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('GITHUB_EVENT_NAME') != 'push'
            or event.get('ref') != 'refs/heads/main'
            or event.get('repository', {}).get('full_name') != os.environ.get('GITHUB_REPOSITORY')):
        raise ValueError('Status publication requires a main-push GitHub Actions job')
    print(json.dumps(rebuild(), sort_keys=True))


if __name__ == '__main__':
    main()
