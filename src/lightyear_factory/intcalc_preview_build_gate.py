"""Fixed C2 build/verifier ports. No CLI activation or credential intake.

Children are fresh execs with a clean environment, not forked controller state.
Private evidence stays local. Resource names are persisted before create; the
parent verifies removal even after a worker fault. These are unsigned integrity
records, not native-owner or production-controller proof.
"""
from dataclasses import asdict
import codecs
import hashlib
import io
import json
import math
import os
from pathlib import Path
import platform
import re
import selectors
import signal
import stat
import subprocess
import sys
import tarfile
import time
import uuid

from lightyear_factory import intcalc_preview_composition as c
from lightyear_factory.intcalc_preview_transport import persist

JRE = '3d25d5cb6ca22137a17d2aeddc7b965027ce1e404d52c5c92a8796cece4d7b07'
JRE_CONFIG = '2eac78aca4748f2a6b922f8af332d3d1a5ac161d252c2f5664806100bcf6d8cf'
JDK = '8def71d61fd7f95b08480f51e8ac35e37ec87a0aaad6950a6f1e35c771de5b2d'
JAVAC = '1c6a574beed14cd3c5a48218359fbdb2c6be775ef777cf8338f080213187c0dc'
JAR_TOOL = '1998d56064b12968a9dd4f62bf787a3e30c9fc8a46614437361e18bed45cc444'
JAR_CAP = 64 * 1024 * 1024
DIAGNOSTIC_CAP = 128 * 1024
C2_CLEANUP_RESERVE = 30
_IN_WORKER = False


class AdapterRefused(ValueError):
    pass


def require(ok, code):
    if not ok:
        raise AdapterRefused(code)


def safe_path(value, *, directory=False, owner=False):
    require(os.name == 'posix', 'posix-required')
    p = Path(value).absolute()
    require(p == p.resolve(strict=True), 'resolved-path-required')
    for part in (p, *p.parents):
        require(not stat.S_ISLNK(part.lstat().st_mode), 'linked-path')
    info = p.stat()
    require(stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode), 'file-kind')
    if owner:
        require(info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) & 0o077 == 0, 'owner-mode')
    return p


def read_file(path, cap):
    p = safe_path(path)
    fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_size <= cap, 'file-size')
        raw = bytearray()
        while len(raw) <= cap:
            part = os.read(fd, min(65536, cap + 1 - len(raw)))
            if not part:
                break
            raw.extend(part)
        after = os.fstat(fd)
        require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
                (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
                and len(raw) == before.st_size, 'file-changed')
        return bytes(raw)
    finally:
        os.close(fd)


def exclusive(path, raw, mode=0o600):
    require(type(raw) is bytes, 'record-bytes')
    parent = safe_path(Path(path).parent, directory=True)
    directory = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    fd = None
    try:
        fd = os.open(Path(path).name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     mode, dir_fd=directory)
        require(os.write(fd, raw) == len(raw), 'short-write')
        persist(fd)
        persist(directory)
    finally:
        if fd is not None:
            os.close(fd)
        os.close(directory)


def phase(window, clock=time.monotonic):
    require(type(window) is c.PhaseWindow and window.cleanup_seconds == 5, 'phase-type')
    values = (window.deadline_monotonic, window.original_deadline_monotonic, clock())
    require(all(type(v) in (float, int) and math.isfinite(v) for v in values), 'phase-clock')
    hard = min(values[0], values[1])
    require(hard - values[2] > C2_CLEANUP_RESERVE, 'phase-expired')
    return hard - C2_CLEANUP_RESERVE, hard


