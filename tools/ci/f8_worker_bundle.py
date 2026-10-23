"""CI-only public support capsule; never a factory/admission/model run."""
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import xml.etree.ElementTree as ET
import zipfile

CAP = 'work/f8-public-worker-capsule'
DOC = 'docs/factory/copau-f8-'
MI = 1024 * 1024
PAYLOAD = {'capsule.tar.gz', 'capsule-files.json', 'workspace-manifest.json', 'conformance.json', 'summary.json'}
NS = {'m': 'http://maven.apache.org/POM/4.0.0'}
ET.register_namespace('', NS['m'])

def sha(raw): return hashlib.sha256(raw).hexdigest()

def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(value, indent=2, sort_keys=True) + '\n').encode())

def inventory(root):
    rows = {}; total = 0
    for p in sorted(root.rglob('*')):
        if p.is_symlink(): raise ValueError('capsule-link')
        if p.is_dir(): continue
        info = p.stat(); total += info.st_size
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 8 * MI or total > 32 * MI:
            raise ValueError('capsule-file-or-size')
        rows[p.relative_to(root).as_posix()] = sha(p.read_bytes())
        if len(rows) > 4096: raise ValueError('capsule-count')
    return rows

def inspect_capsule(raw, expected):
    if not isinstance(expected, dict) or not expected or len(expected) > 4096: raise ValueError('capsule-map')
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream: data = stream.read(40 * MI + 1)
    if len(data) > 40 * MI: raise ValueError('capsule-expanded-size')
    rows = {}; total = 0
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:') as archive:
        for entry in archive:
            name = entry.name; parts = name.split('/'); total += entry.size
            if (not entry.isreg() or entry.sparse or name.startswith('/') or ':' in name or '\\' in name
                    or any(p in ('', '.', '..', '.git') for p in parts) or name in rows
                    or entry.size > 8 * MI or total > 32 * MI or len(rows) >= 4096):
                raise ValueError('capsule-entry')
            rows[name] = sha(archive.extractfile(entry).read())
    if rows != expected: raise ValueError('capsule-digest')
    return rows

def project(text, name):
    if name == 'ScreenFrame.java':
        if text.count('List<SourceEdits.Location> trace') != 1: raise ValueError('trace-projection-drift')
        text = text.replace('List<SourceEdits.Location> trace', 'List trace')
    if name == 'AuthorizationRecords.java':
        text, count = re.subn(r'\n    public void load\(SourceEdits[^\n]*\{.*?\n    }\n', '\n', text, flags=re.S)
        if count != 1: raise ValueError('load-projection-drift')
    if 'SourceEdits' in text: raise ValueError('engine-reference')
    return text

def run(args):
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=900)
    if result.returncode:
        print('\n'.join(result.stdout.decode(errors='replace').splitlines()[-50:]), file=sys.stderr)
        raise RuntimeError('CI command failed: ' + args[0])
    return result.stdout

def fixture_pom(original):
    doc = ET.fromstring(original); build = doc.find('m:build', NS)
    for tag, value in [('sourceDirectory', '${project.basedir}/empty'), ('testSourceDirectory', '${project.basedir}/tests'), ('directory', '${project.basedir}/output')]:
        build.find('m:' + tag, NS).text = value
    build.remove(build.find('m:testResources', NS))
    return ET.tostring(doc)

