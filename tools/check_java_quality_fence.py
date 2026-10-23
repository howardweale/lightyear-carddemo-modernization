"""Derive the pre-run Java quality fence from trusted base Git objects.

No date unlock and no PR-side exception. Fenced drafts may run proof jobs,
but remain unmergeable until a separately reviewed post-run policy change.
"""
import argparse
import hashlib
import json
from pathlib import PurePosixPath
import subprocess

ORIGINAL = 'docs/factory/copau-factory-judge-freeze-2026-10-18.json'
AMENDMENT = 'docs/factory/copau-factory-judge-freeze-amendment-2026-10-20.json'
F2 = 'docs/factory/copau-f2-preparation-2026-10-22/request.json'


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args])


def safe_path(value):
    if (not isinstance(value, str) or not value or '\\' in value or ':' in value
            or value.startswith('/') or any(x in ('', '.', '..') for x in value.split('/'))):
        raise ValueError('invalid-fence-path')
    return value


def derive(read, names):
    """read and names describe one trusted base, never the candidate checkout."""
    paths = set()
    prefixes = set()
    inputs = {}

    def document(path, expected=None):
        path = safe_path(path)
        raw = read(path)
        digest = hashlib.sha256(raw).hexdigest()
        if expected is not None and digest != expected:
            raise ValueError('fence-record-hash:' + path)
        inputs[path] = digest
        paths.add(path)
        return json.loads(raw)

    def rows(values):
        if not isinstance(values, list) or not values:
            raise ValueError('empty-fence-inventory')
        for row in values:
            paths.add(safe_path(row['path']))
            if len(row['sha256']) != 64:
                raise ValueError('invalid-fence-digest')

    original = document(ORIGINAL)
    amendment = document(AMENDMENT)
    if amendment['original_manifest_sha256'] != inputs[ORIGINAL]:
        raise ValueError('freeze-amendment-binding')
    rows(original['files'])
    rows(amendment['files'])
    rows([amendment['existing_authorized_change']])
    # The amendment freezes the exact test inventory, including additions.
    for path in tuple(paths):
        if '/service/src/test/' in path:
            prefixes.add(path.split('/src/test/')[0] + '/src/test/')

    request = document(F2)
    if request['schema'] != 'copau-f2-preparation/1':
        raise ValueError('unreviewed-f2-schema')
    for binding in request['engineering_source_bindings'].values():
        paths.add(safe_path(binding['path']))
    for binding in request['bindings'].values():
        document(binding['path'], binding['sha256'])
    scope = json.loads(read(request['bindings']['scope']['path']))
    prefixes.add(safe_path(scope['candidate_directory']) + '/')
    paths.add(safe_path(scope['interfaces']['source_path']))
    for path in request['work_order']['scope']['allowed_paths']:
        prefixes.add(safe_path(path).rstrip('/') + '/')
    workspace = json.loads(read(request['bindings']['workspace']['path']))
    if not isinstance(workspace, dict) or not workspace:
        raise ValueError('empty-worker-binding')
    paths.update(safe_path(path) for path in workspace)

    # Include all retained support inventories, including additive proposals.
    # Unioning prevents a later record from silently removing a fenced path.
    support = sorted(path for path in names if path.startswith('docs/factory/copau-f8-')
                     and path.endswith('.json') and
                     ('support-bindings-' in path or 'worker-packaging-' in path))
    if not support:
        raise ValueError('missing-support-bindings')
    for path in support:
        value = document(path)
        rows(value['selection']['source_bindings'])
    return dict(paths=sorted(paths), prefixes=sorted(prefixes), inputs=inputs)


def violations(fence, changed):
    return sorted(path for path in changed if path in fence['paths']
                  or any(path.startswith(prefix) or path == prefix.rstrip('/')
                         for prefix in fence['prefixes']))


def inspect(repo, base, head):
    # Resolve full object IDs before composing revision:path arguments.
    base = git(repo, 'rev-parse', '--verify', base + '^{commit}').decode().strip()
    head = git(repo, 'rev-parse', '--verify', head + '^{commit}').decode().strip()
    names = git(repo, 'ls-tree', '-r', '--name-only', base).decode().splitlines()
    fence = derive(lambda path: git(repo, 'show', base + ':' + path), names)
    # --no-renames exposes both old and new names, including deletions/mode changes.
    changed = git(repo, 'diff', '--no-renames', '--name-only', '-z', base, head).decode().split('\0')
    blocked = violations(fence, [path for path in changed if path])
    canonical = json.dumps(fence, sort_keys=True, separators=(',', ':')).encode()
    return dict(schema='java-quality-fence/1', base=base, head=head,
                fence_sha256=hashlib.sha256(canonical).hexdigest(),
                fenced_paths=len(fence['paths']), fenced_prefixes=fence['prefixes'],
                source_records=fence['inputs'], blocked_paths=blocked,
                merge_permitted=not blocked, automatic_expiry=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True)
    parser.add_argument('--head', default='HEAD')
    parser.add_argument('--repo', default='.')
    args = parser.parse_args()
    report = inspect(args.repo, args.base, args.head)
    print(json.dumps(report, sort_keys=True))
    if report['blocked_paths']:
        raise SystemExit('java-quality-fence: fenced changes require post-run review')


if __name__ == '__main__':
    main()
