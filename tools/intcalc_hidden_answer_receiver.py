"""One-use H3-A receiver. No identity-path API, Docker client, file writer or candidate.

H3-B supplies the trusted pre-decryption claim/handle broker and the private
consumer. Private frames stay in memory. This module has no executable entry.
"""
import hashlib
import json
import os
import re
import selectors
import stat
import time

from tools import intcalc_heldout_encrypted_stream as writer


class Refused(ValueError):
    pass


def require(test, code):
    if not test:
        raise Refused(code)


def hash_ok(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def shape(value, fields):
    require(type(value) is dict and set(value) == set(fields.split()), 'receive-shape')


def strict(raw, cap):
    require(type(raw) is bytes and len(raw) <= cap, 'receive-limit')
    def pairs(items):
        row = {}
        for name, value in items:
            require(name not in row, 'receive-json')
            row[name] = value
        return row
    def invalid(_):
        raise Refused('receive-json')
    try:
        result = json.loads(raw, object_pairs_hook=pairs, parse_float=invalid, parse_constant=invalid)
        require(writer.canonical(result) == raw, 'receive-canonical')
        return result
    except (ValueError, UnicodeError, RecursionError):
        raise Refused('receive-json') from None


class Pipe:
    """Only a non-inheritable, read-only, anonymous pipe from Howard's broker."""
    def __init__(self, fd):
        import fcntl
        require(os.name == 'posix' and type(fd) is int and fd >= 3
                and not os.get_inheritable(fd) and stat.S_ISFIFO(os.fstat(fd).st_mode)
                and fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY
                and re.fullmatch(r'pipe:\[[0-9]+\]', os.readlink('/proc/self/fd/' + str(fd))),
                'receive-pipe')
        self.fd = fd
        os.set_blocking(fd, False)
        self.selector = selectors.DefaultSelector()
        self.selector.register(fd, selectors.EVENT_READ)

    def read(self, size, end):
        require(0 < size <= 65536 and self.fd is not None, 'receive-pipe')
        while True:
            remaining = end - time.monotonic()
            require(remaining > 0 and self.selector.select(remaining), 'receive-deadline')
            try:
                return os.read(self.fd, size)
            except BlockingIOError:
                continue

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        if self.fd is not None:
            self.selector.close()
            os.close(self.fd)
            self.fd = None


class Frames:
    def __init__(self, pipe, deadline, total_cap):
        self.pipe, self.end, self.cap = pipe, deadline, total_cap
        self.seen = 0
        self.digest = hashlib.sha256()

    def take(self, size):
        require(0 <= size <= writer.CASE_CAP and self.seen + size <= self.cap, 'receive-limit')
        value = bytearray()
        while len(value) < size:
            require(time.monotonic() < self.end, 'receive-deadline')
            left = min(65536, size-len(value))
            data = self.pipe.read(left, self.end)
            require(type(data) is bytes and 0 < len(data) <= left, 'receive-truncated')
            value.extend(data)
        self.seen += size
        return bytes(value)

    def frame(self):
        prefix = self.take(8)
        length = int.from_bytes(prefix, 'big')
        require(0 < length <= writer.CASE_CAP, 'receive-limit')
        raw = self.take(length)
        self.digest.update(prefix)
        self.digest.update(raw)
        return raw


def completion(raw, approval):
    require(type(raw) is bytes and raw.endswith(b'\n') and len(raw) <= 65536
            and writer.sha(raw) == approval['completion_sha256'], 'receive-commitment')
    row = strict(raw[:-1], 65535)
    shape(row, 'schema bindings count ciphertext postflight_sha256 cleanup')
    require(row['schema'] == 'heldout-private-completion/1' and row['cleanup'] is True
            and row['count'] == approval['count'] and type(row['count']) is int
            and hash_ok(row['postflight_sha256']), 'receive-completion')
    shape(row['ciphertext'], 'sha256 bytes')
    ciphertext = row['ciphertext']
    require(hash_ok(ciphertext['sha256']) and type(ciphertext['bytes']) is int
            and 64 <= ciphertext['bytes'] <= writer.CIPHER_CAP, 'receive-ciphertext')
    binding = writer.checked_binding(row['bindings'])
    require(binding == approval['bindings_sha256']
            and row['bindings']['input_commitment_sha256'] == approval['input_sha256']
            and row['bindings']['encryptor_sha256'] == approval['age_sha256'], 'receive-binding')
    return row


def verify_cipher(fd, desc, end):
    """Hash the very fd handed to the decryptor, ahead of invocation, then rewind."""
    require(type(fd) is int and fd >= 3 and not os.get_inheritable(fd), 'receive-ciphertext')
    before = os.fstat(fd)
    require(stat.S_ISREG(before.st_mode) and stat.S_IMODE(before.st_mode) == 0o600
            and before.st_uid == os.getuid() and before.st_nlink == 1
            and before.st_size == desc['bytes'], 'receive-ciphertext')
    os.lseek(fd, 0, os.SEEK_SET)
    digest = hashlib.sha256()
    size = 0
    while True:
        require(time.monotonic() < end, 'receive-deadline')
        block = os.read(fd, min(65536, before.st_size - size + 1))
        if not block:
            break
        if size == 0:
            require(block.startswith(b'age-encryption.org/v1\n'), 'receive-ciphertext')
        size += len(block)
        require(size <= before.st_size, 'receive-ciphertext')
        digest.update(block)
    after = os.fstat(fd)
    require(size == desc['bytes'] and digest.hexdigest() == desc['sha256']
            and (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
            == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns),
            'receive-ciphertext')
    os.lseek(fd, 0, os.SEEK_SET)


def decode(pipe, projection, source_manifest, end):
    count, binding, cap = projection['count'], projection['bindings_sha256'], projection['plaintext_cap']
    frames = Frames(pipe, end, cap)
    header = strict(frames.frame(), 2048)
    require(header == dict(schema='heldout-encrypted-payload/1', binding_sha256=binding, count=count)
            and type(header['count']) is int, 'receive-header')
    # Same sorted JSON as private_payload. Feed case projections incrementally
    # rather than holding a second 512 MiB serialization of the input inventory.
    input_hash = hashlib.sha256(b'{"cases":[')
    inventory, cases = [], []
    for seq in range(count):
        raw = frames.frame()
        row = strict(raw, writer.CASE_CAP)
        require(writer.checked_case(row, seq) == raw, 'receive-case')
        inventory.append(writer.sha(raw))
        case = dict(id=f'HC-{seq+1:03d}', inputs=row['inputs'],
                    processing_date=row['processing_date'], timestamp=row['timestamp'])
        if seq:
            input_hash.update(b',')
        input_hash.update(writer.canonical(case))
        # Hold validated immutable bounded frames. No callback on a prefix.
        cases.append(raw)
    suffix = dict(schema='fresh-heldout-inputs/1', qualified=False, expected_outputs_present=False,
                  named_limit='open-source reference, not mainframe-proven; inputs only, unqualified',
                  source_manifest=source_manifest)
    input_hash.update(b'],' + writer.canonical(suffix)[1:])
    require(input_hash.hexdigest() == projection['input_sha256'], 'receive-input-manifest')
    preceding = frames.digest.hexdigest()
    trailer = strict(frames.frame(), 16384)
    require(trailer == dict(schema='heldout-encrypted-end/1', count=count, cases_sha256=inventory,
                            frames_sha256=preceding) and type(trailer['count']) is int, 'receive-trailer')
    require(time.monotonic() < end and pipe.read(1, end) == b'', 'receive-trailing')
    return cases


class Receiver:
    """Trusted stage-2 caller only. A second attempt refuses even after an early fault."""
    def __init__(self):
        self.used = False

    def receive(self, approval, source_manifest, broker, deadline):
        require(not self.used, 'receive-consumed')
        self.used = True
        shape(approval, 'operation_id stage1_sha256 jar_sha256 completion_sha256 bindings_sha256 '
                        'input_sha256 age_sha256 source_manifest_sha256 count plaintext_cap')
        require(all(hash_ok(value) for k, value in approval.items() if k.endswith('_sha256') or k == 'operation_id')
                and type(approval['count']) is int and 1 <= approval['count'] <= 64
                and type(approval['plaintext_cap']) is int and 0 < approval['plaintext_cap'] <= writer.STREAM_CAP
                and writer.sha(writer.canonical(source_manifest)) == approval['source_manifest_sha256'],
                'receive-approval')
        # H3-B verifies Howard's exact approval, scope, S1 end state and lifetime.
        # Its exclusive, fully synced replay claim is required BEFORE opening
        # completion.json, answers.age, the USB or any other private answer input.
        require(time.monotonic() < deadline, 'receive-deadline')
        claim = broker.claim(approval, deadline)
        require(hash_ok(claim), 'receive-claim')
        try:
            row = completion(broker.read_completion(claim, deadline), approval)
            with broker.open_cipher(claim, deadline) as fd:
                verify_cipher(fd, row['ciphertext'], deadline)
                # The identity path is never an argument to the receiver. The
                # separate trusted custodian starts age and enforces its pin.
                with broker.decrypt(fd, claim, approval['age_sha256'], deadline) as session:
                    with session.pipe() as pipe:
                        cases = decode(pipe, approval, source_manifest, deadline)
                    require(session.join_success(deadline) is True, 'receive-age-exit')
            proof = broker.removal_receipt(claim, deadline)
            shape(proof, 'claim_sha256 operation_id decryptor_exited group_absent handles_closed '
                         'usb_mount_absent howard_removed_usb howard_no_identity_copy codex_absent')
            require(proof['claim_sha256'] == claim and proof['operation_id'] == approval['operation_id']
                    and all(proof[k] is True for k in proof if k not in ('claim_sha256', 'operation_id')),
                    'receive-custody')
            require(time.monotonic() < deadline, 'receive-deadline')
            return PrivateHandoff(cases, claim, writer.sha(writer.canonical(proof)))
        except Refused:
            raise
        except (writer.Refused, OSError, ValueError, KeyError, RuntimeError, TimeoutError):
            raise Refused('receive-fault') from None


class PrivateHandoff:
    """In-process verifier memory only; no serialization or public per-case metadata."""
    def __init__(self, cases, claim, removal):
        self._cases = cases
        self.claim_sha256 = claim
        self.removal_sha256 = removal

    def __reduce__(self):
        raise Refused('receive-private')

    def consume(self, compare):
        require(self._cases is not None, 'receive-consumed')
        rows, self._cases = self._cases, None
        try:
            # H3-B verifies the claim, USB removal and private-operation deadline,
            # never passes expected bytes to its candidate process, and reduces
            # its observation to the authorized aggregate outside this receiver.
            return compare(rows, self.claim_sha256, self.removal_sha256)
        finally:
            rows.clear()
