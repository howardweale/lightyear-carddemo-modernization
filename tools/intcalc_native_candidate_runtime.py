"""Trusted native Intel runtime for H3. No CLI, reference, decryptor or build port.

Private results are memory-only return values for the separate verifier. A
reviewed runtime binding and a separately admitted H1 host are caller inputs.
"""
from dataclasses import dataclass
from io import BytesIO
from contextlib import contextmanager
import os
import stat
import tempfile
from pathlib import Path
import re
import time
import uuid
from zipfile import BadZipFile, ZipFile

from lightyear_factory import public_repair_answer_key as key
from lightyear_factory import public_repair_controller as c
from lightyear_factory import public_repair_staged as s1
from lightyear_factory import public_repair_worker as p5
from lightyear_factory.public_evaluator_adapter import case_deadlines
from tools import intcalc_private_reference_host as h1


class Refused(ValueError):
    pass


def require(check, code):
    if not check:
        raise Refused(code)


REPOSITORY = 'docker.io/library/eclipse-temurin'
JAVA = '/opt/java/openjdk/bin/java'
PLATFORM = 'linux/amd64'
KEY_HASH = 'fb51317ab1f5bba9677e543133364b34e893babcac279519b6f743d9568f3b37'
ISOLATION = ('--pull=never', '--platform=linux/amd64', '--runtime=runc', '--network=none',
             '--read-only', '--cap-drop=ALL', '--security-opt=no-new-privileges',
             '--pids-limit=64', '--memory=512m', '--cpus=1', '--user=65534:65534',
             '--ipc=private', '--cgroupns=private', '--log-driver=none', '--no-healthcheck')
FIXED_ENV = {'JAVA_HOME', 'JAVA_VERSION', 'LANG', 'LANGUAGE', 'LC_ALL', 'PATH'}
LIMITS = ('Qualified Intel host and pinned JRE only.',
          'Windows administrators including Howard are trusted.',
          'Operator review is not independent attestation. Preview, NOT-P5.')


@dataclass(frozen=True)
class Image:
    manifest: str
    config: str
    java: str
    version: str
    cli: str
    host_profile: str
    environment: tuple
    digest: str

    @property
    def ref(self):
        return f'{REPOSITORY}@sha256:{self.manifest}'


def reviewed_image(raw, approved_sha256, manifest, config, licence_inventory):
    require(c.hash_ok(approved_sha256) and c.sha(raw) == approved_sha256, 'runtime-binding')
    row = s1.strict(raw)
    hashes = ('manifest', 'config', 'java', 'java_version_stderr', 'docker_cli',
              'licence_inventory', 'host_profile')
    names = {k + '_sha256' for k in hashes}
    require(type(row) is dict and set(row) == names | {'schema', 'platform', 'repository'}
            and row['schema'] == 'native-candidate-binding/1'
            and (row['platform'], row['repository']) == (PLATFORM, REPOSITORY)
            and all(c.hash_ok(row[k]) for k in names), 'runtime-binding')
    require(0 < len(manifest) <= 1048576 and 0 < len(config) <= 1048576
            and 0 < len(licence_inventory) <= 4194304
            and c.sha(manifest) == row['manifest_sha256'] and c.sha(config) == row['config_sha256']
            and c.sha(licence_inventory) == row['licence_inventory_sha256'], 'runtime-image')
    description, settings = s1.strict(manifest), s1.strict(config)
    require(description.get('schemaVersion') == 2 and 'manifests' not in description
            and description.get('mediaType') in ('application/vnd.oci.image.manifest.v1+json',
                'application/vnd.docker.distribution.manifest.v2+json')
            and description['config']['digest'] == 'sha256:' + row['config_sha256']
            and description['config']['size'] == len(config)
            and (settings.get('os'), settings.get('architecture')) == ('linux', 'amd64'),
            'runtime-image')
    env = settings['config'].get('Env', [])
    require(type(env) is list and all(type(v) is str and '=' in v for v in env), 'runtime-environment')
    keys = [v.split('=', 1)[0] for v in env]
    require(len(set(keys)) == len(env) and set(keys) <= FIXED_ENV
            and any(re.fullmatch(r'JAVA_VERSION=jdk-21[.+0-9A-Za-z_-]*', v) for v in env)
            and not settings['config'].get('Volumes'), 'runtime-environment')
    return Image(row['manifest_sha256'], row['config_sha256'], row['java_sha256'],
                 row['java_version_stderr_sha256'], row['docker_cli_sha256'],
                 row['host_profile_sha256'], tuple(env), approved_sha256)