def probe(source, image, missing=False):
    from lightyear_execution.backend import OCIContainerBackend
    from lightyear_execution.contracts import ExecutionPolicy
    from lightyear_factory.contracts import GateContract
    from lightyear_factory.gates import GateRunner
    from lightyear_factory.workspace import IsolatedWorkspace
    policy = json.loads(Path('factory/execution/policy.json').read_bytes())
    policy['runtime'].update(image=image['image'], image_digest=image['image_digest'], allowed_commands=['mvn'])
    policy['isolation'].update(memory_mb=4096, tmpfs_mb=1024, cpus=2.0, pids_limit=256)
    policy['admission']['trusted_key_ids'] = ['fixture-only-unused-no-key']
    dest = source.parent / ('missing-worker' if missing else 'worker')
    ws = IsolatedWorkspace(source, dest, ('probe',), read_manifest=inventory(source)); ws.create()
    if missing:
        next((dest / CAP / 'm2/ai/lightyear/worker/carddemo-shared-support').rglob('*.jar')).unlink()
    private = source.parent / 'controller-only-decoy.txt'; private.write_text('F8_CONTROLLER_ONLY_DECOY')
    def scan(surface, raw):
        if b'F8_CONTROLLER_ONLY_DECOY' in raw or any(t.encode() in raw for t in ws.canaries.values()):
            raise ValueError('fixture-isolation-breach')
    runner = GateRunner(dest, backend=OCIContainerBackend(ExecutionPolicy.from_dict(policy), 'docker', execute=True), require_container=True, isolation_scan=scan)
    args = ['mvn', '-o', '-B', '-ntp', '-C', '-s', CAP + '/settings.xml', '-gs', CAP + '/settings.xml', '-f', 'probe/pom.xml', '-Dmaven.repo.local=/tmp/factory-build/' + CAP + '/m2', '-Duser.home=/tmp/factory-build/' + CAP + '/home', '-Df8.isolated=true', '-Df8.private.path=' + str(private), 'test']
    report = runner.run((GateContract('offline-missing' if missing else 'offline-isolation', tuple(args), 600, False),))
    row = report['gates'][0]; text = row['stdout'] + row['stderr']
    if missing:
        if row['status'] != 'failed' or row['timed_out'] or 'carddemo-shared-support' not in text or 'offline' not in text.lower(): raise ValueError('missing-dependency-not-refused')
    elif row['status'] != 'passed' or 'F8_ISOLATION_CHECKS_PASSED' not in text:
        raise ValueError('offline-isolation-not-proven')
    ws.scan_contents(scan, 'fixture-workspace') if not missing else None
    return report

