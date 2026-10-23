"""Account scope/date projection; evidence verification must precede publication."""
from datetime import date
import re
from tools.carddemo_account_proof import GROUPS

ENGINE_PROGRAMS = ('COACTVWC', 'COACTUPC', 'COPAUS0C', 'COPAUS1C')


def _strings(value, reason):
    if (not isinstance(value, list) or not value
        or any(not isinstance(item, str) or not item.strip() for item in value)
        or len(set(value)) != len(value)):
        raise ValueError(reason)
    return list(value)


def _date(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value):
        raise ValueError('account-publication-date')
    return date.fromisoformat(value)


def project_scope(group, scopes, source, measurement_date):
    """Project already hash-bound scopes; never infer whole-screen retirement."""
    if (group.get('program') != 'COACTUPC' or group.get('whole_screen_idiomatic') is not False
        or set(scopes) != set(GROUPS)):
        raise ValueError('account-publication-scope')
    if _date(group['publication_date']) < _date(measurement_date):
        raise ValueError('account-publication-before-measurement')
    if (not isinstance(source, dict) or set(source) != {'path', 'sha256'}
        or source['path'] != 'spec/modernization/carddemo-screens/upstream/app/cbl/COACTUPC.cbl'
        or not isinstance(source['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', source['sha256'])):
        raise ValueError('account-publication-source')
    result = {}; seen = set()
    for key in GROUPS:
        scope = scopes[key]
        if (scope.get('schema') != 'carddemo-idiomatic-java-scope/1'
            or scope.get('program') != 'COACTUPC' or scope.get('source') != source
            or scope.get('remaining_statement_engine_programs') != list(ENGINE_PROGRAMS)):
            raise ValueError('account-publication-scope-source')
        paragraphs = _strings(scope.get('validation_paragraphs'), 'account-publication-paragraphs')
        if any(not re.fullmatch(r'[0-9]{4}-[A-Z0-9-]+', item) for item in paragraphs) or seen.intersection(paragraphs):
            raise ValueError('account-publication-paragraphs')
        seen.update(paragraphs)
        result[key] = dict(validation_paragraphs=paragraphs,
            rule_methods=_strings(scope.get('rule_methods'), 'account-publication-methods'),
            java_files=_strings(scope.get('java_files'), 'account-publication-java-files'))
    return dict(program='COACTUPC', publication_date=group['publication_date'],
        measurement_date=measurement_date, whole_screen_idiomatic=False, groups=result,
        validation_paragraph_count=len(seen), remaining_statement_engine_programs=list(ENGINE_PROGRAMS))


def scope_paragraph(value):
    return (f"As of {value['publication_date']}, the COACTUPC publication scope covers "
        f"{value['validation_paragraph_count']} validation paragraphs in {len(value['groups'])} groups. "
        f"The bound proof retains its measurement date {value['measurement_date']}. "
        'The whole account screen remains incomplete. Statement-engine programs: '
        + ', '.join(value['remaining_statement_engine_programs']) + '. '
        'Scope classification alone does not establish a passing proof or merge readiness.')


"""Source-bound paragraph classification, not execution or equivalence proof."""
import argparse
import ast
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re

BASE = 'spec/modernization/carddemo-screens/'
JAVA = 'factory/carddemo-web/service/src/main/java/ai/lightyear/carddemo/'
PATHS = [BASE + 'paragraph-scope-' + p + '.json' for p in ('COACTUPC', 'COSGN00C')]
ANNOTATION = r'@CobolSource\(program="([^"]+)", paragraph="([^"]+)", lines="([^"]+)"\)'
DIRECT = {'AccountUpdateService.java', 'AccountUpdateTransaction.java', 'SignonService.java', 'ScreenFrame.java'}


def require(value, code):
    if not value:
        raise ValueError(code)


def raw(root, path):
    require(not Path(path).is_absolute() and '..' not in Path(path).parts and '\\' not in path, 'scope-path')
    return (Path(root) / path).read_bytes().replace(b'\r\n', b'\n')


def inventory(source):
    return [dict(name=line[7:72].strip()[:-1], line=i + 1)
            for i, line in enumerate(source.decode().splitlines())
            if len(line) > 7 and line[6] != '*' and line[7] != ' '
            and re.fullmatch('[A-Z0-9][A-Z0-9-]*[.]', line[7:72].strip())]


def java_annotations(code):
    # Preserve quoted strings while removing comments before matching annotations.
    code = re.sub(r'"(?:\\.|[^"\\])*"|/\*[\s\S]*?\*/|//[^\n]*',
                  lambda m: m[0] if m[0].startswith('"') else ' ', code)
    block = r'((?:' + ANNOTATION + r'\s*)+)(?:@Override\s*)?(?:public|private|protected)\s+(?:static\s+)?[^;{]+?\b(\w+)\s*\('
    rows = []
    for match in re.finditer(block, code):
        method = match.groups()[-1]
        rows.extend(dict(program=p, paragraph=n, lines=s, method=method)
                    for p, n, s in re.findall(ANNOTATION, match[1]))
    return rows


def native_routes(root):
    tree = ast.parse(raw(root, 'src/lightyear_data/carddemo/update_edits.py'))
    build = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'build')
    result = {}
    def mapping(node):
        require(isinstance(node, ast.DictComp) and len(node.generators) == 1, 'native-route-form')
        generator = node.generators[0]
        require(not generator.ifs and not generator.is_async and isinstance(node.key, ast.Name)
                and isinstance(generator.target, ast.Name) and node.key.id == generator.target.id, 'native-route-form')
        names, target = ast.literal_eval(generator.iter), ast.literal_eval(node.value)
        require(all(isinstance(n, str) for n in names) and isinstance(target, str), 'native-route-literals')
        return dict.fromkeys(names, target)
    for node in build.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == 'native_paragraphs':
                    require(not result, 'native-route-reset'); result.update(mapping(node.value))
                elif isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name) and target.value.id == 'native_paragraphs':
                    result[ast.literal_eval(target.slice)] = ast.literal_eval(node.value)
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value
            if isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name) and call.func.value.id == 'native_paragraphs':
                require(call.func.attr == 'update' and len(call.args) == 1 and not call.keywords, 'native-route-form')
                result.update(mapping(call.args[0]))
    require(result, 'native-routes-empty')
    for filename in ('AccountPhoneDateModel.java', 'AccountMapModel.java'):
        code = raw(root, JAVA + filename).decode()
        match = re.search(r'RULES=Map.of\(([\s\S]*?)\);', code)
        require(match, 'model-route-form')
        pairs = re.findall(r'"([^"]+)"\s*,\s*"([^"]+)"', match[1])
        require(pairs and not set(result).intersection(p for p, _ in pairs), 'model-route-duplicate')
        result.update(pairs)
    edits = raw(root, JAVA + 'SourceEdits.java').decode()
    require(all('case "' + name + '"' in edits for name in set(result.values())), 'native-dispatch-class')
    require('AccountMapModel.retire(' in raw(root, JAVA + 'AccountUpdateService.java').decode()
            and 'AccountPhoneDateModel.retire(original)' in raw(root, JAVA + 'AccountMapModel.java').decode(), 'production-route-chain')
    return result


