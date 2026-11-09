"""CI-only exact-commit clone for tests requiring clean loaded module origins."""
import atexit
from functools import lru_cache, wraps
import os
from pathlib import Path
import subprocess
import sys
import tempfile

MARKER = 'LIGHTYEAR_CLEAN_SOURCE_TEST_HEAD'


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args],
                                   stderr=subprocess.STDOUT, timeout=120)


@lru_cache(maxsize=1)
def checkout():
    source = Path(__file__).resolve().parents[1]
    head = git(source, 'rev-parse', 'HEAD').decode().strip()
    temp = tempfile.TemporaryDirectory(prefix='operator-source-', dir=os.environ['RUNNER_TEMP'])
    atexit.register(temp.cleanup)
    root = Path(temp.name).resolve() / 'checkout'
    # Local object reuse only; no network, hooks, signing, or original-index writes.
    subprocess.run(['git', '-c', 'core.autocrlf=false', '-c', 'core.longpaths=true',
                    'clone', '--shared', '--no-checkout', str(source), str(root)],
                   check=True, capture_output=True, timeout=120)
    hooks = Path(temp.name) / 'empty-hooks'
    hooks.mkdir()
    git(root, 'config', 'core.hooksPath', str(hooks))
    git(root, 'config', 'core.autocrlf', 'false')
    git(root, 'config', 'core.longpaths', 'true')
    git(root, 'checkout', '--detach', head)
    if git(root, 'rev-parse', 'HEAD').decode().strip() != head:
        raise AssertionError('fixture exact commit')
    if git(root, 'status', '--porcelain=v1', '--untracked-files=all'):
        raise AssertionError('fixture clean checkout')
    return root, head


def clean_checkout_test(method):
    @wraps(method)
    def run(test):
        test.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')
        expected = os.environ.get(MARKER)
        if expected:
            root = Path(__file__).resolve().parents[1]
            test.assertEqual(Path(os.environ['GITHUB_WORKSPACE']).resolve(), root)
            test.assertEqual(git(root, 'rev-parse', 'HEAD').decode().strip(), expected)
            test.assertEqual(git(root, 'status', '--porcelain=v1', '--untracked-files=all'), b'')
            return method(test)
        root, head = checkout()
        env = dict(os.environ, GITHUB_WORKSPACE=str(root), PYTHONDONTWRITEBYTECODE='1')
        env[MARKER] = head
        env['PYTHONPATH'] = os.pathsep.join(str(root / p) for p in ('src', '.', 'tests'))
        result = subprocess.run([sys.executable, '-B', '-m', 'unittest', test.id()],
                                cwd=root, env=env, capture_output=True, timeout=120)
        test.assertEqual(result.returncode, 0,
                         (result.stdout + result.stderr)[-8192:].decode('utf-8', errors='replace'))
        test.assertEqual(git(root, 'rev-parse', 'HEAD').decode().strip(), head)
        test.assertEqual(git(root, 'status', '--porcelain=v1', '--untracked-files=all'), b'')
    return run
