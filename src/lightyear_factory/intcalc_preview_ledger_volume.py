"""Actual-volume pre-admission probe used only by the fixed attended bootstrap.

Creates only exclusive public probe files in the two explicitly supplied ledger
parents. Never cleans, repairs permissions, follows a symlink or falls back from
F_FULLFSYNC. A successful syscall/readback is not a power-loss experiment.
"""
import ctypes
from dataclasses import dataclass
import errno
import os
from pathlib import Path
import platform
import stat
import sys
import time

from lightyear_factory import intcalc_preview_admission as a
from lightyear_factory import intcalc_preview_composition as c
from lightyear_factory import intcalc_preview_transport as t

MIN_FREE = 20 * 1024 ** 3
MAX_AGE_SECONDS = 5
_SEAL = object()


class VolumeRefused(ValueError):
    def __init__(self, code, file_kind='none', error_number=None):
        self.code, self.file_kind, self.error_number = code, file_kind, error_number
        super().__init__(code)  # no raw exception, local path or device name

    def public_record(self):
        return {'status': 'REFUSED', 'reason': self.code, 'file_kind': self.file_kind,
                'errno': self.error_number, 'qualified': False, 'power_loss_tested': False}


def require(ok, code, kind='none'):
    if not ok:
        raise VolumeRefused(code, kind)


def native():
    require(os.name == 'posix' and sys.platform == 'darwin' and platform.machine() == 'arm64', 'native-macos-arm64-required')


class StatFS64(ctypes.Structure):
    # Darwin arm64 public struct statfs ABI, Apple xnu bsd/sys/mount.h.
    # Field layout is checked before calling libc; no guessed network CLI output.
    _fields_ = [('bsize', ctypes.c_uint32), ('iosize', ctypes.c_int32),
        ('blocks', ctypes.c_uint64), ('bfree', ctypes.c_uint64), ('bavail', ctypes.c_uint64),
        ('files', ctypes.c_uint64), ('ffree', ctypes.c_uint64), ('fsid', ctypes.c_int32 * 2),
        ('owner', ctypes.c_uint32), ('type', ctypes.c_uint32), ('flags', ctypes.c_uint32),
        ('subtype', ctypes.c_uint32), ('fstypename', ctypes.c_char * 16),
        ('mounton', ctypes.c_char * 1024), ('mountfrom', ctypes.c_char * 1024),
        ('flags_ext', ctypes.c_uint32), ('reserved', ctypes.c_uint32 * 7)]


def filesystem(fd):
    native()
    require(ctypes.sizeof(StatFS64) == 2168 and StatFS64.flags.offset == 64
            and StatFS64.fstypename.offset == 72, 'statfs-abi')
    libc = ctypes.CDLL('/usr/lib/libSystem.B.dylib', use_errno=True)
    function = libc.fstatfs
    function.argtypes = (ctypes.c_int, ctypes.POINTER(StatFS64))
    function.restype = ctypes.c_int
    result = StatFS64()
    if function(fd, ctypes.byref(result)) != 0:
        raise VolumeRefused('fstatfs-failed', 'directory', ctypes.get_errno())
    return {'filesystem': bytes(result.fstypename).decode('ascii', errors='strict'),
            'fsid': list(result.fsid), 'flags': int(result.flags),
            'available_bytes': int(result.bavail) * int(result.bsize)}


def validate_filesystem(observation):
    require(type(observation) is dict and set(observation) == {'filesystem', 'fsid', 'flags', 'available_bytes'}, 'filesystem-fields')
    require(observation['filesystem'] == 'apfs', 'apfs-required')
    flags = observation['flags']
    require(type(flags) is int and flags & 0x1000 != 0, 'local-volume-required')
    # Refuse read-only, removable, ownership-ignoring and snapshot mounts.
    require(not flags & (0x1 | 0x200 | 0x200000 | 0x40000000), 'volume-flags')
    require(type(observation['available_bytes']) is int and observation['available_bytes'] >= MIN_FREE, 'host-disk-headroom')
    require(type(observation['fsid']) is list and len(observation['fsid']) == 2
            and all(type(v) is int for v in observation['fsid']), 'filesystem-identity')