def capture(argv, work_end, hard_end, cap=DIAGNOSTIC_CAP):
    """POSIX, bounded nonblocking pipes and one absolute reap deadline."""
    require(os.name == 'posix' and time.monotonic() < work_end <= hard_end, 'command-deadline')
    proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, env={'PATH': '/usr/bin:/bin:/usr/sbin:/sbin'},
                            close_fds=True, start_new_session=not _IN_WORKER)
    streams = (proc.stdout, proc.stderr)
    buffers = [bytearray(), bytearray()]
    poller = selectors.DefaultSelector()
    fault = None
    try:
        for i, stream in enumerate(streams):
            os.set_blocking(stream.fileno(), False)
            poller.register(stream, selectors.EVENT_READ, i)
        while poller.get_map() or proc.poll() is None:
            now = time.monotonic()
            if now >= work_end:
                fault = AdapterRefused('command-deadline')
                break
            for key, _ in poller.select(min(0.05, work_end - now)):
                block = os.read(key.fileobj.fileno(), 65536)
                if not block:
                    poller.unregister(key.fileobj)
                    continue
                target = buffers[key.data]
                require(len(target) + len(block) <= cap, 'command-output-cap')
                target.extend(block)
        if fault:
            raise fault
        require(time.monotonic() < work_end, 'command-late')
        return {'rc': proc.returncode, 'stdout': bytes(buffers[0]), 'stderr': bytes(buffers[1])}
    finally:
        # Kill the whole fresh process group even if the leader exited while a
        # descendant still held a pipe. No fresh relative timeout is introduced.
        try:
            if _IN_WORKER:
                proc.kill()
            else:
                os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        remaining = hard_end - time.monotonic()
        if proc.poll() is None:
            require(remaining > 0, 'child-reap-deadline')
            try:
                proc.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                raise AdapterRefused('child-reap-unconfirmed') from None
        poller.close()
        for stream in streams:
            stream.close()
        if not _IN_WORKER:
            while True:
                try:
                    os.killpg(proc.pid, 0)
                except ProcessLookupError:
                    break
                require(time.monotonic() < hard_end, 'child-group-reap-unconfirmed')
                time.sleep(min(0.01, max(0, hard_end - time.monotonic())))


def jar_from_tar(raw):
    require(type(raw) is bytes and len(raw) <= JAR_CAP + 65536, 'archive-size')
    try:
        with tarfile.open(fileobj=io.BytesIO(raw), mode='r:') as archive:
            entries = list(archive)
            require(len(entries) == 1, 'archive-inventory')
            item = entries[0]
            require(item.name == 'candidate.jar' and item.isfile()
                    and not item.linkname and 0 < item.size <= JAR_CAP, 'archive-member')
            stream = archive.extractfile(item)
            data = stream.read(JAR_CAP + 1)
            require(len(data) == item.size, 'archive-partial')
            return data
    except (tarfile.TarError, OSError, EOFError):
        raise AdapterRefused('archive-invalid') from None


def resource_name(kind, name):
    return kind in ('container', 'volume') and type(name) is str and re.fullmatch(
        r'(?:intcalc-c1-[0-9a-f]{32}(?:-collect|-out)?|c2-build-[0-9a-f]{32}(?:-collect|-out)?)', name) is not None


class Registry:
    def __init__(self, root):
        self.root = safe_path(root, directory=True, owner=True)

    def register(self, kind, name):
        if kind.startswith('removed-'):
            return self.removed(kind.removeprefix('removed-'), name)
        require(resource_name(kind, name), 'resource-name')
        exclusive(self.root / (kind + '-' + name + '.json'), c.canonical({'kind': kind, 'name': name}))

    def removed(self, kind, name):
        require(resource_name(kind, name), 'resource-name')
        exclusive(self.root / ('removed-' + kind + '-' + name + '.json'), c.canonical({'kind': kind, 'name': name}))

    def entries(self):
        paths = list(self.root.iterdir())
        require(len(paths) <= 200, 'resource-count')
        rows = []
        for p in paths:
            row = c.strict_json(read_file(p, 1024))
            require(set(row) == {'kind', 'name'} and resource_name(row['kind'], row['name']), 'resource-record')
            base = row['kind'] + '-' + row['name'] + '.json'
            require(p.name in (base, 'removed-' + base), 'resource-record-name')
            if p.name == 'removed-' + base:
                require(read_file(self.root / base, 1024) == read_file(p, 1024), 'resource-removal-join')
            if p.name == base and not (self.root / ('removed-' + base)).exists():
                rows.append(row)
        return sorted(rows, key=lambda r: r['kind'] == 'volume')


