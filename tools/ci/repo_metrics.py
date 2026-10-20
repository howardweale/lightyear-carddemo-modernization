"""Read Git objects for reproducible repository measurements; execute only in CI."""
import argparse
import ast
from collections import Counter, defaultdict
import datetime
import json
from pathlib import Path
import subprocess

LAYERS = {
    'core': ['lightyear_common', 'lightyear_evidence', 'lightyear_trust', 'lightyear_judge'],
    'engine': ['lightyear_factory', 'lightyear_workflow', 'lightyear_execution',
               'lightyear_knowledge_graph', 'lightyear_business_rules', 'lightyear_runtime',
               'lightyear_agent', 'lightyear_audit', 'lightyear_cloud_runner', 'lightyear_extensions'],
    'estates': ['lightyear_mainframe', 'lightyear_calibration', 'carddemo_oracle'],
    'apps': ['lightyear_control_tower', 'lightyear_pilot', 'lightyear_readiness',
             'lightyear_qualification', 'lightyear_toolkit'],
}
LEVEL = {package: index for index, packages in enumerate(LAYERS.values()) for package in packages}


def analyze(path, raw, known):
    package = path.split('/')[1]
    tree = ast.parse(raw, filename=path)
    imports, functions = [], []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules = [alias.name.split('.')[0] for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            modules = [package if node.level else (node.module or '').split('.')[0]]
        else:
            modules = []
        imports.extend({'from': package, 'to': target, 'path': path, 'line': node.lineno}
                       for target in sorted(set(modules)) if target in known and target != package)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            lines = node.end_lineno - node.lineno + 1
            if lines > 150:
                functions.append({'path': path, 'name': node.name, 'line': node.lineno, 'lines': lines})
    return imports, functions


def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root)


def measure(root, ref, clone_dir=None):
    commit = git(root, 'rev-parse', '--verify', ref + '^{commit}').decode().strip()
    rows = []
    for row in git(root, 'ls-tree', '-rlz', commit).split(b'\0'):
        if not row:
            continue
        header, name = row.split(b'\t', 1)
        mode, kind, oid, size = header.split()
        if kind == b'blob':
            rows.append((name.decode(), oid.decode(), int(size)))
    known = {path.split('/')[1] for path, _, _ in rows if path.startswith('src/')}
    folders = defaultdict(lambda: {'files': 0, 'bytes': 0})
    for path, _, size in rows:
        folder = path.split('/')[0] if '/' in path else '.'
        folders[folder]['files'] += 1
        folders[folder]['bytes'] += size
    sources = [(path, oid) for path, oid, _ in rows if path.startswith('src/') and path.endswith('.py')]
    data = git_batch(root, [oid for _, oid in sources])
    lines, imports, functions, large = Counter(), [], [], []
    for (path, _), raw in zip(sources, data, strict=True):
        count = len(raw.splitlines())
        lines[path.split('/')[1]] += count
        edges, oversized = analyze(path, raw, known)
        imports.extend(edges)
        functions.extend(oversized)
        if count > 800:
            large.append({'path': path, 'lines': count})
    edges = {(row['from'], row['to']) for row in imports}
    mutual = sorted([list(pair) for pair in edges if pair[0] < pair[1] and pair[::-1] in edges])
    violations = [row for row in imports if row['from'] in LEVEL and row['to'] in LEVEL
                  and LEVEL[row['from']] < LEVEL[row['to']]]
    judge = [row for row in imports if row['from'] == 'lightyear_judge' and row['to'] not in LAYERS['core']]
    pack = None
    if clone_dir:
        stats = git(clone_dir, 'count-objects', '-v').decode().splitlines()
        pack = int(dict(line.split(': ', 1) for line in stats)['size-pack']) * 1024
    return {
        'schema': 'repository-metrics/1', 'commit': commit,
        'tree': git(root, 'rev-parse', commit + '^{tree}').decode().strip(),
        'as_of': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'method': 'Tracked Git blobs; Python physical lines and AST import statements in src; dynamic imports excluded.',
        'top_level': dict(sorted(folders.items())), 'tracked_files': len(rows),
        'tracked_bytes': sum(size for _, _, size in rows),
        'python_lines_by_package': dict(sorted(lines.items())),
        'mutual_package_pairs': mutual, 'mutual_package_pair_count': len(mutual),
        'layer_violations': violations, 'layer_violation_count': len(violations),
        'unclassified_packages': sorted(known - set(LEVEL)),
        'layer_policy': 'Proposed four-layer map; lightyear_data remains unclassified pending A3. Same-layer edges allowed. Not an enforcement receipt.',
        'judge_non_core_imports': judge, 'judge_non_core_import_count': len(judge),
        'functions_over_150_lines': functions, 'files_over_800_lines': large,
        'root_files': sorted(path for path, _, _ in rows if '/' not in path),
        'flat_tools_files': sorted(path for path, _, _ in rows if path.startswith('tools/') and path.count('/') == 1),
        'clone_pack_bytes': pack,
        'clone_measurement': 'Fresh bare clone --no-local, packed object bytes' if clone_dir else 'not measured',
    }


def git_batch(root, oids):
    if not oids:
        return []
    raw = subprocess.check_output(['git', 'cat-file', '--batch'], cwd=root,
                                  input=('\n'.join(oids) + '\n').encode())
    offset, blobs = 0, []
    for oid in oids:
        end = raw.index(b'\n', offset)
        actual, kind, size = raw[offset:end].split()
        if actual.decode() != oid or kind != b'blob':
            raise ValueError('unexpected Git object')
        start = end + 1
        offset = start + int(size) + 1
        blobs.append(raw[start:offset - 1])
    if offset != len(raw):
        raise ValueError('unexpected trailing Git output')
    return blobs


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ref', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--clone-dir', type=Path)
    args = parser.parse_args()
    value = measure(Path.cwd(), args.ref, args.clone_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8', newline='\n')
