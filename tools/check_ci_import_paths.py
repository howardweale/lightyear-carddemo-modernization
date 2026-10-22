"""Static CI trigger/import coverage. Never imports the inspected repository."""
from __future__ import annotations

import argparse
import ast
from collections import deque
import fnmatch
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

import yaml


def glob_matches(path, pattern):
    expression = ''
    i = 0
    while i < len(pattern):
        if pattern[i:i + 3] == '**/':
            expression += '(?:.*/)?'
            i += 3
        elif pattern[i:i + 2] == '**':
            expression += '.*'
            i += 2
        elif pattern[i] == '*':
            expression += '[^/]*'
            i += 1
        elif pattern[i] == '?':
            expression += '[^/]'
            i += 1
        else:
            expression += re.escape(pattern[i])
            i += 1
    return re.fullmatch(expression, path) is not None


def includes(rule, path):
    if 'paths' in rule:
        included = False
        for pattern in rule['paths']:
            if glob_matches(path, pattern.removeprefix('!')):
                included = not pattern.startswith('!')
        return included
    return not any(glob_matches(path, p) for p in rule.get('paths-ignore', []))


def triggers(config):
    events = config.get('on', {})
    if isinstance(events, str):
        events = [events]
    if isinstance(events, list):
        return {event: {} for event in ('pull_request', 'push') if event in events}
    return {event: events[event] or {} for event in ('pull_request', 'push') if event in events}


def git_snapshot(root, ref):
    """Read committed owned source as inert bytes, with bounded batch responses."""
    def git(*args):
        return subprocess.check_output(['git', '-C', str(root), *args])
    commit = git('rev-parse', '--verify', ref + '^{commit}').decode().strip()
    names = git('ls-tree', '-rz', commit).split(b'\0')
    selected = []
    for record in names:
        if not record:
            continue
        metadata, encoded = record.split(b'\t', 1)
        mode, kind, oid = metadata.decode().split()
        path = encoded.decode('utf-8')
        owned = (path.startswith(('src/', 'tools/', 'tests/', 'factory/carddemo-web/runtime/'))
                 and path.endswith(('.py', '.sh', '.ps1')))
        workflow = path.startswith('.github/workflows/') and path.endswith(('.yml', '.yaml'))
        wrapper = '/' not in path and path.endswith(('.sh', '.ps1'))
        if owned or workflow or wrapper:
            if kind != 'blob' or mode not in ('100644', '100755'):
                raise ValueError('non-regular source: ' + path)
            selected.append((path, oid))
    # Batch only sizes first: do not download or print large evidence files.
    ids = ''.join(oid + '\n' for _, oid in selected).encode()
    headers = subprocess.run(['git', '-C', str(root), 'cat-file', '--batch-check'],
                             input=ids, stdout=subprocess.PIPE, check=True).stdout.splitlines()
    if len(headers) != len(selected):
        raise ValueError('incomplete object inventory')
    for (path, oid), header in zip(selected, headers):
        actual, kind, size = header.decode().split()
        if actual != oid or kind != 'blob' or int(size) > 2_000_000:
            raise ValueError('source object identity/size: ' + path)
    process = subprocess.run(['git', '-C', str(root), 'cat-file', '--batch'],
                             input=ids, stdout=subprocess.PIPE, check=True)
    raw = process.stdout
    offset = 0
    files = {}
    for path, oid in selected:
        end = raw.index(b'\n', offset)
        actual, kind, size = raw[offset:end].decode().split()
        size = int(size)
        if actual != oid or kind != 'blob':
            raise ValueError('source object identity: ' + path)
        offset = end + 1
        files[path] = raw[offset:offset + size].decode('utf-8-sig')
        offset += size
        if raw[offset:offset + 1] != b'\n':
            raise ValueError('source object framing')
        offset += 1
    if offset != len(raw):
        raise ValueError('extra object bytes')
    return commit, files