def classpath(raw):
    """Inspect only P5 jar entries, bounded before decompression; never load a class."""
    require(type(raw) is bytes and 0 < len(raw) <= s1.JAR_BYTES, 'runtime-jar')
    try:
        with ZipFile(BytesIO(raw)) as jar:
            entries = jar.infolist()
            names = [item.filename for item in entries]
            require(0 < len(names) <= 4096 and len(set(names)) == len(names)
                    and {'META-INF/MANIFEST.MF', 'Main.class'} <= set(names)
                    and sum(item.file_size for item in entries) <= 32 * 1024 * 1024,
                    'runtime-classpath')
            for item in entries:
                name = item.filename
                require(item.orig_filename == name and name.isascii() and '\\' not in name
                        and all(re.fullmatch(r'[\w.$-]+', p) and p not in ('.', '..')
                                for p in name.rstrip('/').split('/')), 'runtime-classpath')
                if item.is_dir():
                    require(item.file_size == 0, 'runtime-classpath')
                elif name == 'META-INF/MANIFEST.MF':
                    require(item.file_size <= 1024, 'runtime-classpath')
                    lines = jar.read(item).decode('ascii').splitlines()
                    if lines and lines[-1] == '':
                        lines.pop()
                    require(len(lines) in (2, 3) and 'Main-Class: Main' in lines
                            and 'Manifest-Version: 1.0' in lines
                            and all(v in ('Manifest-Version: 1.0', 'Main-Class: Main')
                                    or re.fullmatch(r'Created-By: [ -~]{1,128}', v) for v in lines)
                            and len(set(lines)) == len(lines), 'runtime-classpath')
                else:
                    require(name.endswith('.class') and not name.startswith('META-INF/'),
                            'runtime-classpath')
                    with jar.open(item) as stream:
                        header = stream.read(8)
                    require(len(header) == 8 and header[:4] == b'\xca\xfe\xba\xbe'
                            and header[4:6] != b'\xff\xff'
                            and 45 <= int.from_bytes(header[6:], 'big') <= 65, 'runtime-class-version')
    except (BadZipFile, UnicodeError, NotImplementedError, RuntimeError, OSError):
        raise Refused('runtime-jar') from None


def selected_jar(raw, descriptor, selected, binding, closure):
    expected = s1.validate_descriptor(descriptor, selected, binding, closure)
    require(len(raw) == expected['jar_bytes'] and c.sha(raw) == expected['jar_sha256'],
            'runtime-selected-jar')
    classpath(raw)
    return expected['jar_sha256']


def boundary(state, image, mounts, entry, args):
    # Inspect before start, including image defaults and all live mount destinations.
    p5.boundary(state, image.ref, mounts)
    config, host = state['Config'], state['HostConfig']
    actual_mounts = state['Mounts']
    require(len(actual_mounts) == len({m['Destination'] for m in actual_mounts})
            and all(m['Destination'] in mounts and m['Type'] in ('bind', 'volume')
                    for m in actual_mounts), 'runtime-mounts')
    require(state['Image'] == 'sha256:' + image.config
            and config['Entrypoint'] == [entry] and config['Cmd'] == args
            and tuple(config.get('Env', ())) == image.environment
            and config.get('Healthcheck', {}).get('Test') == ['NONE']
            and not config.get('Tty') and not config.get('OpenStdin')
            and host.get('IpcMode') == 'private' and host.get('CgroupnsMode') == 'private'
            and host.get('Runtime') == 'runc' and not host.get('PidMode')
            and not host.get('UTSMode') and not host.get('CapAdd') and not host.get('DeviceRequests')
            and not host.get('Devices') and not host.get('VolumesFrom')
            and not host.get('Tmpfs') and not host.get('PortBindings')
            and host.get('SecurityOpt') in (['no-new-privileges'], ['no-new-privileges:true']),
            'runtime-boundary')