def cleanup(prefix, registry, hard_end):
    rows = []
    for row in registry.entries():
        kind, name = row['kind'], row['name']
        command = ['rm', '--force', '--volumes', name] if kind == 'container' else ['volume', 'rm', '--force', name]
        result = capture([*prefix, *command], hard_end - 0.05, hard_end)
        marker = b'no such container' if kind == 'container' else b'no such volume'
        require(result['rc'] == 0 or result['rc'] == 1 and marker in result['stderr'].lower(), 'resource-remove')
        result = capture([*prefix, kind, 'inspect', name], hard_end - 0.05, hard_end)
        require(result['rc'] == 1 and marker in result['stderr'].lower(), 'resource-absence-unconfirmed')
        registry.removed(kind, name)
        rows.append({**row, 'absence_confirmed': True})
    require(time.monotonic() < hard_end, 'cleanup-deadline')
    return rows


def pins(packet):
    c.validate_packet(packet)
    expected = {'runtime_manifest_sha256': JRE, 'runtime_config_sha256': JRE_CONFIG,
                'toolchain_manifest_sha256': JDK, 'javac_sha256': JAVAC, 'jar_sha256': JAR_TOOL,
                'runtime_platform': 'linux/arm64', 'byte_policy_sha256': 'STRICT'}
    require(all(packet[k] == v for k, v in expected.items()), 'exact-pins')
    return expected