def check(root, manifest):
    program = manifest['program']
    require(manifest['schema'] == 'carddemo-paragraph-scope/1' and program in ('COACTUPC', 'COSGN00C'), 'scope-schema')
    require(manifest['source']['path'] == BASE + 'upstream/app/cbl/' + program + '.cbl', 'scope-source-path')
    source = raw(root, manifest['source']['path']); lines = source.decode().splitlines()
    require(sha256(source).hexdigest() == manifest['source']['sha256'], 'scope-source-hash')
    labels = inventory(source); rows = manifest['paragraphs']
    require(len(labels) == (88 if program == 'COACTUPC' else 6), 'source-inventory-count')
    require([dict(name=r['name'], line=r['line']) for r in rows] == labels
            and len({r['name'] for r in rows}) == len(rows), 'paragraph-inventory-exactly-once')
    require(manifest['routing_sources'], 'routing-bindings-empty')
    for path, digest in manifest['routing_sources'].items():
        require(sha256(raw(root, path)).hexdigest() == digest, 'routing-source-changed:' + path)
    needed = {'src/lightyear_data/carddemo/update_edits.py', JAVA + 'SourceEdits.java',
              JAVA + 'AccountMapModel.java', JAVA + 'AccountPhoneDateModel.java',
              *(JAVA + name for name in DIRECT)}
    require(needed <= set(manifest['routing_sources']), 'routing-binding-closure')
    native = native_routes(root) if program == 'COACTUPC' else {}
    annotations = {}
    for path in sorted((Path(root) / JAVA).glob('*.java')):
        annotations[path.name] = java_annotations(path.read_text(encoding='utf-8'))
    direct = {a['paragraph'] for name in DIRECT for a in annotations[name] if a['program'] == program}
    names = {r['name'] for r in rows}
    dispatched = (set(native) & names) | direct
    by_name = {r['name']: r for r in rows}
    for row in rows:
        category = row['classification']
        require(category in ('java', 'engine', 'not-applicable'), 'paragraph-classification')
        if category != 'java':
            require(isinstance(row.get('reason'), str) and row['reason'].strip(), 'paragraph-reason')
            require(row['name'] not in dispatched and 'java' not in row, 'engine-or-exit-dispatched-to-java')
            if category == 'not-applicable':
                metadata = row['name'] in {'PROGRAM-ID', 'DATE-WRITTEN', 'DATE-COMPILED'} and row['line'] < 859 and program == 'COACTUPC'
                statements = [s[7:72].strip() for s in lines[row['line']:row['line'] + 3] if len(s) > 7 and s[6] != '*' and s[7:72].strip()]
                require(metadata or row['name'].endswith('-EXIT') and ''.join(statements).startswith('EXIT.'), 'non-executable-classification')
            continue
        binding = row['java']; path = binding['file']; annotation = binding['annotation']
        require(path == JAVA + binding['class'] + '.java' and path in manifest['routing_sources'], 'java-file-binding')
        require(dict(annotation, method=binding['method']) in annotations[Path(path).name], 'java-annotation-method-binding')
        require(annotation['program'] == program and annotation['paragraph'] in names, 'annotation-program-paragraph')
        span = annotation['lines'].split('-'); require(len(span) == 2, 'annotation-range')
        first, last = map(int, span)
        require(1 <= first <= row['line'] <= last <= len(lines), 'annotation-source-range')
        span_bytes = ('\n'.join(lines[first-1:last]) + '\n').encode()
        require(sha256(span_bytes).hexdigest() == binding['source_span_sha256'], 'annotation-source-span-hash')
        parent = row.get('covered_by', row['name'])
        require(annotation['paragraph'] == parent and parent in dispatched, 'java-dispatch-binding')
        if parent != row['name']:
            require(by_name[parent]['classification'] == 'java' and by_name[parent]['java'] == binding, 'covered-paragraph-binding')
        if parent in native:
            require(binding['class'] == native[parent], 'native-class-binding')
        else:
            require(Path(path).name in DIRECT, 'direct-class-binding')
    # A nested body covered by a retired native paragraph cannot be relabelled engine.
    for row in rows:
        if row['classification'] == 'not-applicable': continue
        for parent in rows:
            if parent['classification'] != 'java' or parent['name'] not in native: continue
            first, last = map(int, parent['java']['annotation']['lines'].split('-'))
            if first <= row['line'] <= last:
                require(row['classification'] == 'java', 'covered-body-still-labelled-engine')
    counts = {kind: Counter(r['classification'] for r in rows)[kind] for kind in ('java', 'engine', 'not-applicable')}
    return dict(program=program, inventory=len(rows), counts=counts, source_sha256=manifest['source']['sha256'],
                scope_only=True, equivalence_or_mutation_proof=False)


def inputs(root):
    present = [p for p in PATHS if (Path(root) / p).exists()]
    if not present: return []
    require(len(present) == 2, 'both-program-manifests-required')
    paths = set(present)
    for path in present:
        record = json.loads(raw(root, path)); paths.add(record['source']['path']); paths.update(record['routing_sources'])
    return sorted(paths)


def load(root):
    if not inputs(root): return None
    return [check(root, json.loads(raw(root, path))) for path in PATHS]


def markdown(value):
    lines = ['| Program | Inventory entries | Java | Engine | Not applicable |', '|---|---:|---:|---:|---:|']
    for row in value:
        counts = row['counts']
        lines.append(f"| {row['program']} | {row['inventory']} | {counts['java']} | {counts['engine']} | {counts['not-applicable']} |")
    lines.append('Counts classify source scope, not passing execution or mutation proof. The retained full-slice 678/678 proof is unchanged. COACTUPC inventory includes three identification headers and its exit labels.')
    return '\n'.join(lines)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--root', type=Path, default=Path('.'))
    parser.add_argument('--out', type=Path, required=True); args = parser.parse_args()
    result = load(args.root); require(result is not None, 'paragraph-manifests-missing')
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
