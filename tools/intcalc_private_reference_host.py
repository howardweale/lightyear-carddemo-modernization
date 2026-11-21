"""Howard-only H-A inspection/public qualification. No private inputs or keys.

All commands are inert on import. CI must use synthetic tests only. A profile
and exact operation approval are supplied privately by Howard after review.
Human custody declarations are not independent Windows attestation.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import selectors
import signal
import stat
import subprocess
import sys
import threading
import time

from tools import intcalc_reference_execution as ref
from tools import intcalc_reference_per_run as qualification
from tools import intcalc_reference_provisional as provisional

QUALIFICATION_COMMIT = '71a18164612ce574d889a39ceb335c5643721fc6'
QUALIFICATION_TREE = '7316662cb5cc52d5361ad1954c417b37e1e18fe5'
QUALIFICATION_RECEIPT = '934457b92d24dfc330e078420b14cb529fa6478c6799347b53857e74af98784b'
PACKAGE = '8496a8c754b0a179888561be69aa06d4655d15e0c54decb891c757bb190d960d'
SUITE = '6da875e28f95409290f77363c135ef98af395fe3448c9bf3e3da28b4cad370b2'
PRE = ('accounts_distinct private_account_standard private_account_dedicated '
    'fresh_tokens_checked membership_resolution_complete codex_account_standard '
    'codex_outside_docker_users per_account_wsl2 private_distro_registration_join '
    'private_distro_absent_from_codex_registration backing_storage_acl_isolated '
    'backing_storage_local_no_sync_backup native_linux_amd64 endpoint_local_unix '
    'engine_process_socket_distro_join desktop_engine_rejected endpoint_overrides_absent '
    'private_root_native_distro_fs private_root_owner_only private_root_no_symlink_escape '
    'local_no_sync_backup_attested codex_stopped_preflight process_visibility_complete '
    'no_codex_background_or_autostart operator_attends_full_window').split()
POST = ['codex_remained_stopped', 'codex_stopped_postflight']
BINS = ('docker', 'git', 'systemctl', 'ss', 'findmnt', 'getfacl', 'sudo', 'readlink', 'sha256sum')
CODES = frozenset(('host-arguments', 'host-operator', 'host-profile', 'host-custody',
    'host-source', 'host-approval', 'host-clock', 'host-platform', 'host-native-fs',
    'host-path', 'host-permissions', 'host-cli', 'host-endpoint', 'host-workloads',
    'host-space', 'host-command', 'host-output-cap', 'host-deadline', 'host-image',
    'host-boundary', 'host-inventory', 'host-criterion', 'host-cleanup',
    'host-file', 'host-fault', 'host-public-worker', 'host-binding'))
FIRST_WRITE_LIMIT = ('FIRST_WRITE_ENCRYPTION_APPLICATION_BOUNDARY: plaintext memory may '
    'be captured by trusted host paging, hibernation or crash dumps; their exclusion '
    'and forensic erasure are not claimed.')
LIMITS = qualification.LIMITS + [FIRST_WRITE_LIMIT,
    'Windows administrators, including Howard, remain trusted; operator-reported custody.']


class Refused(ValueError):
    def __init__(self, code):
        self.code = code if code in CODES else 'host-fault'
        super().__init__(self.code)


def require(ok, code):
    if not ok:
        raise Refused(code)


def canonical(row):
    def check(value):
        if type(value) in (str, bool, int) or value is None:
            return
        require(type(value) in (list, dict), 'host-file')
        if type(value) is dict:
            require(all(type(k) is str for k in value), 'host-file')
        for child in value.values() if type(value) is dict else value:
            check(child)
    check(row)
    return json.dumps(row, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def hashed(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def strict(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'host-file')
            result[key] = value
        return result
    def invalid(_):
        raise Refused('host-file')
    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_float=invalid, parse_constant=invalid)
        canonical(value)
        return value
    except (ValueError, UnicodeError, RecursionError):
        raise Refused('host-file') from None


def read(path, cap=1048576):
    path = Path(path)
    require(not path.is_symlink() and path.is_file() and path.stat().st_size <= cap, 'host-file')
    with path.open('rb') as stream:
        raw = stream.read(cap+1)
    require(len(raw) <= cap, 'host-file')
    return raw


def closed(row, keys, code):
    require(type(row) is dict and set(row) == set(keys.split()), code)


def aware(value):
    try:
        require(type(value) is str and len(value) <= 40, 'host-clock')
        parsed = datetime.fromisoformat(value)
        require(parsed.tzinfo is not None and parsed.utcoffset() is not None, 'host-clock')
        return parsed
    except ValueError:
        raise Refused('host-clock') from None


def custody(row, operation, profile_hash, source, tree, *, post=False):
    closed(row, 'schema status observed_at_with_offset operation_id private_profile_commitment_sha256 '
        'reviewed_source_commit reviewed_source_tree raw_private_evidence_retained_by '
        'raw_private_values_included docker_users_group_state engine_kind public_host_qualification '
        'qualification_receipt_sha256 checks administrators_including_howard_trusted '
        'no_swap_required no_hibernation_required crash_dump_controls_required execution_authorized', 'host-custody')
    require(row['schema'] == 'ha-separate-account-custody-return/1' and row['status'] == 'OBSERVED'
        and row['operation_id'] == operation and row['private_profile_commitment_sha256'] == profile_hash
        and row['reviewed_source_commit'] == source and row['reviewed_source_tree'] == tree
        and row['engine_kind'] == 'PRIVATE_DISTRO_ENGINE'
        and row['docker_users_group_state'] in ('PRESENT', 'ABSENT')
        and row['raw_private_evidence_retained_by'] == 'Howard'
        and row['raw_private_values_included'] is False
        and row['administrators_including_howard_trusted'] is True
        and all(row[k] is False for k in ('no_swap_required', 'no_hibernation_required',
            'crash_dump_controls_required', 'execution_authorized')), 'host-custody')
    closed(row['checks'], ' '.join(PRE+POST), 'host-custody')
    require(all(row['checks'][k] is True for k in PRE+(POST if post else [])), 'host-custody')
    require(row['public_host_qualification'] in ('PENDING', 'PASSED')
        and (row['qualification_receipt_sha256'] is None or hashed(row['qualification_receipt_sha256'])), 'host-custody')
    aware(row['observed_at_with_offset'])


def profile(row):
    closed(row, 'schema source_commit source_tree private_root client_config binaries dockerd_sha256', 'host-profile')
    require(row['schema'] == 'ha-private-host-profile/1'
        and all(type(row[k]) is str and re.fullmatch('[0-9a-f]{40}', row[k]) for k in ('source_commit', 'source_tree'))
        and hashed(row['dockerd_sha256']), 'host-profile')
    closed(row['binaries'], ' '.join(BINS), 'host-profile')
    for binary in row['binaries'].values():
        closed(binary, 'path sha256', 'host-profile')
        require(type(binary['path']) is str and hashed(binary['sha256']), 'host-profile')
    require(all(type(row[k]) is str and row[k] for k in ('private_root', 'client_config')), 'host-profile')


def approval(row, digest, raw, p, mode, now):
    closed(row, 'schema authority operation_id mode profile_sha256 custody_sha256 '
        'source_commit source_tree valid_from expires_at public_only', 'host-approval')
    require(hashed(digest) and sha(raw) == digest and row['schema'] == 'ha-operation-approval/1'
        and row['authority'] == 'Howard' and row['mode'] == mode
        and mode in ('INSPECT', 'QUALIFY_PUBLIC') and row['public_only'] is True
        and hashed(row['operation_id']) and hashed(row['custody_sha256'])
        and row['profile_sha256'] == sha(canonical(p))
        and row['source_commit'] == p['source_commit'] and row['source_tree'] == p['source_tree'], 'host-approval')
    start, end = aware(row['valid_from']), aware(row['expires_at'])
    require(start <= now < end and 0 < (end-start).total_seconds() <= 7200, 'host-clock')
    return min(5400, (end-now).total_seconds())


def private_directory(value):
    require(os.name == 'posix', 'host-platform')
    path = Path(value)
    require(path.is_absolute() and path == path.resolve(strict=True)
        and not str(path).startswith(('/mnt/', '/media/', '/run/desktop/')), 'host-path')
    info = path.stat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
        and stat.S_IMODE(info.st_mode) == 0o700, 'host-permissions')
    for parent in path.parents:
        row = parent.stat()
        require(row.st_uid in (0, os.getuid()) and not stat.S_IMODE(row.st_mode) & 0o022, 'host-permissions')
    return path


def exclusive(path, raw):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        require(os.write(fd, raw) == len(raw), 'host-file')
        os.fsync(fd)
    finally:
        os.close(fd)
    directory = os.open(Path(path).parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    require(read(path, max(1048576, len(raw))) == raw, 'host-file')


def private_control_file(path):
    require(os.name == 'posix', 'host-platform')
    require(path.is_absolute() and path == path.resolve(strict=True) and not path.is_symlink(), 'host-path')
    info = path.stat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
        and info.st_nlink == 1 and stat.S_IMODE(info.st_mode) == 0o600, 'host-permissions')


class Commands:
    """Bounded memory capture with no shell and no inherited endpoint settings."""
    def __init__(self, binaries, deadline, wall_deadline):
        self.binaries, self.deadline = binaries, deadline
        self.wall_deadline = wall_deadline

    def run(self, command, *, allowed=(0,), seconds=30, cap=4194304):
        require(command and type(command[0]) is str and command[0] != 'sudo' and command[0] in self.binaries, 'host-command')
        entry = self.binaries[command[0]]
        binary = Path(entry['path'])
        require(binary.is_absolute() and binary == binary.resolve(strict=True)
            and sha(read(binary, 268435456)) == entry['sha256'], 'host-cli')
        remaining = min(seconds, self.deadline-time.monotonic(), self.wall_deadline-time.time())
        require(remaining > 0, 'host-deadline')
        env = dict(PATH='/usr/bin:/bin', LANG='C.UTF-8', LC_ALL='C.UTF-8', TZ='UTC', PYTHONDONTWRITEBYTECODE='1')
        proc = subprocess.Popen([str(binary), *command[1:]], env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        outputs, overflow = [bytearray(), bytearray()], threading.Event()
        def collect(index, stream):
            try:
                while True:
                    block = stream.read(65536)
                    if not block:
                        break
                    if len(outputs[index])+len(block) > cap:
                        overflow.set()
                        os.killpg(proc.pid, signal.SIGKILL)
                        break
                    outputs[index].extend(block)
            except (OSError, ValueError):
                overflow.set()
        readers = [threading.Thread(target=collect, args=(i, stream), daemon=True)
                   for i, stream in enumerate((proc.stdout, proc.stderr))]
        for reader in readers:
            reader.start()
        try:
            proc.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            raise Refused('host-deadline') from None
        finally:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait()
            for reader in readers:
                reader.join(timeout=2)
            proc.stdout.close()
            proc.stderr.close()
        require(not overflow.is_set() and all(not r.is_alive() for r in readers), 'host-output-cap')
        require(time.monotonic() < self.deadline and time.time() < self.wall_deadline
                and proc.returncode in allowed, 'host-command')
        return proc.returncode, bytes(outputs[0]), bytes(outputs[1])

    def out(self, command, **kwargs):
        return self.run(command, **kwargs)[1]


def system_tool(binaries, name):
    """Only distro executables at these fixed locations may cross the sudo boundary."""
    locations = {
        'sudo': ('/usr/bin/sudo',),
        'readlink': ('/usr/bin/readlink',),
        'sha256sum': ('/usr/bin/sha256sum',),
        'ss': ('/usr/bin/ss', '/usr/sbin/ss'),
    }
    entry = binaries[name]
    require(entry['path'] in locations[name], 'host-cli')
    path = Path(entry['path'])
    require(path.resolve(strict=True) == path, 'host-cli')
    for part in (path, *path.parents):
        info = part.stat()
        require(info.st_uid == 0 and not info.st_mode & 0o022, 'host-cli')
    require(sha(read(path, 268435456)) == entry['sha256'], 'host-cli')
    return str(path)


def engine_pid(value):
    require(type(value) is str and re.fullmatch(r'[1-9][0-9]{0,9}', value)
            and 1 < int(value) <= 2147483647, 'host-endpoint')
    return value


def attended_engine_facts(commands, pid):
    engine_pid(pid)
    sudo, link, digest, ss = (system_tool(commands.binaries, n)
                              for n in ('sudo', 'readlink', 'sha256sum', 'ss'))
    prefix = [sudo, '-k', '-u', 'root', '--']
    proc = '/proc/' + pid
    fixed_reads = (
        [link, '--', proc + '/exe'],
        [digest, '--', proc + '/exe'],
        [link, '--', proc + '/root'],
        [link, '--', proc + '/ns/mnt'],
        [ss, '-Hxlpn', 'src', '=', '/run/docker.sock', 'or', 'src', '=', '/var/run/docker.sock'],
    )
    exe, checksum, root, namespace, listener = [
        attended_read(prefix + args, commands.deadline, commands.wall_deadline) for args in fixed_reads
    ]
    match = re.fullmatch(r'([a-f0-9]{64})  ' + re.escape(proc + '/exe') + '\n', checksum)
    require(match and exe.startswith('/') and exe.endswith('/dockerd\n') and exe.count('\n') == 1
            and root == '/\n' and re.fullmatch(r'mnt:\[[0-9]+\]\n', namespace), 'host-endpoint')
    return match[1], root.rstrip('\n'), namespace.rstrip('\n'), listener.splitlines()


def attended_read(argv, deadline, wall_deadline):
    """Keep sudo in the foreground terminal group. Only its stdout enters H1 memory."""
    require(os.name == 'posix' and os.getuid() != 0 and os.geteuid() != 0
            and not os.environ.get('GITHUB_ACTIONS') and sys.stdin.isatty()
            and os.tcgetpgrp(sys.stdin.fileno()) == os.getpgrp(), 'host-operator')
    end = min(deadline, time.monotonic() + 90)
    def remaining():
        seconds = min(end - time.monotonic(), wall_deadline - time.time())
        require(seconds > 0, 'host-deadline')
        return seconds
    remaining()
    # No -S, askpass, shell, inherited environment, terminal transcript or password pipe.
    with subprocess.Popen(argv, cwd='/', env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'},
                          stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL) as child:
        output = bytearray()
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(child.stdout, selectors.EVENT_READ)
                while True:
                    require(selector.select(remaining()), 'host-deadline')
                    chunk = os.read(child.stdout.fileno(), 8192)
                    if not chunk:
                        break
                    output.extend(chunk)
                    require(len(output) <= 65536, 'host-output-cap')
            require(child.wait(timeout=remaining()) == 0, 'host-command')
        except subprocess.TimeoutExpired:
            raise Refused('host-deadline') from None
        finally:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    child.kill()
    return bytes(output).decode('utf-8', 'strict')


def engine_join(pid, process_root, process_namespace, self_namespace, socket_path, listeners, info):
    require(type(pid) is str and pid.isdigit() and int(pid) > 1
        and process_root == '/' and process_namespace == self_namespace
        and socket_path == '/run/docker.sock', 'host-endpoint')
    rows = [line for line in listeners if re.search(r'\s(?:/var)?/run/docker\.sock\s', line)]
    require(len(rows) == 1 and re.search(
        r'\("dockerd",pid=' + re.escape(pid) + r',fd=[0-9]+\)', rows[0]), 'host-endpoint')
    require(info.get('OSType') == 'linux' and info.get('Architecture') in ('x86_64', 'amd64')
        and 'desktop' not in json.dumps(info).lower(), 'host-endpoint')


def native_filesystem(row):
    require(type(row) is dict and len(row.get('filesystems', [])) == 1
        and row['filesystems'][0].get('fstype') == 'ext4'
        and str(row['filesystems'][0].get('source', '')).startswith('/dev/'), 'host-native-fs')


class Host:
    def __init__(self, p, commands):
        self.p, self.commands = p, commands

    def docker(self, *args, **kwargs):
        require(not list(Path(self.p['client_config']).iterdir()), 'host-endpoint')
        return self.commands.out(['docker', '--config', self.p['client_config'],
            '--host', 'unix:///var/run/docker.sock', *args], **kwargs)

    def filesystem(self, path):
        row = strict(self.commands.out(['findmnt', '--json', '--target', str(path), '--output', 'FSTYPE,SOURCE,TARGET']))
        native_filesystem(row)

    def observe(self):
        require(os.name == 'posix' and platform.system() == 'Linux' and platform.machine() == 'x86_64'
            and 'microsoft-standard-wsl2' in read('/proc/sys/kernel/osrelease').decode().lower(), 'host-platform')
        require(os.getuid() != 0 and os.geteuid() != 0, 'host-operator')
        root = private_directory(self.p['private_root'])
        config = private_directory(self.p['client_config'])
        require(root != config and not list(config.iterdir()), 'host-endpoint')
        self.filesystem(root)
        acl = self.commands.out(['getfacl', '-cp', '--', str(root)]).decode().splitlines()
        require(set(line for line in acl if line) == {'user::rwx', 'group::---', 'other::---'}, 'host-permissions')
        require(os.statvfs(root).f_bavail * os.statvfs(root).f_frsize >= 21474836480, 'host-space')
        pid_query = ['systemctl', 'show', 'docker', '--property=MainPID', '--value']
        pid = engine_pid(self.commands.out(pid_query).decode().strip())
        process = Path('/proc') / pid
        instance = process.stat()
        digest, process_root, namespace, listeners = attended_engine_facts(self.commands, pid)
        require(digest == self.p['dockerd_sha256'], 'host-endpoint')
        socket = Path('/var/run/docker.sock')
        require(socket.resolve(strict=True) == Path('/run/docker.sock')
            and stat.S_ISSOCK(socket.stat().st_mode), 'host-endpoint')
        info = strict(self.docker('info', '--format', '{{json .}}'))
        require(self.commands.out(pid_query).decode().strip() == pid
                and os.path.samestat(instance, process.stat()), 'host-endpoint')
        engine_join(pid, process_root, namespace,
                    os.readlink('/proc/self/ns/mnt'), str(socket.resolve()), listeners, info)
        self.filesystem(info['DockerRootDir'])
        require(not self.docker('ps', '-aq').strip(), 'host-workloads')
        return dict(native_linux_amd64=True, local_distro_engine=True, native_private_fs=True,
                    owner_only=True, empty_daemon=True, host_free_ge_20gib=True)


def source_identity(commands, p):
    root = str(ref.ROOT.resolve())
    values = [commands.out(['git', '-C', root, 'rev-parse', value]).decode().strip() for value in ('HEAD', 'HEAD^{tree}')]
    require(values == [p['source_commit'], p['source_tree']]
        and not commands.out(['git', '-C', root, 'status', '--porcelain', '--untracked-files=no']).strip()
        and not commands.out(['git', '-C', root, 'ls-files', '--others']).strip(), 'host-source')
    return values


def public_bindings():
    raw = read(ref.ROOT/qualification.BINDING)
    row = strict(raw)
    for key in ('recipe', 'installer', 'request'):
        ref.joined(ref.ROOT, row[key])
    for entry in row['sources']:
        ref.joined(ref.ROOT, entry)
    require(row['public_suite_sha256'] == SUITE and row['package_library_sha256'] == PACKAGE, 'host-binding')
    req = strict(ref.joined(ref.ROOT, row['request']))
    suite = strict(ref.joined(ref.ROOT, req['suite']))
    probes = strict(ref.joined(ref.ROOT, req['probes']))['probes']
    source = strict(ref.joined(ref.ROOT, req['source_binding']))
    return row, req, suite, probes, source


def public_boundary(row, image, root, output, permit, uid):
    require(row.get('Image') == image and row.get('HostConfig', {}).get('NetworkMode') == 'none', 'host-boundary')
    h = row['HostConfig']
    require(h.get('ReadonlyRootfs') is True and not h.get('Privileged')
        and h.get('CapDrop') == ['ALL'] and 'no-new-privileges' in h.get('SecurityOpt', [])
        and h.get('Memory') == 2147483648 and h.get('PidsLimit') == 128
        and h.get('CgroupnsMode') == 'private'
        and h.get('LogConfig', {}).get('Type') == 'none'
        and not h.get('Devices') and not h.get('CapAdd')
        and row.get('Config', {}).get('User') == uid, 'host-boundary')
    mounts = {m['Destination']: m for m in row.get('Mounts', []) if m.get('Type') == 'bind'}
    expected = {'/source': (str(root), False), '/output': (str(output), True), '/host-public-permit.json': (str(permit), False)}
    require(set(mounts) == set(expected) and all((mounts[k]['Source'], mounts[k]['RW']) == v for k, v in expected.items()), 'host-boundary')
    require(all(m['Type'] == 'bind' or (m['Type'] == 'tmpfs' and m['Destination'] in ('/tmp', '/work'))
                for m in row.get('Mounts', [])), 'host-boundary')
    require(set(h.get('Tmpfs', {})) == {'/tmp', '/work'}, 'host-boundary')


def qualify_public(host, p, authority, custody_hash, deadline, postflight):
    row, req, suite, probes, source = public_bindings()
    parent = private_directory(p['private_root'])
    run = parent/('public-qualification-'+authority['operation_id'])
    run.mkdir(mode=0o700)  # exclusive; never reuse an old operation
    output = run/'observations'
    output.mkdir(mode=0o700)
    permit = run/'public-permit.json'
    exclusive(permit, canonical(dict(schema='ha-public-container/1', public_only=True, suite_sha256=SUITE)))
    iid = run/'image.id'
    context = run/'build-context'
    (context/'tools/legacy_twin').mkdir(mode=0o700, parents=True)
    build_config = run/'build-client-config'
    build_config.mkdir(mode=0o700)
    for key in ('recipe', 'installer'):
        exclusive(context/row[key]['path'], ref.joined(ref.ROOT, row[key]))
    host.commands.out(['docker', '--config', str(build_config), '--host', 'unix:///var/run/docker.sock',
        'build', '--platform', 'linux/amd64', '--file', str(context/row['recipe']['path']),
        '--iidfile', str(iid), str(context)], seconds=min(1800, deadline-time.monotonic()), cap=16777216)
    image = read(iid).decode().strip()
    require(re.fullmatch('sha256:[a-f0-9]{64}', image) is not None, 'host-image')
    inspection = strict(host.docker('image', 'inspect', image))
    require(len(inspection) == 1 and inspection[0]['Id'] == image
        and inspection[0]['Architecture'] == 'amd64' and inspection[0]['Os'] == 'linux', 'host-image')
    name = 'ha-public-'+authority['operation_id'][:32]
    uid = str(os.getuid())+':'+str(os.getgid())
    created = False
    cleanup = False
    try:
        host.docker('create', '--name', name, '--network=none', '--read-only', '--cap-drop=ALL',
            '--security-opt=no-new-privileges', '--cpus=2', '--memory=2g', '--pids-limit=128',
            '--log-driver=none', '--cgroupns=private', '--user', uid, '--tmpfs', '/tmp:rw,nosuid,nodev,size=256m',
            '--tmpfs', '/work:rw,nosuid,nodev,exec,size=1g',
            '--mount', 'type=bind,src='+str(ref.ROOT.resolve())+',dst=/source,readonly',
            '--mount', 'type=bind,src='+str(output)+',dst=/output',
            '--mount', 'type=bind,src='+str(permit)+',dst=/host-public-permit.json,readonly',
            '--env', 'PYTHONPATH=/source/src:/source', '--env', 'PYTHONDONTWRITEBYTECODE=1',
            '--workdir', '/source', image, 'python3', '-B', 'tools/intcalc_attended_reference_public.py',
            'compare', '--request', '/source/'+row['request']['path'], '--output', '/output/public')
        created = True
        public_boundary(strict(host.docker('inspect', name))[0], image, ref.ROOT.resolve(), output, permit, uid)
        host.docker('start', name)
        status = host.docker('wait', name, seconds=min(2100, deadline-time.monotonic()-60)).decode().strip()
        require(status in ('0', '2'), 'host-public-worker')
    finally:
        if created:
            host.docker('rm', '-f', name, seconds=20)
            cleanup = not host.docker('ps', '-a', '--filter', 'name=^/'+name+'$', '--format', '{{.Names}}', seconds=10).strip()
        exclusive(run/'cleanup.json', canonical(dict(cleanup=cleanup, operation_id=authority['operation_id']))+b'\n')
    require(cleanup, 'host-cleanup')
    report_raw = read(output/'public/report.json')
    report = strict(report_raw)
    inventory_raw = read(output/'public/inventory.json', 4194304)
    require(provisional.inventory_digest(strict(inventory_raw)) == PACKAGE
        and ref.sha(inventory_raw) == report['inventory_sha256'], 'host-inventory')
    good = qualification.attest(report, row, row['request']['sha256'], suite, probes, source)
    require((status == '0') == good, 'host-criterion')
    resources = report.get('host_resources')
    closed(resources, 'cgroup_memory_peak_bytes elapsed_milliseconds', 'host-criterion')
    require(type(resources['cgroup_memory_peak_bytes']) is int
        and 0 < resources['cgroup_memory_peak_bytes'] <= 2147483648
        and type(resources['elapsed_milliseconds']) is int
        and 0 <= resources['elapsed_milliseconds'] <= 2100000, 'host-criterion')
    source_identity(host.commands, p)
    host.observe()
    post_hash = postflight()
    require(hashed(post_hash) and time.monotonic() < deadline, 'host-custody')
    receipt = dict(schema='ha-public-host-qualification/1', status='CRITERION_MET' if good else 'DISCREPANCY',
        operation_id=authority['operation_id'], source_commit=p['source_commit'], source_tree=p['source_tree'],
        qualification_source_commit=QUALIFICATION_COMMIT, qualification_source_tree=QUALIFICATION_TREE,
        reviewed_qualification_sha256=QUALIFICATION_RECEIPT, profile_sha256=sha(canonical(p)),
        custody_sha256=custody_hash, postflight_custody_sha256=post_hash,
        public_suite_sha256=SUITE, package_library_sha256=PACKAGE,
        report_sha256=sha(report_raw), inventory_sha256=sha(inventory_raw),
        comparison_criterion_met=good, cases=len(report['cases']), probes=len(report['probes']),
        all_probes_match=report['all_probes_match'], cleanup=True, public_only=True,
        host_resources=resources,
        local_image_id=image, image_digest_bound=False, private_use_authorized=False, limits=LIMITS)
    exclusive(run/'HOST-QUALIFICATION.json', canonical(receipt)+b'\n')
    return good


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('INSPECT', 'QUALIFY_PUBLIC'))
    for key in ('profile', 'custody', 'approval'):
        parser.add_argument('--'+key, type=Path, required=True)
    parser.add_argument('--approval-sha256', required=True)
    parser.add_argument('--postflight', type=Path)
    args = parser.parse_args(argv)
    require(os.name == 'posix' and not os.environ.get('GITHUB_ACTIONS') and sys.stdin.isatty(), 'host-operator')
    os.umask(0o077)
    for control in (args.profile, args.custody, args.approval):
        private_control_file(control)
    p = strict(read(args.profile)); profile(p)
    raw, custody_raw = read(args.approval), read(args.custody)
    authorized = strict(raw)
    seconds = approval(authorized, args.approval_sha256, raw, p, args.mode, datetime.now(timezone.utc))
    require(sha(custody_raw) == authorized['custody_sha256'], 'host-custody')
    observed = strict(custody_raw)
    custody(observed, authorized['operation_id'], sha(canonical(p)), p['source_commit'], p['source_tree'])
    require(aware(authorized['valid_from']) <= aware(observed['observed_at_with_offset'])
        <= datetime.now(timezone.utc), 'host-clock')
    require(input('Type the reviewed approval SHA256: ').strip() == args.approval_sha256, 'host-approval')
    seconds = approval(authorized, args.approval_sha256, raw, p, args.mode, datetime.now(timezone.utc))
    deadline = time.monotonic()+seconds
    commands = Commands(p['binaries'], deadline, aware(authorized['expires_at']).timestamp())
    source_identity(commands, p)
    host = Host(p, commands)
    host.observe()
    if args.mode == 'INSPECT':
        print('host-custody-local-checks-match-public-qualification-pending')
        return 0
    require(args.postflight is not None and not args.postflight.exists(), 'host-arguments')
    def postflight():
        after = datetime.now(timezone.utc)
        expected = input('Perform the reviewed postflight checks; enter their exact receipt SHA256: ').strip()
        private_control_file(args.postflight)
        raw_post = read(args.postflight)
        require(hashed(expected) and sha(raw_post) == expected, 'host-custody')
        post = strict(raw_post)
        custody(post, authorized['operation_id'], sha(canonical(p)), p['source_commit'], p['source_tree'], post=True)
        require(after <= aware(post['observed_at_with_offset']) <= datetime.now(timezone.utc)
                < aware(authorized['expires_at']), 'host-clock')
        return expected
    good = qualify_public(host, p, authorized, sha(custody_raw), deadline, postflight)
    print('host-public-criterion-met-review-required' if good else 'host-public-discrepancy')
    return 0 if good else 2


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Refused as error:
        print(error.code)
        raise SystemExit(2) from None
    except (Exception, KeyboardInterrupt):
        print('host-fault')
        raise SystemExit(2) from None