class BuildGateAdapter:
    def __init__(self, packet, *, parent, session_id, docker_binary, endpoint,
                 verifier_binding, verifier_binding_sha256, gate_source_sha256):
        require(os.name == 'posix' and sys.platform == 'darwin' and platform.machine() == 'arm64',
                'native-controller-required')
        self.packet = c.strict_json(c.canonical(packet))
        pins(self.packet)
        require(c.is_hash(session_id) and c.is_hash(verifier_binding_sha256)
                and c.is_hash(gate_source_sha256), 'binding-hashes')
        parent = safe_path(parent, directory=True, owner=True)
        self.root = parent / ('build-gate-' + session_id)
        self.root.mkdir(mode=0o700)
        self.config = self.root / 'docker-config'
        self.config.mkdir(mode=0o700)
        binary = safe_path(docker_binary)
        require(os.access(binary, os.X_OK), 'docker-executable')
        require(type(endpoint) is str and endpoint.startswith('unix:///') and not any(ch.isspace() for ch in endpoint), 'local-endpoint')
        # Socket path itself may be a documented Docker-managed symlink; its
        # exact endpoint is authenticated in the attended inspection evidence.
        self.prefix = [str(binary), '--config', str(self.config), '--host', endpoint]
        self.binding = str(safe_path(verifier_binding, owner=True))
        self.binding_hash, self.gate_hash = verifier_binding_sha256, gate_source_sha256
        self.pid, self.next_build, self.next_gate = os.getpid(), 1, 1
        self.built = {}

    def _request(self, operation, attempt, window, source=None):
        require(os.getpid() == self.pid, 'process-changed')
        work_end, hard_end = phase(window)
        root = self.root / (operation + '-' + str(attempt))
        root.mkdir(mode=0o700)
        registry_root = root / 'resources'
        registry_root.mkdir(mode=0o700)
        request = {'operation': operation, 'attempt': attempt, 'packet': self.packet,
                   'root': str(root), 'registry': str(registry_root), 'prefix': self.prefix,
                   'work_end': work_end, 'hard_end': hard_end, 'verifier_binding': self.binding,
                   'verifier_binding_sha256': self.binding_hash, 'gate_source_sha256': self.gate_hash}
        if operation == 'build':
            raw = source.encode('utf-8', errors='strict')
            require(0 < len(raw) <= 65536 and not any(ord(ch) < 32 and ch not in '\t\r\n' for ch in source), 'source-contract')
            exclusive(root / 'Main.java', raw, 0o444)
            request['source_sha256'] = c.digest(raw)
        else:
            request['artifact'] = str(self.root / ('build-' + str(attempt)) / 'candidate.jar')
            request['artifact_sha256'] = self.built[attempt].artifact_sha256
        # The private request has monotonic floats; it is not a public authority
        # record and is parsed only by the fixed child, never supplied by a model.
        request_raw = json.dumps(request, sort_keys=True, allow_nan=False).encode('utf-8')
        request_path = root / 'worker-request.json'
        exclusive(request_path, request_raw)
        worker = Path(__file__).with_name('intcalc_preview_build_gate_worker.py')
        outcome = None
        try:
            outcome = capture([sys.executable, '-I', '-B', str(worker), str(request_path),
                               c.digest(request_raw)], hard_end - 12, hard_end - 10, 16384)
            require(outcome['rc'] == 0, 'worker-failed')
        finally:
            reaped = cleanup(self.prefix, Registry(registry_root), hard_end)
            exclusive(root / 'parent-cleanup.json', c.canonical({'resources': reaped, 'cleanup_confirmed': True}))
        value = c.strict_json(outcome['stdout'])
        require(type(value) is dict and value.get('completed') is True and value.get('cleanup_confirmed') is True, 'worker-result')
        require(time.monotonic() < hard_end, 'late-result')
        return value

    def build(self, attempt, source, window):
        require(type(attempt) is int and attempt == self.next_build <= 2 and self.next_gate == attempt, 'build-order')
        self.next_build += 1  # consumed even if validation/launch fails
        try:
            value = self._request('build', attempt, window, source)
            result = c.BuildResult(**value)
            require(result.source_sha256 == c.digest(source.encode('utf-8')), 'source-join')
            self.built[attempt] = result
            if result.compile_failed:
                self.next_gate += 1  # no verifier attempt exists for an unbuilt source
            return result
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            raise AdapterRefused('build-failed-no-retry') from None

    def gate(self, attempt, built, window):
        require(type(attempt) is int and attempt == self.next_gate <= 2
                and self.built.get(attempt) == built and type(built) is c.BuildResult
                and built.compile_failed is False, 'gate-order')
        self.next_gate += 1
        try:
            value = self._request('gate', attempt, window)
            value['verdicts'] = tuple(value['verdicts'])
            result = c.GateResult(**value)
            c.feedback(result.verdicts)
            require(not set(result.verdicts) & c.UNSAFE, 'unsafe-verdict')
            return result
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            raise AdapterRefused('gate-failed-no-retry') from None