def open_parent(value):
    native()
    path = Path(value)
    require(path.is_absolute() and path == path.resolve(strict=True), 'resolved-parent-required')
    require(not any(part in ('.', '..') for part in path.parts), 'parent-components')
    # This catches known synchronized namespaces; it is not a discovery of all
    # sync software. The authenticated attended placement record is also required.
    deny = ('onedrive', 'dropbox', 'cloudstorage', 'mobile documents', 'google drive')
    require(not any(any(word in part.lower() for word in deny) for part in path.parts), 'synchronized-parent')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parts[1:]:
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = nxt
        info = os.fstat(fd)
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
                and stat.S_IMODE(info.st_mode) == 0o700, 'ledger-parent-owner-mode', 'directory')
        return path, fd, (info.st_dev, info.st_ino)
    except OSError as error:
        os.close(fd)
        raise VolumeRefused('parent-io-failed', 'directory', error.errno) from None
    except BaseException:
        os.close(fd)
        raise


def full_sync(fd, kind):
    native()
    import fcntl
    require(hasattr(fcntl, 'F_FULLFSYNC'), 'fullfsync-unavailable', kind)
    try:
        fcntl.fcntl(fd, fcntl.F_FULLFSYNC)
    except OSError as error:
        raise VolumeRefused('fullfsync-failed', kind, error.errno) from None