class NativeDocker(p5.Docker):
    """The inherited collector, removal and bounded command functions also serve P5."""
    def __init__(self, prefix, resources, execution, cleanup, image):
        super().__init__(prefix, resources, execution, cleanup)
        self.image = image

    def preflight_image(self):
        rows = s1.strict(self.ok(['image', 'inspect', self.image.ref]))
        require(type(rows) is list and len(rows) == 1, 'runtime-image')
        row = rows[0]
        require((row['Os'], row['Architecture']) == ('linux', 'amd64')
                and row['Id'] == 'sha256:' + self.image.config
                and any(v in (self.image.ref, self.image.ref.removeprefix('docker.io/library/'))
                        for v in row['RepoDigests']), 'runtime-image')

    def volume(self, name, size):
        require(size == '16m', 'runtime-volume')
        super().volume(name, size)
        rows = s1.strict(self.ok(['volume', 'inspect', name]))
        require(len(rows) == 1 and rows[0]['Name'] == name and rows[0]['Driver'] == 'local'
                and rows[0]['Scope'] == 'local' and rows[0]['Options'] == {
                    'type': 'tmpfs', 'device': 'tmpfs', 'o': 'size=16m,uid=65534,gid=65534,mode=0700'
                }, 'runtime-volume')

    def create(self, name, kind, mounts, entry, args):
        require(kind == 'jre' and entry in ('/bin/sleep', JAVA), 'runtime-command')
        self.record('container', name)
        flags = []
        for dest, (source, rw, mode) in mounts.items():
            require(mode in ('volume', 'bind') and not any(k in source for k in ',\n\r"'),
                    'runtime-mounts')
            flags += ['--mount', f'type={mode},source={source},target={dest}' +
                      (',volume-nocopy' if mode == 'volume' else '') + ('' if rw else ',readonly')]
        self.ok(['create', '--name', name, *ISOLATION, *flags,
                 '--entrypoint=' + entry, self.image.ref, *args])
        boundary(self.inspect(name), self.image, mounts, entry, args)

    def verify_jre(self, collector):
        raw = self.ok(['exec', collector, '/usr/bin/sha256sum', JAVA], 512)
        require(raw == (self.image.java + '  ' + JAVA + '\n').encode(), 'runtime-java')
        row = self.call(['exec', collector, JAVA, '-version'], 8192)
        require(row['rc'] == 0 and row['stdout'] == b''
                and b'version "21' in row['stderr']
                and c.sha(row['stderr']) == self.image.version, 'runtime-java')

    def observe_case(self, jar, input_dir, stamp, date):
        self.preflight_image()
        candidate = 'prw-' + uuid.uuid4().hex
        volume = candidate + '-out'
        self.volume(volume, '16m')
        collector = self.collector('jre', volume, '/output')
        self.verify_jre(collector)
        mounts = {'/candidate.jar': (str(jar), False, 'bind'), '/output': (volume, True, 'volume')}
        mounts.update({'/input/' + dd + '.bin': (str(input_dir / (dd + '.bin')), False, 'bind')
                       for dd in p5.INPUTS})
        self.create(candidate, 'jre', mounts, JAVA,
                    ['-Xmx256m', '-jar', '/candidate.jar', '--input-dir', '/input',
                     '--output-dir', '/output', '--processing-date', date,
                     '--timestamp', stamp, '--codec', 'cp037'])
        running = self.call(['start', '--attach', candidate], p5.DATA, limited=True)
        self.end = self.hard - .1
        if running['timed_out'] or running['output_capped']:
            killed = self.call(['kill', candidate])
            require(killed['rc'] == 0 or b'is not running' in killed['stderr'].lower(), 'runtime-stop')
        state = self.inspect(candidate)['State']
        require(not state['Running'] and not state['Error']
                and state.get('StartedAt') not in (None, '', '0001-01-01T00:00:00Z')
                and type(state['ExitCode']) is int, 'runtime-infrastructure')
        result = {channel: running[channel] for channel in ('stdout', 'stderr', 'timed_out', 'output_capped')}
        result['exit'] = state['ExitCode']
        for dd in p5.OUTPUTS:
            path = '/output/' + dd + '.bin'
            # The collector runs after the candidate stopped; the volume is now stable.
            presence = self.call(['exec', collector, '/usr/bin/test', '-e', path])
            require(presence['rc'] in (0, 1) and presence['stdout'] == presence['stderr'] == b'',
                    'runtime-output')
            if presence['rc'] != 0:
                link = self.call(['exec', collector, '/usr/bin/test', '-L', path])
                require(link['rc'] == 1 and link['stdout'] == link['stderr'] == b'', 'runtime-output')
                result[dd] = None
            else:
                result[dd], capped = self.prefix_copy(collector, path, p5.DATA)
                result['output_capped'] |= capped
        return result