def worker_build(request, registry):
    root, prefix = Path(request['root']), request['prefix']
    end, hard = request['work_end'], request['hard_end'] - 12
    private = []
    require(c.digest(read_file(root / 'Main.java', 65536)) == request['source_sha256'], 'source-drift')
    def command(args, cap=DIAGNOSTIC_CAP):
        result = capture([*prefix, *args], end, hard, cap)
        private.append({'argv': args, 'rc': result['rc'], 'stdout_sha256': c.digest(result['stdout']),
                        'stderr_sha256': c.digest(result['stderr'])})
        require(result['rc'] == 0, 'docker-operation')
        return result['stdout']
    from lightyear_mainframe import intcalc_candidate_gate as gate
    require(gate.daemon_runtime_platform(command(['info', '--format', '{"os":{{json .OSType}},"architecture":{{json .Architecture}}}'])) == 'linux/arm64', 'daemon-platform')
    token = uuid.uuid4().hex
    name, collector, volume = ('c2-build-' + token + suffix for suffix in ('', '-collect', '-out'))
    image = 'docker.io/library/eclipse-temurin@sha256:' + JDK
    # Inspect only; never pull. Config.Id semantics are not used here.
    info = c.strict_json(command(['image', 'inspect', image]))
    require(len(info) == 1 and info[0]['Os'] == 'linux' and info[0]['Architecture'] == 'arm64'
            and any(x in ('eclipse-temurin@sha256:' + JDK, 'docker.io/library/eclipse-temurin@sha256:' + JDK)
                    for x in info[0]['RepoDigests']), 'jdk-image-platform-digest')
    registry.register('volume', volume)
    command(['volume', 'create', '--driver=local', '--opt=type=tmpfs', '--opt=device=tmpfs',
             '--opt=o=size=64m,uid=65534,gid=65534,mode=0700', volume])
    common = ['--pull=never', '--platform=linux/arm64', '--network=none', '--read-only',
              '--cap-drop=ALL', '--security-opt=no-new-privileges', '--pids-limit=64',
              '--memory=512m', '--cpus=1', '--user=65534:65534']
    registry.register('container', name)
    command(['create', '--name', name, *common, '--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=32m,mode=1777',
             '--mount', f'type=bind,src={root / "Main.java"},dst=/source/Main.java,readonly',
             '--mount', f'type=volume,source={volume},target=/build,volume-nocopy',
             '--entrypoint=/bin/sh', image, '-c', 'while :; do sleep 1; done'])
    command(['start', name])
    state = c.strict_json(command(['inspect', name]))[0]
    boundary(state, image, {'/source/Main.java': False, '/build': True})
    tools = command(['exec', name, '/usr/bin/env', '-i', '/usr/bin/sha256sum',
                     '/opt/java/openjdk/bin/javac', '/opt/java/openjdk/bin/jar']).decode('ascii').splitlines()
    require(tools == [JAVAC + '  /opt/java/openjdk/bin/javac', JAR_TOOL + '  /opt/java/openjdk/bin/jar'], 'toolchain-hashes')
    command(['exec', name, '/usr/bin/env', '-i', '/bin/mkdir', '/build/classes'])
    # Docker exec must succeed separately from javac. The fixed trusted wrapper
    # records javac's exit and separates both output streams into the private
    # bounded volume. No candidate-controlled shell text or command is interpolated.
    marker = command(['exec', name, '/usr/bin/env', '-i', 'LANG=C.UTF-8', 'TZ=UTC', '/bin/sh', '-c',
        '/opt/java/openjdk/bin/javac -proc:none --release 21 -encoding UTF-8 -d /build/classes /source/Main.java >/build/javac.stdout 2>/build/javac.stderr; '
        'rc=$?; printf "%s\\n" "$rc" >/build/javac.exit || exit 125; printf "C2_JAVAC_EXIT=%s\\n" "$rc"; exit 0'])
    matched = re.fullmatch(rb'C2_JAVAC_EXIT=([0-9]{1,3})\n', marker)
    require(matched is not None, 'compiler-exit-marker')
    compiler_exit = int(matched.group(1))
    # OpenJDK javac Main.Result: only ERROR(1) is completed source failure.
    # CMDERR(2), SYSERR(3), ABNORMAL(4), signals and unknown codes are faults.
    require(compiler_exit in (0, 1), 'compiler-terminal-fault')
    if compiler_exit == 0:
        command(['exec', name, '/usr/bin/env', '-i', 'LANG=C', 'TZ=UTC', '/opt/java/openjdk/bin/jar',
                 '--create', '--file', '/build/candidate.jar', '--main-class', 'Main', '-C', '/build/classes', '.'])
    command(['pause', name])
    require(c.strict_json(command(['inspect', name]))[0]['State']['Paused'] is True, 'builder-not-paused')
    registry.register('container', collector)
    command(['create', '--name', collector, *common, '--mount', f'type=volume,source={volume},target=/capture,readonly,volume-nocopy',
             '--entrypoint=/bin/sh', image, '-c', 'while :; do sleep 1; done'])
    command(['start', collector])
    boundary(c.strict_json(command(['inspect', collector]))[0], image, {'/capture': False})
    exit_readback = command(['exec', collector, '/usr/bin/head', '-c', '16', '/capture/javac.exit'], 16)
    require(exit_readback == str(compiler_exit).encode('ascii') + b'\n', 'compiler-exit-readback')
    compiler_stderr, truncated = '', False
    artifact = None
    if compiler_exit:
        compiler_stderr, truncated = compile_diagnostic(command(
            ['exec', collector, '/usr/bin/head', '-c', '4097', '/capture/javac.stderr'], 4097))
    else:
        artifact = jar_from_tar(command(['exec', collector, '/bin/tar', '-C', '/capture', '-cf', '-', 'candidate.jar'], JAR_CAP + 65536))
        exclusive(root / 'candidate.jar', artifact)
    artifact_hash = c.digest(artifact) if artifact is not None else None
    receipt = {'source_sha256': request['source_sha256'], 'artifact_sha256': artifact_hash,
               'compiler_exit_code': compiler_exit, 'compile_failed': compiler_exit == 1,
               'projected_stderr_sha256': c.digest(compiler_stderr.encode('utf-8')) if compiler_exit else None,
               'stderr_truncated': truncated,
               'operations': private, 'runtime_platform': 'linux/arm64', 'runtime_manifest_sha256': JRE,
               'runtime_config_sha256': JRE_CONFIG, 'toolchain_manifest_sha256': JDK,
               'javac_sha256': JAVAC, 'jar_sha256': JAR_TOOL,
               'packet_sha256': c.digest(c.canonical(request['packet'])), 'qualified': False,
               'production_controller_receipt': False}
    raw = c.canonical(receipt)
    exclusive(root / 'build-receipt.json', raw)
    return asdict(c.BuildResult(request['source_sha256'], artifact_hash, 'linux/arm64', JRE,
                               JRE_CONFIG, JDK, JAVAC, JAR_TOOL, c.digest(raw), True, True,
                               compiler_exit == 1, compiler_exit if compiler_exit else None,
                               compiler_stderr, truncated))


