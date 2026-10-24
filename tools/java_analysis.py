"""CI-only Java static-analysis capture; an unreviewed baseline never passes."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

SERVICE = Path('factory/carddemo-web/service')
CONFIG = Path('spec/modernization/java-analysis')
VERSIONS = {'checkstyle': '3.6.0', 'checkstyle_engine': '10.21.4',
            'errorprone': '2.38.0', 'compiler': '3.14.0', 'spotbugs': '4.9.3.0'}
NS = 'http://maven.apache.org/POM/4.0.0'
ET.register_namespace('', NS)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def require(condition, code):
    if not condition:
        raise ValueError(code)


def emit(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def add(parent, tag, value=None):
    child = ET.SubElement(parent, '{' + NS + '}' + tag)
    if value is not None:
        child.text = str(value)
    return child


def analysis_pom(original, tool, output, source=None):
    """Only an exclusive disposable copy is written; the frozen POM stays intact."""
    root = ET.fromstring(original)
    build = root.find('{' + NS + '}build')
    if build is None:
        build = add(root, 'build')
    directory = build.find('{' + NS + '}directory')
    if directory is None:
        directory = add(build, 'directory')
    directory.text = str(output)
    if source is not None:
        add(build, 'sourceDirectory', source)
    plugins = build.find('{' + NS + '}plugins')
    if plugins is None:
        plugins = add(build, 'plugins')
    artifact = {'checkstyle': 'maven-checkstyle-plugin',
                'errorprone': 'maven-compiler-plugin', 'spotbugs': 'spotbugs-maven-plugin'}[tool]
    require(not any(p.findtext('{' + NS + '}artifactId') == artifact for p in plugins),
            'existing-analysis-plugin-needs-review')
    plugin = add(plugins, 'plugin')
    add(plugin, 'groupId', 'com.github.spotbugs' if tool == 'spotbugs' else 'org.apache.maven.plugins')
    add(plugin, 'artifactId', artifact)
    add(plugin, 'version', VERSIONS['compiler' if tool == 'errorprone' else tool])
    config = add(plugin, 'configuration')
    if tool == 'checkstyle':
        add(config, 'configLocation', (CONFIG / 'checkstyle.xml').resolve())
        add(config, 'outputFile', output / 'checkstyle.xml')
        add(config, 'outputFileFormat', 'xml')
        add(config, 'includeResources', 'false')
        add(config, 'includeTestResources', 'false')
        add(config, 'includeTestSourceDirectory', 'false')
        add(config, 'failsOnError', 'false')
        dependency = add(add(plugin, 'dependencies'), 'dependency')
        for key, value in [('groupId', 'com.puppycrawl.tools'), ('artifactId', 'checkstyle'),
                           ('version', VERSIONS['checkstyle_engine'])]:
            add(dependency, key, value)
    elif tool == 'spotbugs':
        for key, value in [('xmlOutput', 'true'), ('spotbugsXmlOutputDirectory', output),
                           ('spotbugsXmlOutputFilename', 'spotbugs.xml'), ('effort', 'Max'),
                           ('threshold', 'Low'), ('failOnError', 'true'), ('noClassOk', 'false')]:
            add(config, key, value)
    else:
        for key, value in [('fork', 'true'), ('showWarnings', 'true'), ('encoding', 'UTF-8'),
                           ('release', '21'), ('useIncrementalCompilation', 'false')]:
            add(config, key, value)
        args = add(config, 'compilerArgs')
        # Collect all findings without stopping at the first error. The final
        # baseline gate, not compiler warning severity, decides acceptance.
        for value in ['-XDcompilePolicy=simple', '--should-stop=ifError=FLOW',
                      '-Xplugin:ErrorProne -XepAllErrorsAsWarnings',
                      '-XDaddTypeAnnotationsToSymbol=true', '-Xmaxwarns', '100000',
                      '-Xmaxerrs', '100000']:
            add(args, 'arg', value)
        for group in ('api', 'file', 'main', 'model', 'parser', 'processing', 'tree', 'util'):
            add(args, 'arg', '-J--add-exports=jdk.compiler/com.sun.tools.javac.' + group + '=ALL-UNNAMED')
        for group in ('code', 'comp'):
            add(args, 'arg', '-J--add-opens=jdk.compiler/com.sun.tools.javac.' + group + '=ALL-UNNAMED')
        dependency = add(add(config, 'annotationProcessorPaths'), 'path')
        for key, value in [('groupId', 'com.google.errorprone'), ('artifactId', 'error_prone_core'),
                           ('version', VERSIONS['errorprone'])]:
            add(dependency, key, value)
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


def row(path, rule, line):
    require(isinstance(rule, str) and bool(rule), 'missing-rule')
    require(int(line) > 0, 'missing-source-line')
    return {'path': path, 'rule': rule, 'line': int(line)}


def parse(tool, output, sources):
    """Retain location, rule and multiplicity, refusing unknown source paths."""
    by_suffix = {p.replace('\\', '/'): p for p in sources}

    def locate(value):
        value = value.replace('\\', '/')
        hits = [path for suffix, path in by_suffix.items()
                if value == suffix or value.endswith('/' + suffix)]
        require(len(hits) == 1, 'unknown-or-ambiguous-analysis-source')
        return hits[0]

    rows = []
    if tool == 'checkstyle':
        root = ET.parse(output / 'checkstyle.xml').getroot()
        require(root.tag == 'checkstyle', 'checkstyle-schema')
        files = root.findall('file')
        seen = [locate(f.attrib['name']) for f in files]
        require(len(seen) == len(set(seen)) and set(seen) == set(sources), 'checkstyle-source-coverage')
        for file, path in zip(files, seen):
            for error in file.findall('error'):
                rows.append(row(path, error.attrib['source'], error.attrib['line']))
    elif tool == 'spotbugs':
        root = ET.parse(output / 'spotbugs.xml').getroot()
        require(root.tag == 'BugCollection', 'spotbugs-schema')
        require(not root.findall('.//MissingClass') and not root.findall('.//Error'), 'spotbugs-incomplete')
        errors = root.find('Errors')
        require(errors is None or int(errors.get('errors', '0')) == 0, 'spotbugs-errors')
        require(root.find('FindBugsSummary') is not None, 'spotbugs-missing-summary')
        for bug in root.findall('BugInstance'):
            lines = bug.findall('SourceLine')
            primary = [line for line in lines if line.get('primary') == 'true']
            require(bool(primary or lines), 'spotbugs-missing-location')
            line = (primary or lines)[0]
            # SpotBugs uses package-relative source paths.
            suffix = line.attrib['sourcepath']
            hits = [p for p in sources if p.endswith('/' + suffix)]
            require(len(hits) == 1, 'spotbugs-source-ambiguity')
            rows.append(row(hits[0], bug.attrib['type'], line.attrib['start']))
    else:
        log = (output / 'maven.log').read_text(encoding='utf-8')
        diagnostics = re.findall(r'(?m)^.*?([^\s]+\.java):\[(\d+),\d+\]\s+(?:warning:\s*)?\[([A-Za-z0-9]+)\]', log)
        diagnostics += re.findall(r'(?m)^.*?([^\s]+\.java):(\d+):\s*warning:\s*\[([A-Za-z0-9]+)\]', log)
        # Maven may repeat diagnostics in a summary. Identical locations/rules
        # represent one javac finding; different locations are never collapsed.
        rows = [row(locate(p), rule, line) for p, line, rule in sorted(set(diagnostics))]
        require('BUILD SUCCESS' in log, 'errorprone-compilation-incomplete')
        require('Compiling' in log, 'errorprone-compilation-not-observed')
        require(not re.search(r'only showing the first|of \d+ total|100000 warnings', log), 'errorprone-diagnostics-truncated')
    return sorted(rows, key=lambda r: (r['path'], r['line'], r['rule']))


def gate(reports, baseline, previous):
    require(baseline.get('status') == 'reviewed', 'java-analysis-baseline-awaits-review')
    require(set(reports) == {'checkstyle', 'errorprone', 'spotbugs'}, 'analysis-tool-coverage')
    require(baseline['versions'] == VERSIONS, 'analysis-version-drift')
    canonical = lambda r: json.dumps(r, sort_keys=True, separators=(',', ':'))
    for tool, report in reports.items():
        require(report['tool'] == tool and report['complete'] and report['negative_control'], 'analysis-incomplete')
        require(report['versions'] == VERSIONS and report['checkout'] == reports['checkstyle']['checkout'], 'analysis-binding')
        actual = Counter(map(canonical, report['findings']))
        allowed = Counter(map(canonical, baseline['findings'][tool]))
        require(not actual - allowed, 'new-java-analysis-findings:' + tool)
        # Once main has a reviewed baseline, increases require a separate policy
        # change; ordinary PRs can only remove entries, never add allowances.
        if previous.get('status') == 'reviewed':
            require(previous['versions'] == VERSIONS, 'trusted-baseline-version')
            require(not allowed - Counter(map(canonical, previous['findings'][tool])), 'baseline-expanded:' + tool)


def run_tool(tool, project, original, output, sources, source_dir=None):
    output.mkdir(parents=True, exist_ok=False)
    pom = project / ('.k1-analysis-' + tool + '.pom.xml')
    payload = analysis_pom(original, tool, output.resolve(), source_dir)
    with pom.open('xb') as handle:
        handle.write(payload)
    goals = {'checkstyle': ['checkstyle:checkstyle'], 'errorprone': ['compile'],
             'spotbugs': ['compile', 'spotbugs:spotbugs']}[tool]
    command = ['mvn', '-B', '-ntp', '-Dstyle.color=never', '-DskipTests', '-f', str(pom), *goals]
    try:
        proc = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        (output / 'maven.log').write_bytes(proc.stdout)
        require(proc.returncode == 0, 'analysis-command-failed:' + tool)
        return parse(tool, output, sources)
    finally:
        require(pom.read_bytes() == payload, 'analysis-pom-mutated')
        pom.unlink()


def capture(tool, output):
    require(os.environ.get('CI') == 'true', 'ci-only-analysis')
    require(not output.exists(), 'output-already-exists')
    output.mkdir(parents=True)
    original = (SERVICE / 'pom.xml').read_bytes()
    tracked = subprocess.check_output(['git', 'ls-files', '-z']).decode().split('\0')
    sources = {p: sha(Path(p).read_bytes()) for p in tracked if p.startswith(SERVICE.as_posix() + '/src/main/java/') and p.endswith('.java')}
    require(bool(sources), 'empty-java-scope')
    checkout = subprocess.check_output(['git', 'rev-parse', 'HEAD']).decode().strip()
    # Disposable sources are outside both the frozen test tree and production.
    canary = output / 'negative-control'
    canary.mkdir()
    source = canary / 'src' / 'AnalysisCanary.java'
    source.parent.mkdir()
    source.write_text('import java.util.*;\npublic class AnalysisCanary {\n'
                      '  public void broken() { int Bad_name = 1; int other = 2; new Exception(); }\n'
                      '  public boolean equal(String left, String right) { return left == right; }\n}\n', encoding='utf-8')
    minimal = ('<project xmlns="' + NS + '"><modelVersion>4.0.0</modelVersion>'
               '<groupId>synthetic</groupId><artifactId>analysis-canary</artifactId><version>1</version>'
               '<properties><maven.compiler.release>21</maven.compiler.release>'
               '<maven.compiler.source>21</maven.compiler.source><maven.compiler.target>21</maven.compiler.target>'
               '</properties></project>').encode()
    canary_rows = run_tool(tool, canary, minimal, canary / 'result', {source.as_posix(): sha(source.read_bytes())}, source.parent.resolve())
    expected = {'checkstyle': ('OneStatementPerLineCheck', 'AvoidStarImportCheck'),
                'errorprone': ('DeadException',), 'spotbugs': ('ES_COMPARING_STRINGS_WITH_EQ',)}[tool]
    require(all(any(r['rule'].endswith(rule) for r in canary_rows) for rule in expected), 'negative-control-not-detected')
    findings = run_tool(tool, SERVICE, original, output / 'actual', sources)
    require((SERVICE / 'pom.xml').read_bytes() == original, 'frozen-pom-changed')
    require(all(sha(Path(p).read_bytes()) == digest for p, digest in sources.items()), 'java-source-changed')
    report = dict(schema='java-analysis-capture/1', tool=tool, versions=VERSIONS, complete=True,
                  negative_control=True, checkout=checkout, run=os.environ.get('GITHUB_RUN_ID'),
                  attempt=os.environ.get('GITHUB_RUN_ATTEMPT'), pom_sha256=sha(original),
                  source_hashes=sources, findings=findings, finding_count=len(findings),
                  proof_rerun=False, idiomatic_index_change=None, baseline_approved=False)
    emit(output / 'report.json', report)
    print(json.dumps({'tool': tool, 'findings': len(findings), 'sources': len(sources), 'baseline_approved': False}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['capture', 'gate'])
    parser.add_argument('--tool', choices=['checkstyle', 'errorprone', 'spotbugs'])
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--base')
    args = parser.parse_args()
    if args.command == 'capture':
        require(args.tool is not None, 'missing-tool')
        capture(args.tool, args.out)
    else:
        path = CONFIG / 'baseline.json'
        require(args.base is not None, 'missing-trusted-base')
        base = subprocess.check_output(['git', 'rev-parse', '--verify', args.base + '^{commit}']).decode().strip()
        exists = subprocess.run(['git', 'cat-file', '-e', base + ':' + path.as_posix()], capture_output=True).returncode == 0
        previous = json.loads(subprocess.check_output(['git', 'show', base + ':' + path.as_posix()])) if exists else {'status': 'absent'}
        reports = {tool: json.loads((args.out / tool / 'report.json').read_text()) for tool in ('checkstyle', 'errorprone', 'spotbugs')}
        gate(reports, json.loads(path.read_text()), previous)
        print('Reviewed Java analysis baseline: no new findings.')


if __name__ == '__main__':
    main()