def assemble(output):
    output.mkdir(parents=True, exist_ok=True)
    spec = json.loads(Path(DOC + 'support-bindings-j2-2026-10-22.json').read_bytes())
    image = json.loads(Path(DOC + 'java-image-pin-r2-2026-10-20.json').read_bytes())['selection']
    run(['docker', 'pull', image['reference']])
    actual = json.loads(run(['docker', 'image', 'inspect', image['reference']]))[0]
    if actual['Architecture'] != 'amd64' or actual['Os'] != 'linux' or actual['Id'] != 'sha256:' + image['config_sha256']: raise ValueError('image-identity')
    versions = run(['docker', 'run', '--rm', image['reference'], 'mvn', '-version']) + run(['docker', 'run', '--rm', image['reference'], 'java', '-version'])
    if image['maven'].encode() not in versions or b'21.0.12.1+1' not in versions: raise ValueError('toolchain-version')
    stage = Path(tempfile.mkdtemp(prefix='f8-public-build-', dir=output.parent)); cap = stage / CAP
    for name in ('home/.keep', 'tmp/.keep'): (cap / name).parent.mkdir(parents=True, exist_ok=True); (cap / name).touch()
    for proposal, name in [('worker-pom-proposal', 'pom.xml'), ('worker-settings-proposal', 'settings.xml')]:
        (cap / name).write_bytes(Path(DOC + proposal + '-r2-2026-10-20.xml').read_bytes())
    support = stage / 'support'; projected = {}
    for row in spec['selection']['source_bindings']:
        raw = Path(row['path']).read_bytes()
        if sha(raw) != row['sha256']: raise ValueError('shared-source-drift')
        path = support / 'src/ai/lightyear/carddemo' / Path(row['path']).name
        path.parent.mkdir(parents=True, exist_ok=True); path.write_text(project(raw.decode(), path.name))
        projected[row['path']] = {'source_sha256': row['sha256'], 'projected_sha256': sha(path.read_bytes())}
    doc = ET.fromstring((cap / 'pom.xml').read_bytes()); doc.find('m:artifactId', NS).text = 'carddemo-shared-support'
    deps = doc.find('m:dependencies', NS)
    for dep in list(deps):
        if dep.find('m:artifactId', NS).text != 'jackson-databind': deps.remove(dep)
    build = doc.find('m:build', NS); build.find('m:sourceDirectory', NS).text = '${project.basedir}/src'; build.find('m:directory', NS).text = '${project.basedir}/target'
    ET.ElementTree(doc).write(support / 'pom.xml')
    def online(pom):
        return run(['docker', 'run', '--rm', '--user', f'{os.getuid()}:{os.getgid()}', '-e', 'MAVEN_CONFIG=/tmp/f8-maven', '--mount', f'type=bind,src={stage},dst=/workspace', '--workdir', '/workspace', image['reference'], 'mvn', '-B', '-ntp', '-C', '-Dmaven.repo.local=/workspace/' + CAP + '/m2', '-Duser.home=/tmp', '-f', pom, 'test' if pom.startswith('probe') else 'compile'])
    online('support/pom.xml')
    classes = {p.relative_to(support / 'target/classes').as_posix(): p.read_bytes() for p in (support / 'target/classes').rglob('*.class')}
    if set(classes) != set(spec['selection']['allowed_jar_class_entries']) or any(b'SourceEdits' in b for b in classes.values()): raise ValueError('support-class-closure')
    artifact = cap / 'm2/ai/lightyear/worker/carddemo-shared-support/0.1.0-f8/carddemo-shared-support-0.1.0-f8'
    artifact.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(str(artifact) + '.jar', 'w', compression=zipfile.ZIP_DEFLATED) as jar:
        for name, raw in sorted(classes.items()): jar.writestr(zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0)), raw)
    doc.remove(build); Path(str(artifact) + '.pom').write_bytes(ET.tostring(doc))
    (artifact.parent / '_remote.repositories').write_text(artifact.name + '.jar>=\n' + artifact.name + '.pom>=\n')
    fixture = stage / 'probe'; (fixture / 'tests').mkdir(parents=True)
    (fixture / 'pom.xml').write_bytes(fixture_pom((cap / 'pom.xml').read_bytes()))
    shutil.copyfile('tools/ci/f8_worker_fixture/PackagingTest.java', fixture / 'tests/PackagingTest.java')
    for name in ('home/.keep', 'tmp/.keep'): (fixture / name).parent.mkdir(parents=True, exist_ok=True); (fixture / name).touch()
    online('probe/pom.xml')
    for p in (cap / 'm2').rglob('*'):
        if p.is_file() and p.suffix not in ('.jar', '.pom') and p.name != '_remote.repositories': p.unlink()
    capsule = inventory(cap); source = stage / 'probe-source'; source.mkdir()
    public = json.loads(Path(DOC + 'workspace-manifest-proposal-2026-10-20.json').read_bytes())
    for path, digest in public.items():
        if path.endswith('.java'): continue
        raw = Path(path).read_bytes()
        if sha(raw) != digest: raise ValueError('public-source-drift')
        target = source / path; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(raw)
    shutil.copytree(cap, source / CAP); (source / 'probe/tests').mkdir(parents=True)
    for path in ('pom.xml', 'tests/PackagingTest.java', 'home/.keep', 'tmp/.keep'):
        target = source / 'probe' / path; target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(fixture / path, target)
    positive = probe(source, image); negative = probe(source, image, missing=True)
    workspace = {p: d for p, d in inventory(source).items() if not p.startswith('probe/')}
    raw_tar = io.BytesIO()
    with tarfile.open(fileobj=raw_tar, mode='w') as archive:
        for name in capsule:
            raw = (cap / name).read_bytes(); entry = tarfile.TarInfo(name); entry.size = len(raw); entry.mode = 0o644; archive.addfile(entry, io.BytesIO(raw))
    payload = gzip.compress(raw_tar.getvalue(), mtime=0); inspect_capsule(payload, capsule)
    (output / 'capsule.tar.gz').write_bytes(payload); save(output / 'capsule-files.json', capsule); save(output / 'workspace-manifest.json', workspace)
    save(output / 'conformance.json', {'schema': 'f8-worker-conformance/1', 'positive': positive, 'missing_dependency': negative, 'fixture_only': True, 'factory_run_acceptance': False, 'source_projections': projected, 'class_hashes': {p: sha(b) for p, b in classes.items()}})
    save(output / 'summary.json', {'schema': 'f8-worker-bundle/1', 'source_head': run(['git', 'rev-parse', 'HEAD']).decode().strip(), 'source_run': int(os.environ['GITHUB_RUN_ID']), 'source_attempt': int(os.environ['GITHUB_RUN_ATTEMPT']), 'image': image['reference'], 'toolchain_versions': versions.decode(), 'capsule_sha256': sha(payload), 'capsule_bytes': len(payload), 'capsule_files_sha256': sha((output / 'capsule-files.json').read_bytes()), 'workspace_manifest_sha256': sha((output / 'workspace-manifest.json').read_bytes()), 'conformance_sha256': sha((output / 'conformance.json').read_bytes()), 'fixture_only': True, 'factory_run_acceptance': False})

if __name__ == '__main__':
    if os.environ.get('GITHUB_ACTIONS') != 'true': raise SystemExit('F8 packaging is CI-only')
    destination = Path(sys.argv[1]).resolve()
    try: assemble(destination)
    except Exception as error:
        save(destination / 'failure.json', {'schema': 'f8-worker-failure/1', 'type': type(error).__name__, 'error': str(error), 'factory_run_acceptance': False})
        raise