def probe_directory(fd, name):
    """O_EXCL, exact bytes, full-sync file + directory; retain on all outcomes."""
    require(c.is_hash(name), 'probe-id')
    leaf = 'c2-volume-probe-' + name + '.json'
    raw = c.canonical({'schema': 'full-intcalc-ledger-volume-probe/1', 'probe_id': name,
                       'public_only': True, 'credential': False}) + b'\n'
    file_fd = None
    kind = 'file'
    try:
        file_fd = os.open(leaf, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        info = os.fstat(file_fd)
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == os.getuid()
                and stat.S_IMODE(info.st_mode) == 0o600, 'probe-file-kind', 'file')
        require(os.write(file_fd, raw) == len(raw), 'probe-short-write', 'file')
        full_sync(file_fd, 'file')
        kind = 'directory'
        full_sync(fd, 'directory')
        kind = 'file'
        os.lseek(file_fd, 0, os.SEEK_SET)
        require(os.read(file_fd, len(raw) + 1) == raw, 'probe-readback', 'file')
        # A second create must fail specifically with EEXIST. No overwrite/retry.
        try:
            duplicate = os.open(leaf, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        except FileExistsError:
            pass
        else:
            os.close(duplicate)
            raise VolumeRefused('exclusive-create-not-enforced', 'file')
        return {'probe_sha256': c.digest(raw), 'exclusive_create': True, 'readback_match': True,
                'file_fullfsync': True, 'directory_fullfsync': True}
    except OSError as error:
        raise VolumeRefused('probe-io-failed', kind, error.errno) from None
    finally:
        if file_fd is not None:
            os.close(file_fd)


@dataclass(frozen=True)
class AttendedPlacement:
    # Trusted bootstrap must authenticate this record; caller-supplied booleans
    # or a hash alone cannot establish operator authority.
    approval_sha256: str
    use_parent_identity: tuple
    run_parent_identity: tuple
    filesystem_id: tuple
    outside_sync_and_candidate_roots: bool


class VolumeLease:
    def __init__(self, seal, rows, placement, observed, receipts):
        require(seal is _SEAL, 'probe-capability-required')
        self._rows, self._placement, self._observed = rows, placement, observed
        self._pid, self._used, self._closed = os.getpid(), False, False
        self._receipts = receipts

    def check(self, *, admission=False):
        try:
            return self._check(admission=admission)
        except BaseException:
            self.close()
            raise

    def _check(self, *, admission=False):
        require(not self._closed and os.getpid() == self._pid, 'lease-process-or-closed')
        now = time.monotonic()
        require(now >= self._observed, 'clock-regressed')
        if admission:
            require(not self._used and now - self._observed <= MAX_AGE_SECONDS, 'admission-volume-stale-or-used')
            self._used = True  # any subsequent admission failure stays consumed
        for path, fd, identity in self._rows.values():
            current = os.fstat(fd)
            require((current.st_dev, current.st_ino) == identity and current.st_uid == os.getuid()
                    and stat.S_IMODE(current.st_mode) == 0o700, 'pinned-parent-drift')
            _, reopened, observed = open_parent(path)
            try:
                require(observed == identity, 'parent-path-rebound')
            finally:
                os.close(reopened)
            fs = filesystem(fd)
            validate_filesystem(fs)
            require(tuple(fs['fsid']) == self._placement.filesystem_id, 'volume-changed')
        return True

    def receipt(self):
        return {'schema': 'full-intcalc-ledger-volume-observation/1', 'status': 'PROBE_PASSED',
                'placement_approval_sha256': self._placement.approval_sha256,
                'filesystem': 'apfs', 'local': True, 'minimum_host_free_bytes': MIN_FREE,
                'probes': c.strict_json(c.canonical(self._receipts)),
                'admission_max_age_seconds': MAX_AGE_SECONDS, 'power_loss_tested': False,
                'hardware_flush_honesty_established': False, 'docker_disk_headroom_checked': False,
                'qualified': False, 'production_controller_receipt': False}

    def close(self):
        if not self._closed:
            self._closed = True
            for _, fd, _ in self._rows.values():
                os.close(fd)


def qualify(use_parent, run_parent, *, probe_id, placement):
    native()
    require(type(placement) is AttendedPlacement and c.is_hash(placement.approval_sha256)
            and placement.outside_sync_and_candidate_roots is True and c.is_hash(probe_id), 'authenticated-placement-required')
    rows, receipts = {}, {}
    started = time.monotonic()
    try:
        for kind, value, expected in (('use', use_parent, placement.use_parent_identity),
                                      ('run', run_parent, placement.run_parent_identity)):
            path, fd, identity = open_parent(value)
            rows[kind] = (path, fd, identity)
            require(identity == expected, 'placement-parent-identity')
            fs = filesystem(fd)
            validate_filesystem(fs)
            require(tuple(fs['fsid']) == placement.filesystem_id, 'placement-filesystem')
        require(rows['use'][2] != rows['run'][2], 'distinct-ledger-parents-required')
        for kind, (_, fd, _) in rows.items():
            receipts[kind] = probe_directory(fd, c.digest((probe_id + ':' + kind).encode('ascii')))
        # Synchronous kernel calls cannot be preempted here. A late return is
        # refused; the attended operator must stop a hung preflight; no admission follows it.
        require(time.monotonic() - started <= 30, 'probe-late-no-admission')
        lease = VolumeLease(_SEAL, rows, placement, time.monotonic(), receipts)
        lease._check()  # qualify owns descriptor cleanup until the lease returns
        return lease
    except BaseException:
        for _, fd, _ in rows.values():
            os.close(fd)
        raise


class CheckedUseStore:
    def __init__(self, lease):
        require(type(lease) is VolumeLease, 'actual-volume-lease-required')
        self.lease = lease

    def consume(self, credential_id, nonce_sha256):
        self.lease.check(admission=True)
        a.ExclusivePreviewUseStore(str(self.lease._rows['use'][0])).consume(credential_id, nonce_sha256)
        self.lease.check()


class CheckedRunLedger:
    def __init__(self, lease, run_id):
        require(type(lease) is VolumeLease, 'actual-volume-lease-required')
        lease.check()
        self.lease = lease
        self.inner = t.ExclusiveRunLedger(str(lease._rows['run'][0]), run_id)
        try:
            lease.check()
        except BaseException:
            self.inner.close()
            raise

    def record_once(self, name, value):
        self.lease.check()
        self.inner.record_once(name, value)
        self.lease.check()

    def close(self):
        self.inner.close()