def compile_diagnostic(raw):
    require(type(raw) is bytes and len(raw) <= 4097, 'compiler-diagnostic-capture')
    # Decode the first 4096 bytes; an incomplete final UTF-8 sequence is omitted,
    # while malformed bytes within the retained prefix refuse the whole result.
    decoder = codecs.getincrementaldecoder('utf-8')(errors='strict')
    text = decoder.decode(raw[:4096], final=len(raw) <= 4096)
    # No generic slash/path heuristic: javac quotes Java string/char literals,
    # comments and markup. Its only host-file mount is /source/Main.java;
    # host prefix/argv/stderr never enter this collector stream.
    # Normalize unexpected C0s into printable escapes so valid UTF-8 javac
    # diagnostics never fail solely because source excerpts contain punctuation.
    text = ''.join('\\u%04x' % ord(ch) if ord(ch) < 32 and ch not in '\t\r\n' else ch for ch in text)
    encoded = text.encode('utf-8')
    truncated = len(raw) > 4096 or len(encoded) > 4096
    if len(encoded) > 4096:
        text = codecs.getincrementaldecoder('utf-8')(errors='strict').decode(encoded[:4096], final=False)
    c.validate_compile_feedback({'schema': c.COMPILE_SCHEMA, 'kind': 'compilation-failed',
                                'javac_stderr': text, 'stderr_truncated': truncated})
    return text, truncated


