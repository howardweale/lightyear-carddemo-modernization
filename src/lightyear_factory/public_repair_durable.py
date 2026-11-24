"""Exclusive durable ports for the new public-repair controller.

No admission, provider, graph or retired INTCALC route is imported. POSIX only;
macOS requires F_FULLFSYNC for files and directories without a fallback. Hashes
establish byte readback, not authority or power-loss behavior of the hardware.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import time

RECORD_BYTES = 1048576
TOTAL_BYTES = 67108864
FILE_COUNT = 512
NAME = re.compile(r'[a-z][a-z0-9-]{0,95}\Z')
HASH = re.compile(r'[0-9a-f]{64}\Z')
SLOT = re.compile(r'(?:planner|builder-0|analysis-[1-5]|repair-[1-5])\Z')
CODES = frozenset(('durable-posix-required', 'durable-path', 'durable-ancestor',
    'durable-parent-mode', 'durable-path-rebound', 'durable-file', 'durable-io',
    'durable-name', 'durable-json', 'durable-cap', 'durable-artifact',
    'durable-exclusive', 'durable-short-write', 'durable-readback',
    'durable-full-sync-unavailable', 'durable-full-sync', 'durable-state',
    'durable-deadline', 'durable-clock', 'durable-run-id'))


class Refused(ValueError):
    def __init__(self, code, file_kind='none', error_number=None):
        self.code = code if type(code) is str and code in CODES else 'durable-io'
        self.file_kind = file_kind if type(file_kind) is str and file_kind in ('none', 'file', 'directory') else 'none'
        self.error_number = error_number if type(error_number) is int and 0 <= error_number < 2 ** 31 else None
        super().__init__(self.code)

    def public_record(self):
        return dict(refusal_code=self.code, file_kind=self.file_kind,
                    errno=self.error_number)


def require(ok, code, kind='none'):
    if not ok:
        raise Refused(code, kind)


def posix():
    require(os.name == 'posix', 'durable-posix-required')


def canonical(value):
    def check(item, depth=0):
        require(depth <= 32, 'durable-json')
        if item is None or type(item) in (str, int, bool):
            return
        if type(item) is list:
            for child in item:
                check(child, depth + 1)
        elif type(item) is dict and all(type(k) is str for k in item):
            for child in item.values():
                check(child, depth + 1)
        else:
            raise Refused('durable-json')
    try:
        check(value)
        raw = json.dumps(value, sort_keys=True, separators=(',', ':'),
                         ensure_ascii=True, allow_nan=False).encode('ascii')
    except (ValueError, UnicodeError, RecursionError, OverflowError) as error:
        if isinstance(error, Refused):
            raise
        raise Refused('durable-json') from None
    require(len(raw) + 1 <= RECORD_BYTES, 'durable-cap')
    return raw


def full_sync(fd, kind):
    posix()
    try:
        if sys.platform == 'darwin':
            import fcntl
            require(hasattr(fcntl, 'F_FULLFSYNC'),
                    'durable-full-sync-unavailable', kind)
            fcntl.fcntl(fd, fcntl.F_FULLFSYNC)
        else:
            os.fsync(fd)
    except OSError as error:
        raise Refused('durable-full-sync', kind, error.errno) from None


def identity(info):
    return info.st_dev, info.st_ino


def close_quiet(fd):
    if fd is not None:
        try:
            os.close(fd)
        except OSError:
            pass  # cleanup must not replace the original failure


def open_parent(value):
    posix()  # before O_DIRECTORY, O_NOFOLLOW, getuid or platform-specific use
    path = Path(value)
    require(path.is_absolute() and path == path.resolve(strict=True), 'durable-path')
    require(not any(part in ('.', '..') for part in path.parts), 'durable-path')
    denied = ('onedrive', 'dropbox', 'cloudstorage', 'mobile documents', 'google drive')
    require(not any(any(word in p.lower() for word in denied) for p in path.parts),
            'durable-path')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parts[1:]:
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                          dir_fd=fd)
            close_quiet(fd)
            fd = nxt
            info = os.fstat(fd)
            require(stat.S_ISDIR(info.st_mode) and info.st_uid in (0, os.getuid())
                    and not stat.S_IMODE(info.st_mode) & 0o022,
                    'durable-ancestor', 'directory')
        info = os.fstat(fd)
        require(info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700,
                'durable-parent-mode', 'directory')
        return path, fd, identity(info)
    except BaseException:
        close_quiet(fd)
        raise


class DurablePorts:
    """Single-process, one-run file ports; caller supplies authenticated placement.

    Parent must already exist, be resolved/private and outside candidate/sync
    roots. run_id is an authenticated run binding hash, not an authority token.
    This component never authenticates that approval. Kernel IO may block;
    late returns refuse and a qualified owner/guardian must enforce the deadline.
    """
    def __init__(self, parent, run_id, deadline, *, clock=time.monotonic):
        posix()
        self._parent_fd = self._run_fd = None
        self._failed = self._closed = False
        self._pid = os.getpid()
        self._clock, self._end = clock, deadline
        self._last = clock()
        self._files = self._bytes = 0
        require(type(run_id) is str and HASH.fullmatch(run_id), 'durable-run-id')
        require(type(deadline) in (int, float) and self._last < deadline < float('inf'),
                'durable-deadline')
        try:
            self._parent, self._parent_fd, self._parent_id = open_parent(parent)
            self._run_name = 'public-repair-' + run_id
            os.mkdir(self._run_name, 0o700, dir_fd=self._parent_fd)
            self._run_fd = os.open(self._run_name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                   dir_fd=self._parent_fd)
            self._run_id = identity(os.fstat(self._run_fd))
            full_sync(self._run_fd, 'directory')
            full_sync(self._parent_fd, 'directory')
            self._check()
            self.record('storage-probe', dict(schema='public-repair-storage-probe/1',
                run_id=run_id, synthetic_public_probe=True, power_loss_tested=False))
        except BaseException as error:
            self._failed = True
            self._cleanup()
            if isinstance(error, FileExistsError):
                raise Refused('durable-exclusive', 'directory', error.errno) from None
            if isinstance(error, OSError):
                raise Refused('durable-io', 'directory', error.errno) from None
            raise

    @property
    def written_usage(self) -> tuple[int, int]:
        """Return the number of files and bytes successfully written and read back."""
        return self._files, self._bytes

    def _cleanup(self):
        close_quiet(self._run_fd)
        close_quiet(self._parent_fd)
        self._run_fd = self._parent_fd = None

    def close(self):
        self._closed = True
        self._cleanup()

    def _check(self):
        require(not self._closed and not self._failed and os.getpid() == self._pid,
                'durable-state')
        now = self._clock()
        require(now >= self._last, 'durable-clock')
        self._last = now
        require(now < self._end, 'durable-deadline')
        _, fd, observed = open_parent(self._parent)
        close_quiet(fd)
        require(observed == self._parent_id, 'durable-path-rebound', 'directory')
        require(identity(os.fstat(self._parent_fd)) == self._parent_id,
                'durable-path-rebound', 'directory')
        info = os.fstat(self._run_fd)
        named = os.stat(self._run_name, dir_fd=self._parent_fd, follow_symlinks=False)
        require(identity(info) == self._run_id == identity(named)
                and stat.S_ISDIR(named.st_mode) and info.st_uid == os.getuid()
                and stat.S_IMODE(info.st_mode) == 0o700,
                'durable-path-rebound', 'directory')

    def _write(self, leaf, raw):
        self._check()
        require(self._files < FILE_COUNT and self._bytes + len(raw) <= TOTAL_BYTES,
                'durable-cap')
        fd = read_fd = None
        kind = 'file'
        try:
            fd = os.open(leaf, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=self._run_fd)
            info = os.fstat(fd)
            require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                    and info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o600,
                    'durable-file', kind)
            require(os.write(fd, raw) == len(raw), 'durable-short-write', kind)
            full_sync(fd, kind)
            kind = 'directory'
            full_sync(self._run_fd, kind)
            kind = 'file'
            read_fd = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=self._run_fd)
            again = os.fstat(read_fd)
            require(identity(again) == identity(info) and again.st_nlink == 1
                    and again.st_uid == os.getuid() and stat.S_IMODE(again.st_mode) == 0o600,
                    'durable-file', kind)
            chunks, remaining = [], len(raw) + 1
            while remaining:
                block = os.read(read_fd, remaining)
                if not block:
                    break
                chunks.append(block)
                remaining -= len(block)
            actual = b''.join(chunks)
            require(actual == raw, 'durable-readback', kind)
            self._check()
            self._files += 1
            self._bytes += len(raw)
            return hashlib.sha256(actual).hexdigest()
        except FileExistsError as error:
            raise Refused('durable-exclusive', kind, error.errno) from None
        except OSError as error:
            raise Refused('durable-io', kind, error.errno) from None
        finally:
            close_quiet(read_fd)
            close_quiet(fd)

    def _operation(self, make):
        try:
            self._check()
            return make()
        except BaseException as error:
            self._failed = True
            self._cleanup()
            if isinstance(error, OSError):
                raise Refused('durable-io', 'directory', error.errno) from None
            raise  # KeyboardInterrupt and SystemExit unchanged

    def record(self, name, public_record):
        def write():
            require(type(name) is str and NAME.fullmatch(name), 'durable-name')
            require(type(public_record) is dict, 'durable-json')
            return self._write('record-' + name + '.json', canonical(public_record) + b'\n')
        return self._operation(write)

    def retain_artifact(self, slot, key, text):
        def write():
            require(type(slot) is str and SLOT.fullmatch(slot), 'durable-artifact')
            expected = 'source' if slot == 'builder-0' or slot.startswith('repair-') else 'text'
            require(key == expected and type(text) is str
                    and all(ord(c) >= 32 or c in '\t\n\r' for c in text), 'durable-artifact')
            try:
                raw = text.encode('utf-8', errors='strict')
            except UnicodeError:
                raise Refused('durable-artifact') from None
            require(len(raw) <= (65536 if key == 'source' else 8192), 'durable-cap')
            return self._write('artifact-' + slot + '-' + key + '.txt', raw)
        return self._operation(write)