@contextmanager
def scratch(host):
    # Native WSL /dev/shm only. mkdir is exclusive, random, and mode 0700.
    area = Path('/dev/shm')
    info = area.stat()
    require(area == area.resolve(strict=True) and stat.S_ISDIR(info.st_mode)
            and info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0o1777, 'runtime-tmpfs')
    desc = h1.strict(host.commands.out(['findmnt', '--json', '--target', str(area),
                                        '--output', 'FSTYPE,SOURCE,TARGET']))
    fs = desc.get('filesystems')
    require(type(fs) is list and len(fs) == 1 and fs[0].get('target') == str(area)
            and fs[0].get('fstype') == 'tmpfs', 'runtime-tmpfs')
    with tempfile.TemporaryDirectory(dir=area, prefix='private-case-') as temporary:
        root = Path(temporary)
        require(stat.S_IMODE(root.stat().st_mode) == 0o700 and root.stat().st_uid == os.getuid(),
                'runtime-tmpfs')
        yield root
    require(not root.exists(), 'runtime-tmpfs-cleanup')


class _Runtime:
    """One unchanged jar. H3 supplies admitted custody, stage-1 and consumed-once authority.

    There is deliberately no staged hidden operation in this module. Its parent
    must own the OS process boundary and reconcile resource journals after child death.
    """
    def __init__(self, host, image, jar):
        h1.profile(host.p)
        require(h1.sha(h1.canonical(host.p)) == image.host_profile
                and host.p['binaries']['docker']['sha256'] == image.cli, 'runtime-host')
        h1.source_identity(host.commands, host.p)
        host.observe()
        classpath(jar)
        self.root = h1.private_directory(host.p['private_root']) / ('native-' + uuid.uuid4().hex)
        self.root.mkdir(mode=0o700)
        self.jar = self.root / s1.LEAF
        p5.exclusive(self.jar, jar, 0o444)
        self.jar_sha = c.sha(jar)
        self.prefix = [host.p['binaries']['docker']['path'], '--config', host.p['client_config'],
                       '--host', 'unix:///var/run/docker.sock']
        self.image = image
        self.host = host
        self.failed = False

    def _docker(self, root, end, hard):
        require(c.sha(p5.read(self.prefix[0], 268435456)) == self.image.cli, 'runtime-cli')
        return NativeDocker(self.prefix, root / 'resources', end, hard, self.image)

    def run_case(self, inputs, stamp, date, phase_end):
        require(not self.failed, 'runtime-closed')
        self.failed = True
        require(type(inputs) is dict and set(inputs) == set(p5.INPUTS)
                and all(type(v) is bytes and len(v) <= p5.DATA for v in inputs.values())
                and type(stamp) is str and re.fullmatch(r'\d{4}-\d\d-\d\d-\d\d\.\d\d\.\d\d\.\d{6}', stamp)
                and type(date) is str and re.fullmatch(r'\d{10}', date), 'runtime-input')
        root = self.root / ('case-' + uuid.uuid4().hex)
        root.mkdir(mode=0o700)
        (root / 'resources').mkdir(mode=0o700)
        with scratch(self.host) as folder:
            result = self._case(inputs, root, folder, stamp, date, phase_end)
        self.failed = False
        return result

    def _case(self, inputs, root, folder, stamp, date, phase_end):
        for dd in p5.INPUTS:
            p5.exclusive(folder / (dd + '.bin'), inputs[dd], 0o444)
        require(c.sha(p5.read(self.jar, s1.JAR_BYTES)) == self.jar_sha, 'runtime-selected-jar')
        end, hard = case_deadlines(time.monotonic(), phase_end)
        # Split the five-second reserve between collection and independent removal.
        removal_reserve = min(2.5, (hard - end) / 2)
        docker = self._docker(root, end, hard - removal_reserve)
        try:
            result = docker.observe_case(self.jar, folder, stamp, date)
        finally:
            removals = self._docker(root, hard - .05, hard).cleanup()
        require(sorted(row['kind'] for row in removals) == ['container', 'container', 'volume']
                and all(row['absence_confirmed'] is True for row in removals), 'runtime-cleanup')
        require(time.monotonic() < hard, 'runtime-deadline')
        return result