class ImportGraph:
    def __init__(self, files):
        self.files = files
        self.modules = {}
        self.cache = {}
        self.opaque = {}
        for path in sorted(files):
            if not path.endswith('.py'):
                continue
            name = path[:-3].removesuffix('/__init__')
            names = {name.replace('/', '.')}
            if name.startswith(('src/', 'tests/', 'tools/')):
                names.add(name.split('/', 1)[1].replace('/', '.'))
            for name in names:
                self.modules.setdefault(name, set()).add(path)

    def resolve(self, name, importer=None):
        """Union repository import roots conservatively, including package init."""
        result = set()
        if importer:
            local = importer.rpartition('/')[0]
            candidates = (local + '/' + name.replace('.', '/') + '.py',
                          local + '/' + name.replace('.', '/') + '/__init__.py')
            result.update(p for p in candidates if p in self.files)
        while name:
            result.update(self.modules.get(name, ()))
            name = name.rpartition('.')[0]
        return result

    def imports(self, path):
        if path in self.cache:
            return self.cache[path]
        if not path.endswith('.py'):
            self.cache[path] = set()
            return set()
        result, opaque = set(), set()
        tree = ast.parse(self.files[path], filename=path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    result.update(self.resolve(alias.name, path))
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ''
                if node.level:
                    package = path[:-3].split('/')[:-1]
                    if package and package[0] == 'src':
                        package = package[1:]
                    if node.level > len(package):
                        raise ValueError('relative import escapes package: ' + path)
                    module = '.'.join(package[:len(package) - node.level + 1]
                                      + ([module] if module else []))
                result.update(self.resolve(module, path))
                for alias in node.names:
                    if alias.name != '*':
                        result.update(self.resolve(module + '.' + alias.name, path))
            elif isinstance(node, ast.Call):
                function = node.func
                dynamic = ((isinstance(function, ast.Name) and function.id == '__import__')
                           or (isinstance(function, ast.Attribute)
                               and function.attr in ('import_module', 'spec_from_file_location'))
                           or (isinstance(function, ast.Name)
                               and function.id in ('import_module', 'spec_from_file_location')))
                if dynamic:
                    if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str) and not (
                            isinstance(function, (ast.Name, ast.Attribute))
                            and getattr(function, 'attr', getattr(function, 'id', '')) == 'spec_from_file_location'):
                        result.update(self.resolve(node.args[0].value, path))
                    else:
                        opaque.add(ast.dump(node, include_attributes=False))
        self.cache[path] = result
        self.opaque[path] = opaque
        return result

    def closure(self, roots):
        pending, seen, opaque = deque(sorted(roots)), set(), set()
        while pending:
            path = pending.popleft()
            if path in seen:
                continue
            seen.add(path)
            pending.extend(sorted(self.imports(path) - seen))
            opaque.update((path, item) for item in self.opaque.get(path, ()))
        return seen, opaque

    def entrypoints(self, commands):
        """Conservative literal commands, unittest selectors/discovery and wrappers."""
        roots, wrappers, unresolved = set(), set(), set()
        pending = list(commands)
        while pending:
            command = pending.pop().replace(chr(92) + '\n', ' ').replace('`\n', ' ')
            # Comments and echo output are not commands.
            command = '\n'.join(line for line in command.splitlines()
                                if not line.lstrip().startswith(('#', 'echo ', 'printf ', 'Write-Output ')))
            for token in re.findall(r'[A-Za-z_][A-Za-z0-9_./*?-]*', command.replace(chr(92), '/')):
                normalized = token.replace('\\', '/')
                if normalized in self.files and normalized.endswith('.py'):
                    roots.add(normalized)
                if token.startswith(('test_', 'tests.', 'tools.', 'lightyear_')):
                    roots.update(self.resolve(token))
                if normalized.endswith(('.sh', '.ps1')) and normalized in self.files and normalized not in wrappers:
                    wrappers.add(normalized)
                    pending.append(self.files[normalized])
            for name in re.findall(r'(?:^|\s)-m\s+([A-Za-z_][\w.]*)', command):
                if name not in ('pip', 'unittest', 'compileall', 'venv'):
                    resolved = self.resolve(name)
                    if resolved:
                        roots.update(resolved)
                    elif name.startswith(('tools.', 'lightyear_', 'tests.')):
                        unresolved.add('module:' + name)
            for line in command.splitlines():
                if not re.search(r'-m\s+unittest\s+discover\b', line):
                    continue
                pattern_match = re.search(r'(?:-p|--pattern)(?:=|\s+)[\'"]?([\w*?.-]+)', line)
                pattern = pattern_match.group(1) if pattern_match else 'test*.py'
                start_match = re.search(r'(?:-s|--start-directory)(?:=|\s+)[\'"]?([\w./-]+)', line)
                directory = start_match.group(1).strip('./') if start_match else ''
                # Variables/Join-Path around the test root conservatively use all tests.
                if not directory and 'tests' in line:
                    directory = 'tests'
                prefix = directory + '/' if directory else ''
                roots.update(path for path in self.files if path.startswith(prefix)
                             and fnmatch.fnmatchcase(Path(path).name, pattern))
            if re.search(r'\bpython(?:3)?\s+(?:-B\s+)?-c\b', command):
                unresolved.add('inline-python:' + hashlib.sha256(command.encode()).hexdigest())
        return roots | wrappers, unresolved