def boundary(state, image, mounts):
    config, host = state['Config'], state['HostConfig']
    observed = {m['Destination']: m for m in state['Mounts'] if m['Type'] != 'tmpfs'}
    require(config['Image'] == image and config['User'] == '65534:65534'
            and host['NetworkMode'] == 'none' and host['ReadonlyRootfs'] is True
            and host['PidsLimit'] == 64 and host['Memory'] == 512 * 1024 * 1024
            and host['NanoCpus'] == 1_000_000_000 and 'ALL' in host['CapDrop']
            and any(x.split(':')[0] == 'no-new-privileges' for x in host['SecurityOpt'])
            and set(observed) == set(mounts)
            and all(observed[k]['RW'] is v for k, v in mounts.items()), 'container-boundary')


def worker_gate(request, registry):
    from lightyear_mainframe import intcalc_candidate_gate as gate
    require(c.digest(read_file(gate.__file__, 128 * 1024)) == request['gate_source_sha256'], 'gate-source')
    packet = request['packet']
    template_path = safe_path(request['verifier_binding'], owner=True)
    raw = read_file(template_path, 128 * 1024)
    require(c.digest(raw) == request['verifier_binding_sha256'], 'verifier-binding')
    binding = c.strict_json(raw)
    require('byte_policy' not in binding and binding['case_manifest']['sha256'] == packet['case_manifest_sha256'], 'strict-case-binding')
    artifact = read_file(request['artifact'], JAR_CAP)
    require(c.digest(artifact) == request['artifact_sha256'], 'artifact-drift')
    token = uuid.uuid4().hex
    artifact_name = 'c2-' + token + '.jar'
    exclusive(template_path.parent / artifact_name, artifact)
    binding.update(artifact={'path': artifact_name, 'sha256': c.digest(artifact)}, runtime_platform='linux/arm64',
                   runtime_image='docker.io/library/eclipse-temurin@sha256:' + JRE, max_elapsed_seconds=600)
    path = template_path.parent / ('c2-' + token + '-binding.json')
    bound = c.canonical(binding)
    exclusive(path, bound)
    retained = Path(request['root']) / 'private-gate'
    report = gate.run(path, c.digest(bound), retained, absolute_deadline=request['hard_end'] - 12,
                      docker_prefix=request['prefix'], resource_register=registry.register,
                      cleanup_seconds=18)
    rows = report['cases']
    require(len(rows) == 10 and len({r['id'] for r in rows}) == 10
            and {r['id'] for r in rows} == gate.REQUIRED, 'complete-gate-inventory')
    verdicts = tuple(r['verdict'] for r in rows)
    c.feedback(verdicts)
    require(not set(verdicts) & c.UNSAFE, 'unsafe-gate-result')
    for row in rows:
        runtime = json.loads(read_file(retained / row['id'] / 'runtime.json', 2 * 1024 * 1024).decode('utf-8'))
        require(runtime['cleanup_confirmed'] is True, 'gate-cleanup')
    result_raw = read_file(retained / 'result.json', 4 * 1024 * 1024)
    return asdict(c.GateResult(c.digest(artifact), packet['gate_manifest_sha256'], packet['case_manifest_sha256'],
                              JRE, 'linux/arm64', 'STRICT', verdicts, c.digest(result_raw), True, True))


def worker_main(argv):
    """Private fixed child entry. Receives no secret or generated command."""
    global _IN_WORKER
    _IN_WORKER = True
    require(os.name == 'posix' and len(argv) == 2, 'worker-arguments')
    raw = read_file(argv[0], 32768)
    require(c.digest(raw) == argv[1], 'worker-request-hash')
    request = json.loads(raw.decode('utf-8'))
    pins(request['packet'])
    require(request['operation'] in ('build', 'gate') and request['attempt'] in (1, 2), 'worker-operation')
    registry = Registry(request['registry'])
    result = None
    try:
        result = worker_build(request, registry) if request['operation'] == 'build' else worker_gate(request, registry)
    finally:
        rows = cleanup(request['prefix'], registry, request['hard_end'] - 12)
        exclusive(Path(request['root']) / 'worker-cleanup.json', c.canonical({'resources': rows, 'cleanup_confirmed': True}))
    require(time.monotonic() < request['hard_end'] - 12, 'worker-late')
    return result