FIXTURES = ('matches_all', 'imperfect', 'timeout', 'output_cap', 'boundary')


def fixture_catalog(raw, expected_sha, jars):
    require(c.hash_ok(expected_sha) and c.sha(raw) == expected_sha, 'runtime-fixtures')
    catalog = s1.strict(raw)
    require(set(catalog) == {'schema', 'fixtures', 'arm64_observations_sha256', 'answer_key_sha256'}
            and catalog['schema'] == 'native-public-fixture-catalog/1'
            and catalog['answer_key_sha256'] == KEY_HASH and set(jars) == set(FIXTURES)
            and set(catalog['fixtures']) == set(FIXTURES)
            and c.hash_ok(catalog['arm64_observations_sha256']), 'runtime-fixtures')
    identities = []
    for label in FIXTURES:
        row = catalog['fixtures'][label]
        require(set(row) == {'jar_sha256', 'arm64_build_receipt_sha256'}
                and c.hash_ok(row['arm64_build_receipt_sha256'])
                and c.hash_ok(row['jar_sha256']) and c.sha(jars[label]) == row['jar_sha256'],
                'runtime-fixtures')
        classpath(jars[label])
        identities.append(row['jar_sha256'])
    require(len(set(identities)) == len(FIXTURES), 'runtime-fixtures')
    return catalog


def compared(observed, compare_files):
    require(type(compare_files) is bool and type(observed['exit']) is int
            and all(type(observed[k]) is bool for k in ('timed_out', 'output_capped')), 'runtime-observation')
    fields = ['stdout', 'stderr'] + (list(p5.OUTPUTS) if compare_files else [])
    row = {k: observed[k] for k in ('exit', 'timed_out', 'output_capped')}
    for k in fields:
        value = observed[k]
        require(type(value) is bytes or value is None and k in p5.OUTPUTS, 'runtime-observation')
        row[k] = None if value is None else c.sha(value)
    return row


