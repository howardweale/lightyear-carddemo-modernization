"""Direct B06 JVM worker. No compiler, Maven, signer, judge or network client.

Mounted with the shared public bundle_content reader only. The host authorizes,
checks the image/mounts and supplies separately bound compiled class overlays.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
try:
    from bundle_content import bundle_content_view
except ModuleNotFoundError:
    from tools.b06_image_artifacts.bundle_content import bundle_content_view

LAYER = '/opt/lightyear/b06-build-once'
TEST = '/application/org.idempiere.test'
JDWP = '-agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=*:5005'
AGENTS = ['-javaagent:/results/agent.jar=/results/loaded',
          '-javaagent:/results/closure-agent.jar=/results/closure-observation.json']
CLASS = re.compile(r'target/classes/org/idempiere/test/(?:LightyearOperationsTest|JourneySupport|B06OutsideControl)(?:\$[A-Za-z0-9_$]+)?\.class')


def check(ok, reason):
    if not ok: raise ValueError(reason)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def seal(value):
    return {**value, 'content_sha256': hashlib.sha256(canonical(value)).hexdigest()}


def verify(value):
    check(value.get('content_sha256') == seal({k:v for k,v in value.items() if k != 'content_sha256'})['content_sha256'], 'built-native-content-hash')


def descriptor(path):
    p = Path(path); check(p.is_file() and not p.is_symlink(), 'built-native-file')
    h = hashlib.sha256()
    with p.open('rb') as stream:
        for block in iter(lambda:stream.read(65536), b''): h.update(block)
    return {'bytes':p.stat().st_size, 'sha256':h.hexdigest()}


def arguments(manifest):
    """Explicit prospective change: remove only the two practice agents; add JDWP."""
    verify(manifest)
    args = manifest['fork'][:]
    check(args[0] == '/opt/java/openjdk/bin/java' and args.count('-jar') == 1, 'built-native-java-command')
    jar = args.index('-jar')
    check([v for v in args[:jar] if v.startswith(('-javaagent', '-agentlib', '-agentpath', '-Xrun'))] == AGENTS, 'built-native-practice-agents')
    check(not any(v.startswith(('@', '-DPropertyFile=', '-Dlightyear.output=', '-Djava.io.tmpdir=')) for v in args), 'built-native-argument-injection')
    check(args[args.index('-testproperties')+1] == TEST+'/target/surefire.properties', 'built-native-test-properties-path')
    launcher = args[jar+1]
    check(launcher in manifest['artifacts'] and launcher.endswith('.jar'), 'built-native-launcher-not-bound')
    args = [v for v in args if v not in AGENTS]
    args[1:1] = [JDWP, '-DPropertyFile=/secrets/application.properties',
                 '-Dlightyear.output=/results/journey.xml', '-Djava.io.tmpdir=/results/java-tmp']
    check('-Duser.timezone=UTC' in args and '-Djunit.jupiter.execution.parallel.enabled=false' in args, 'built-native-real-clock-serial')
    return args


def properties(raw):
    # Preserve every byte except the one exact provider selector, including CRLF.
    old = b'__provider.tc.0=org.idempiere.test.B06RuntimeCatalogTest'
    new = b'__provider.tc.0=org.idempiere.test.LightyearOperationsTest'
    lines = raw.splitlines(keepends=True)
    check(sum(line.rstrip(b'\r\n') == old for line in lines) == 1, 'built-native-test-selector')
    check(sum(line.startswith(b'__provider.tc.') for line in lines) == 1, 'built-native-extra-test-selector')
    check(b'testpluginname=org.idempiere.test' in raw.splitlines(), 'built-native-test-plugin')
    return b''.join(new+line[len(old):] if line.rstrip(b'\r\n') == old else line for line in lines)


def validate_spec(manifest, spec):
    verify(manifest); verify(spec)
    check(spec['schema'] == 'b06-built-native-launch/1' and spec['manifest_sha256'] == manifest['content_sha256'], 'built-native-manifest-binding')
    check(spec['argv'] == arguments(manifest), 'built-native-command-differs')
    check(spec['model_calls'] == 0 and spec['rebuild'] is False, 'built-native-scope')
    check(re.fullmatch('sha256:[a-f0-9]{64}', spec['image']) is not None, 'built-native-image')
    overlays = spec['overlays']
    check(overlays and all(CLASS.fullmatch(k) for k in overlays), 'built-native-overlay-path')
    check('target/classes/org/idempiere/test/LightyearOperationsTest.class' in overlays and
          'target/classes/org/idempiere/test/JourneySupport.class' in overlays, 'built-native-required-class')
    baseline = manifest['base_applications']['org.idempiere.test']['entries']
    check({k for k in baseline if CLASS.fullmatch(k)} <= set(overlays), 'built-native-stale-candidate-class')
    for item in overlays.values():
        check(set(item) == {'bytes','sha256'} and type(item['bytes']) is int and item['bytes'] > 0 and
              re.fullmatch('[a-f0-9]{64}', item['sha256']), 'built-native-overlay-descriptor')
    return True


def verify_live(manifest, spec, resolve=Path):
    """Exact shared view before and after; only declared compiled classes may vary."""
    validate_spec(manifest, spec)
    result = {}
    for name, row in manifest['base_applications'].items():
        path = resolve(row['path'])
        actual = bundle_content_view(path, kind='jar' if row['kind']=='jar' else 'folder')['entries']
        expected = copy.deepcopy(row['entries'])
        if name == 'org.idempiere.test':
            check(row['path'] == TEST and row['kind'] == 'folder-archive', 'built-native-test-origin')
            expected.update({k:dict(kind='file', **v) for k,v in spec['overlays'].items()})
        check(actual == expected, 'built-native-application-changed:'+name)
        if row['kind'] == 'jar': check(descriptor(path)['sha256'] == row['jar_sha256'], 'built-native-jar-changed')
        result[name] = hashlib.sha256(canonical(actual)).hexdigest()
    check(descriptor(resolve(manifest['config_path']+'/config.ini'))['sha256']==manifest['base_config_sha256'], 'built-native-active-config-changed')
    for group in ('artifacts','source_files','sealed_files'):
        for path, expected in manifest[group].items():
            if path == manifest['testproperties_path']:
                expected = spec['testproperties']
            check(descriptor(resolve(path)) == {k:expected[k] for k in ('bytes','sha256')}, 'built-native-runtime-changed:'+path)
    return seal(dict(schema='b06-built-native-check/1', launch_sha256=spec['content_sha256'],
        manifest_sha256=manifest['content_sha256'], application_maps_sha256=result,
        overlays=spec['overlays'], argv=spec['argv'], verified=True))


def run(payload, *, resolve=Path, execute=subprocess.run):
    manifest = json.loads(resolve(LAYER+'/manifest.json').read_bytes())
    spec = json.loads(resolve('/runtime/launch.json').read_bytes())
    validate_spec(manifest, spec)
    check(payload['lane'] in ('oracle','postgresql') and 0 < payload['timeout_seconds'] <= 1800, 'built-native-payload')
    from datetime import date
    date.fromisoformat(payload['scenario_date'])
    props = resolve('/secrets/application.properties')
    check(not props.exists(), 'built-native-secret-already-exists')
    out = resolve('/results'); (out/'java-tmp').mkdir()
    def record(name, value):
        with (out/name).open('xb') as stream: stream.write(canonical(value))
    record('built-before.json', verify_live(manifest, spec, resolve))
    lane = payload['lane']; password = payload['password']
    check(not any(c in password for c in '\r\n]'), 'built-native-password-shape')
    port, database = (1521,'FREEPDB1') if lane == 'oracle' else (5432,'idempiere')
    connection = f'CConnection[name=Lightyear isolated,type={"Oracle" if lane=="oracle" else "PostgreSQL"},DBhost={lane},DBport={port},DBname={database},UID=adempiere,PWD={password}]'
    env = {k:v for k,v in os.environ.items() if k not in ('JAVA_TOOL_OPTIONS','JDK_JAVA_OPTIONS','_JAVA_OPTIONS')}
    code = None
    try:
        with props.open('x', encoding='ascii') as stream:
            stream.write('Connection='+connection+'\nTraceLevel=WARNING\nTraceFile=N\nToday='+payload['scenario_date']+'\n')
        props.chmod(0o600)
        with (out/'runtime.log').open('xb') as log:
            try:
                code = execute(spec['argv'], cwd=resolve('/application'), env=env, stdout=log,
                    stderr=subprocess.STDOUT, timeout=payload['timeout_seconds']).returncode
            except subprocess.TimeoutExpired: code = 124
    finally:
        props.unlink(missing_ok=True)
    record('built-after.json', verify_live(manifest, spec, resolve))
    return {'exit_code':code, 'launch_sha256':spec['content_sha256'], 'offline_maven':False}


if __name__ == '__main__':
    print(json.dumps(run(json.load(sys.stdin))), flush=True)