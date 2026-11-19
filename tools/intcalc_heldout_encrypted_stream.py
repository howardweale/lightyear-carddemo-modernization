"""H2a: private framed stream -> pinned age -> exclusive ciphertext.

Library only. No CLI, decryption, key generation, generator or reference execution.
H2b must authenticate custody/authority and provide the bounded producer.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import time

CASE_CAP = 8 * 1024 * 1024
STREAM_CAP = 512 * 1024 * 1024
CIPHER_CAP = STREAM_CAP + 2 * 1024 * 1024
FIELDS = ('ACCTFILE', 'TCATBALF', 'DISCGRP', 'XREFFILE')
CHANNELS = ('ACCTFILE', 'TRANSACT', 'stdout', 'stderr')
CODES = frozenset(('stream-shape', 'stream-limit', 'stream-count', 'stream-order',
    'stream-deadline', 'stream-state', 'stream-binding', 'stream-platform',
    'stream-recipient', 'stream-encryptor', 'stream-encryptor-exit',
    'stream-ciphertext', 'stream-private-path', 'stream-durability',
    'stream-custody', 'stream-producer', 'stream-fault'))


class Refused(ValueError):
    pass


def require(ok, code):
    if not ok:
        raise Refused(code)


def refusal(error):
    return error.args[0] if isinstance(error, Refused) and len(error.args) == 1 and error.args[0] in CODES else 'stream-fault'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(value):
    require(type(value) is str and re.fullmatch('[0-9a-f]{64}', value), 'stream-binding')


def canonical(row):
    def check(x):
        if type(x) is dict:
            require(all(type(k) is str for k in x), 'stream-shape')
            for v in x.values(): check(v)
        elif type(x) is list:
            for v in x: check(v)
        else:
            require(x is None or type(x) in (str, bool, int), 'stream-shape')
    check(row)
    return json.dumps(row, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()


def closed(row, keys):
    require(type(row) is dict and set(row) == set(keys), 'stream-shape')


def checked_case(row, sequence):
    closed(row, ('sequence', 'inputs', 'processing_date', 'timestamp', 'outputs', 'exit', 'compare_output_files'))
    require(type(row['sequence']) is int and row['sequence'] == sequence, 'stream-order')
    require(type(row['processing_date']) is str and re.fullmatch('[0-9]{10}', row['processing_date']), 'stream-shape')
    require(type(row['timestamp']) is str and re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]{2}\.[0-9]{2}\.[0-9]{2}\.[0-9]{6}', row['timestamp']), 'stream-shape')
    require(type(row['exit']) is int and row['exit'] in (0, 12), 'stream-producer')
    require(type(row['compare_output_files']) is bool and row['compare_output_files'] == (row['exit'] == 0), 'stream-shape')
    closed(row['inputs'], FIELDS)
    closed(row['outputs'], CHANNELS)
    for group in ('inputs', 'outputs'):
        for value in row[group].values():
            require(type(value) is str and len(value) <= CASE_CAP and len(value) % 2 == 0
                    and re.fullmatch('[0-9a-f]*', value) is not None, 'stream-shape')
    if not row['compare_output_files']:
        require(row['outputs']['ACCTFILE'] == row['outputs']['TRANSACT'] == '', 'stream-shape')
    raw = canonical(row)
    require(len(raw) <= CASE_CAP, 'stream-limit')
    return raw


class Framer:
    def __init__(self, sink, binding, count):
        require(type(count) is int and 1 <= count <= 64, 'stream-count')
        digest(binding)
        self.sink, self.count, self.seen = sink, count, 0
        self.total, self.ended, self.inventory = 0, False, []
        self.hash = hashlib.sha256()
        self.send(canonical(dict(schema='heldout-encrypted-payload/1', binding_sha256=binding, count=count)))

    def send(self, raw):
        require(not self.ended and len(raw) <= CASE_CAP, 'stream-state')
        frame = len(raw).to_bytes(8, 'big') + raw
        require(self.total + len(frame) <= STREAM_CAP, 'stream-limit')
        self.sink.write(frame)
        self.hash.update(frame); self.total += len(frame)

    def case(self, row):
        require(self.seen < self.count, 'stream-count')
        raw = checked_case(row, self.seen)
        self.send(raw)
        self.inventory.append(sha(raw)); self.seen += 1

    def finish(self):
        require(self.seen == self.count and not self.ended, 'stream-count')
        # Private inventory is encrypted, never returned to caller/public receipt.
        self.send(canonical(dict(schema='heldout-encrypted-end/1', count=self.seen,
                                 frames_sha256=self.hash.hexdigest(), cases_sha256=self.inventory)))
        self.ended = True


def pin_executable(path, expected):
    digest(expected)
    require(type(path) is str and Path(path).is_absolute(), 'stream-encryptor')
    p = Path(path)
    require(p == p.resolve() and not p.is_symlink(), 'stream-encryptor')
    info = p.stat()
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and not info.st_mode & 0o022,
            'stream-encryptor')
    require(info.st_size <= 64 * 1024 * 1024 and sha(p.read_bytes()) == expected, 'stream-encryptor')


class AgeSink:
    """No plaintext persistent fd. age alone receives the ciphertext output fd."""
    def __init__(self, executable, executable_hash, recipient, recipient_hash, fd, deadline):
        require(os.name == 'posix', 'stream-platform')
        pin_executable(executable, executable_hash)
        require(type(recipient) is str and re.fullmatch('age1[023456789acdefghjklmnpqrstuvwxyz]{58}', recipient), 'stream-recipient')
        require(sha(recipient.encode('ascii')) == recipient_hash, 'stream-recipient')
        self.deadline, self.closed = deadline, False
        require(deadline > time.monotonic(), 'stream-deadline')
        def limits():
            import resource
            resource.setrlimit(resource.RLIMIT_FSIZE, (CIPHER_CAP, CIPHER_CAP))
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        self.child = subprocess.Popen([executable, '--encrypt', '--recipient', recipient],
            stdin=subprocess.PIPE, stdout=fd, stderr=subprocess.DEVNULL, env={},
            close_fds=True, start_new_session=True, preexec_fn=limits)
        os.set_blocking(self.child.stdin.fileno(), False)
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.child.stdin, selectors.EVENT_WRITE)

    def write(self, raw):
        require(not self.closed, 'stream-state')
        view = memoryview(raw)
        while view:
            remaining = self.deadline - time.monotonic()
            require(remaining > 0, 'stream-deadline')
            require(self.child.poll() is None, 'stream-encryptor-exit')
            if not self.selector.select(min(remaining, 0.25)): continue
            try: n = os.write(self.child.stdin.fileno(), view[:65536])
            except BlockingIOError: continue
            except OSError as e: raise Refused('stream-encryptor-exit') from e
            require(n > 0, 'stream-encryptor-exit'); view = view[n:]

    def finish(self):
        require(not self.closed, 'stream-state')
        self.closed = True; self.selector.close(); self.child.stdin.close()
        remaining = self.deadline - time.monotonic()
        require(remaining > 0, 'stream-deadline')
        try: code = self.child.wait(timeout=remaining)
        except subprocess.TimeoutExpired as e: raise Refused('stream-deadline') from e
        require(code == 0, 'stream-encryptor-exit')

    def abort(self):
        self.closed = True
        self.selector.close()
        if self.child.poll() is None:
            try: os.killpg(self.child.pid, signal.SIGKILL)
            except ProcessLookupError: pass
        try: self.child.stdin.close()
        except OSError: pass
        self.child.wait(timeout=5)


class PrivateStore:
    """H1 checks the filesystem/ACL/custody; this layer pins directory descriptors."""
    def __init__(self, parent, name):
        require(os.name == 'posix', 'stream-platform')
        require(re.fullmatch('[a-zA-Z0-9_-]{1,64}', name), 'stream-private-path')
        p = Path(parent)
        require(p.is_absolute() and p == p.resolve(), 'stream-private-path')
        for node in (p, *p.parents):
            require(not node.is_symlink() and node.is_dir(), 'stream-private-path')
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        parent_fd = os.open(p, flags)
        try:
            s = os.fstat(parent_fd)
            require(s.st_uid == os.getuid() and stat.S_IMODE(s.st_mode) == 0o700, 'stream-private-path')
            os.mkdir(name, 0o700, dir_fd=parent_fd)
            os.fsync(parent_fd)
            self.dir = os.open(name, flags, dir_fd=parent_fd)
        finally: os.close(parent_fd)
        self.fd = None

    def start(self):
        require(self.fd is None, 'stream-state')
        self.fd = os.open('answers.age', os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                          0o600, dir_fd=self.dir)
        info = os.fstat(self.fd)
        require(info.st_nlink == 1 and stat.S_IMODE(info.st_mode) == 0o600, 'stream-private-path')
        return self.fd

    def seal_ciphertext(self):
        os.fsync(self.fd)
        size = os.fstat(self.fd).st_size
        require(64 <= size <= CIPHER_CAP, 'stream-ciphertext')
        os.lseek(self.fd, 0, os.SEEK_SET)
        h = hashlib.sha256(); seen = 0
        while True:
            chunk = os.read(self.fd, 65536)
            if not chunk: break
            if not seen: require(chunk.startswith(b'age-encryption.org/v1\n'), 'stream-ciphertext')
            h.update(chunk); seen += len(chunk)
            require(seen <= CIPHER_CAP, 'stream-ciphertext')
        require(seen == size == os.fstat(self.fd).st_size, 'stream-ciphertext')
        os.fsync(self.dir)
        return dict(sha256=h.hexdigest(), bytes=size)

    def complete(self, raw):
        fd = os.open('completion.json', os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=self.dir)
        try:
            view = memoryview(raw)
            while view:
                n = os.write(fd, view); require(n > 0, 'stream-durability'); view = view[n:]
            os.fsync(fd); os.lseek(fd, 0, os.SEEK_SET)
            require(os.read(fd, len(raw) + 1) == raw, 'stream-durability')
            os.fsync(self.dir)
        finally: os.close(fd)

    def close(self):
        if self.fd is not None: os.close(self.fd)
        os.close(self.dir)


BINDINGS = ('source_commit', 'source_tree', 'generator_sha256', 'reference_sha256',
    'profile_sha256', 'host_qualification_sha256', 'input_commitment_sha256',
    'recipient_sha256', 'encryptor_sha256', 'policy_sha256', 'authority_sha256')


def checked_binding(row):
    closed(row, BINDINGS)
    for key, value in row.items():
        if key in ('source_commit', 'source_tree'):
            require(type(value) is str and re.fullmatch('[0-9a-f]{40}', value), 'stream-binding')
        else: digest(value)
    return sha(canonical(row))


def write_answers(rows, count, binding, store, make_sink, producer_complete, postflight, deadline,
                  clock=time.monotonic):
    """Callbacks are trusted H2b code, not candidate/plugin inputs. One transaction."""
    binding_hash = checked_binding(binding)
    sink = None
    try:
        require(clock() < deadline, 'stream-deadline')
        sink = make_sink(store.start(), deadline)
        frame = Framer(sink, binding_hash, count)
        for row in rows:
            require(clock() < deadline, 'stream-deadline')
            frame.case(row)
        require(producer_complete() is True, 'stream-producer')
        frame.finish(); sink.finish()
        cipher = store.seal_ciphertext()
        require(clock() < deadline, 'stream-deadline')
        post = postflight()
        digest(post)
        require(clock() < deadline, 'stream-deadline')
        raw = canonical(dict(schema='heldout-private-completion/1', bindings=binding,
            count=count, ciphertext=cipher, postflight_sha256=post, cleanup=True)) + b'\n'
        store.complete(raw)
        # Only the opaque manifest commitment leaves the private operation.
        return dict(schema='heldout-public-commitment/1', commitment_sha256=sha(raw))
    except BaseException:
        if sink is not None:
            try: sink.abort()
            except BaseException: pass  # Incomplete transaction has no returned commitment.
        raise
    finally:
        store.close()