def public_check(host, image, jars, catalog_raw, catalog_sha, parity_raw, answer_root, suite_root, review):
    """Run only on Howard's admitted host under separate public qualification approval."""
    require(review.manifest_sha256 == KEY_HASH, 'runtime-public-key')
    catalog = fixture_catalog(catalog_raw, catalog_sha, jars)
    require(c.sha(parity_raw) == catalog['arm64_observations_sha256'], 'runtime-parity')
    parity = s1.strict(parity_raw)
    require(set(parity) == {'schema', 'jar_sha256', 'cases'} and parity['schema'] == 'arm64-public-parity/1'
            and parity['jar_sha256'] == c.sha(jars['imperfect'])
            and set(parity['cases']) == set(key.CASE_IDS), 'runtime-parity')
    cases, source = key.load(answer_root, suite_root, review)
    require(len(cases) == 16 and source['manifest_sha256'] == KEY_HASH, 'runtime-public-key')
    changed = 0
    for label in FIXTURES:
        runtime = _Runtime(host, image, jars[label])
        deadline = time.monotonic() + 600
        for case_id, case in zip(key.CASE_IDS, cases if label in ('matches_all', 'imperfect') else cases[:1]):
            observed = runtime.run_case(case['inputs'], case['timestamp'], case['processing_date'], deadline)
            if label == 'timeout':
                require(observed['timed_out'] and not observed['output_capped'], 'runtime-timeout-probe')
            elif label == 'output_cap':
                require(observed['output_capped'] and not observed['timed_out'], 'runtime-cap-probe')
            elif label == 'boundary':
                require(not observed['timed_out'] and not observed['output_capped'] and observed['exit'] == 0
                        and observed['stdout'] == b'boundary-probe-passed\n' and observed['stderr'] == b'',
                        'runtime-boundary-probe')
            else:
                require(not observed['timed_out'] and not observed['output_capped'], 'runtime-public-difference')
                fields = case['compare_output_files']
                actual = compared(observed, fields)
                expected = compared(dict(case['expected'], timed_out=False, output_capped=False), fields)
                if label == 'matches_all':
                    require(actual == expected, 'runtime-public-difference')
                else:
                    require(actual == parity['cases'][case_id], 'runtime-parity')
                    changed += int(actual != expected)
    require(changed > 0, 'runtime-parity')
    host.observe()
    return dict(schema='native-candidate-public-check/1', fixtures_sha256=catalog_sha,
                arm64_observations_sha256=c.sha(parity_raw), host_profile_sha256=image.host_profile,
                runtime_binding_sha256=image.digest, answer_key_manifest_sha256=KEY_HASH,
                public_cases_matched=16, public_cases_with_parity=16,
                adversarial_probes_passed=3, private_execution_authorized=False,
                limits=list(LIMITS))


def retained_runtime(host, image, jar, result, binding, closure, qualification_raw, qualification_sha):
    """H3 supplies exact authenticated bytes and verifies exclusive claim / custody first."""
    require(c.hash_ok(qualification_sha) and c.sha(qualification_raw) == qualification_sha,
            'runtime-qualification')
    report = s1.strict(qualification_raw)
    report_keys = ('schema fixtures_sha256 arm64_observations_sha256 host_profile_sha256 '
                   'runtime_binding_sha256 answer_key_manifest_sha256 public_cases_matched '
                   'public_cases_with_parity adversarial_probes_passed private_execution_authorized limits')
    require(type(report) is dict and set(report) == set(report_keys.split())
            and c.hash_ok(report['fixtures_sha256']) and c.hash_ok(report['arm64_observations_sha256'])
            and report['limits'] == list(LIMITS) and report['schema'] == 'native-candidate-public-check/1' and report['runtime_binding_sha256'] == image.digest
            and report['host_profile_sha256'] == image.host_profile and report['answer_key_manifest_sha256'] == KEY_HASH
            and (report['public_cases_matched'], report['public_cases_with_parity'],
                 report['adversarial_probes_passed']) == (16, 16, 3)
            and report['private_execution_authorized'] is False, 'runtime-qualification')
    expected_closure = dict(schema='staged-model-closure/1', binding_sha256=c.digest(binding),
                            model_ports_closed=True, further_model_calls_allowed=False)
    require(closure == expected_closure
            and result['schema'] == 'staged-public-result/1' and result['mode'] == 'STAGED_PUBLIC'
            and result['status'] == 'PUBLIC_COMPLETE_HIDDEN_PENDING'
            and result['selected']['different'] == 0 and result['selected']['match'] == 16
            and result['binding_sha256'] == c.digest(binding) and result['public_answer_key_sha256'] == KEY_HASH
            and binding['public_answer_key_sha256'] == KEY_HASH
            and result['pre_run_commitment_sha256'] == binding['heldout_commitment_sha256']
            and result['closure_record_sha256'] == c.sha(c.canonical(closure) + b'\n')
            and result['hidden_execution_authorized'] is False, 'runtime-staged')
    identity = selected_jar(jar, result['retained_jar'], result['selected'], binding, result['closure_record_sha256'])
    require(result['hidden'] == dict(status='PENDING', reason='separate-human-verifier',
                                     selected_jar_sha256=identity), 'runtime-staged')
    return _Runtime(host, image, jar)