def audit(files):
    graph = ImportGraph(files)
    gaps, opaque, workflows = set(), set(), []
    for path in sorted(files):
        if not path.startswith('.github/workflows/') or not path.endswith(('.yml', '.yaml')):
            continue
        config = yaml.load(files[path], Loader=yaml.BaseLoader)
        if not isinstance(config, dict):
            raise ValueError('invalid workflow: ' + path)
        events = triggers(config)
        filtered = {event: rule for event, rule in events.items()
                    if 'paths' in rule or 'paths-ignore' in rule}
        if not filtered:
            continue
        commands = [str(step['run']) for job in config.get('jobs', {}).values()
                    for step in job.get('steps', []) if 'run' in step]
        roots, unresolved = graph.entrypoints(commands)
        dependencies, dynamic = graph.closure(roots)
        for event, rule in filtered.items():
            for dependency in dependencies:
                if not includes(rule, dependency):
                    gaps.add((path, event, dependency))
            opaque.update((path, event, source, expression) for source, expression in dynamic)
            opaque.update((path, event, '<command>', item) for item in unresolved)
        workflows.append(dict(workflow=path,events=sorted(filtered),roots=sorted(roots),
                              dependencies=sorted(dependencies)))
    return dict(gaps=sorted(gaps), opaque=sorted(opaque), workflows=workflows)


def compare(base, head):
    """Ratchet existing debt; newly uncovered dependencies must be repaired."""
    old = {tuple(item) for item in base['gaps']}
    new = {tuple(item) for item in head['gaps']}
    old_opaque = {tuple(item) for item in base['opaque']}
    new_opaque = {tuple(item) for item in head['opaque']}
    return dict(new_gaps=sorted(new - old), inherited_gaps=sorted(new & old),
                resolved_gaps=sorted(old - new), new_opaque=sorted(new_opaque - old_opaque),
                inherited_opaque=sorted(new_opaque & old_opaque),
                passed=not (new - old or new_opaque - old_opaque))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True)
    parser.add_argument('--head', default='HEAD')
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--out', type=Path, default=Path('work/ci/import-path-coverage.json'))
    args = parser.parse_args(argv)
    # CI supplies exact event SHAs. Refuse option injection or accidental branch names.
    if not re.fullmatch(r'[0-9a-f]{40}', args.base):
        raise ValueError('base must be an exact Git SHA')
    if args.head != 'HEAD' and not re.fullmatch(r'[0-9a-f]{40}', args.head):
        raise ValueError('head must be HEAD or an exact Git SHA')
    base_sha, base_files = git_snapshot(args.root, args.base)
    head_sha, head_files = git_snapshot(args.root, args.head)
    base, head = audit(base_files), audit(head_files)
    result = compare(base, head)
    result.update(schema='lightyear-ci-import-path-coverage/v1', base=base_sha, head=head_sha,
                  scope='Static Python imports and literal workflow entrypoints; no runtime execution proof',
                  baseline=base, current=head)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: result[key] for key in ('base','head','passed','new_gaps','new_opaque')}))
    print('Inherited gaps:', len(result['inherited_gaps']),
          'Resolved gaps:', len(result['resolved_gaps']))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
