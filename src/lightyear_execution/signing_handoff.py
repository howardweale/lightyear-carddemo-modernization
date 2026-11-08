"""Persistent public signing handoff; no private signer, admission or restart.

Use only in a controller-owned local directory with independently authenticated
designation and attempt state. SQLite transactions make state changes durable
before export/verification; native power-loss, ownership and rollback resistance
still need qualification on the chosen host. Existing databases never resume.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import base64
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import stat
from threading import RLock

from cryptography.hazmat.primitives import serialization

from lightyear_control_tower.decisions import canonical
from .external_signing import (
    MAX_PAYLOAD, MAX_SIGNATURE, SigningBinding, SigningRefused, SigningWindow,
    _hex, _pem, _ssh_public, candidate_message, controller_payload,
    verify_candidate_reply, verify_controller_reply,
)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _plain(path, *, directory=False):
    info = path.lstat()
    if (stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400
            or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
            or (not directory and info.st_nlink != 1)):
        raise SigningRefused("handoff-path-not-owned-plain-file")
    return info.st_dev, info.st_ino


@dataclass(frozen=True)
class VerifiedPublicReply:
    purpose: str
    payload_sha256: str
    reply_sha256: str
    verified_identity: str
    reply: bytes
    # This value never becomes an admission, candidate ref update or P5 verdict.


class PublicSigningHandoff:
    """One live owner, original window, one export and reply per signing role.

    Creating a second database for the same admitted attempt is forbidden by the
    integrating controller, not established by a caller-supplied file path here.
    A lost owner or uncertain operation cannot reopen this database to resume.
    No retry, recovery, key lookup, network or signature creation is implemented.
    """

    def __init__(self, path, *, binding, window, attempt_identity_sha256,
                 designation_sha256, controller_public_key, controller_key_sha256,
                 candidate_allowed_signers, candidate_key_sha256):
        if type(binding) is not SigningBinding or type(window) is not SigningWindow:
            raise SigningRefused("handoff-original-binding-required")
        window.check(binding)
        _hex(attempt_identity_sha256, 64)
        _hex(designation_sha256, 64)
        controller = _pem(controller_public_key, controller_key_sha256)
        _, candidate = _ssh_public(candidate_allowed_signers, candidate_key_sha256)
        public_format = (serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        if controller.public_bytes(*public_format) == candidate.public_bytes(*public_format):
            raise SigningRefused("handoff-distinct-role-keys-required")
        self._path = Path(path).absolute()
        self._parents = {}
        for parent in (self._path.parent, *self._path.parent.parents):
            self._parents[parent] = _plain(parent, directory=True)
        for suffix in ("-journal", "-wal", "-shm"):
            if os.path.lexists(str(self._path) + suffix):
                raise SigningRefused("handoff-existing-sidecar")
        self._binding, self._window = binding, window
        self._keys = {
            "controller-receipt": (controller_public_key, controller_key_sha256),
            "candidate-commit": (candidate_allowed_signers, candidate_key_sha256),
        }
        self._header = canonical(dict(
            schema="external-signing-handoff/1", binding=binding.document(
                "controller-receipt", controller_key_sha256),
            attempt_identity_sha256=attempt_identity_sha256,
            designation_sha256=designation_sha256,
            candidate_key_sha256=candidate_key_sha256,
            original_monotonic_deadline=window.monotonic_deadline,
            restart_authorized=False))
        self._lock, self._pid = RLock(), os.getpid()
        self._failed, self._closed, self._db = False, False, None
        self._sealed = {}
        # Occupancy is permanent, including failed initialization. Never unlink.
        try:
            descriptor = os.open(self._path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise SigningRefused("handoff-already-created-no-resume") from exc
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        self._file_identity = _plain(self._path)
        try:
            self._db = sqlite3.connect(self._path, isolation_level=None,
                                       check_same_thread=False, timeout=0)
            self._db.execute("PRAGMA journal_mode=DELETE")
            self._db.execute("PRAGMA synchronous=EXTRA")
            self._db.execute("PRAGMA fullfsync=ON")
            self._db.execute("PRAGMA trusted_schema=OFF")
            if (self._db.execute("PRAGMA journal_mode").fetchone()[0] != "delete"
                    or self._db.execute("PRAGMA synchronous").fetchone()[0] != 3
                    or self._db.execute("PRAGMA fullfsync").fetchone()[0] != 1):
                raise SigningRefused("handoff-durability-profile")
            with self._transaction():
                self._db.execute("CREATE TABLE context (id INTEGER PRIMARY KEY CHECK(id=1), body BLOB NOT NULL)")
                self._db.execute("INSERT INTO context VALUES(1, ?)", (self._header,))
                self._db.execute("""CREATE TABLE handoffs (
                    purpose TEXT PRIMARY KEY, request BLOB NOT NULL,
                    payload BLOB NOT NULL, status TEXT NOT NULL,
                    reply BLOB, verified_identity TEXT)""")
            window.check(binding)
        except BaseException:
            self._failed = True
            self.close()
            raise

    def _live(self, *, context=True):
        if self._closed or self._failed or os.getpid() != self._pid:
            raise SigningRefused("handoff-owner-unavailable-no-resume")
        if (_plain(self._path) != self._file_identity or
                any(_plain(parent, directory=True) != identity
                    for parent, identity in self._parents.items())):
            raise SigningRefused("handoff-path-replaced")
        if context:
            row = self._db.execute("SELECT body FROM context WHERE id=1").fetchone()
            if row != (self._header,):
                raise SigningRefused("handoff-context-drift")

    def _commit(self):
        self._db.execute("COMMIT")

    @contextmanager
    def _transaction(self):
        # The object lock spans this transaction AND any following verification.
        try:
            self._live(context=False)
            self._db.execute("BEGIN IMMEDIATE")
            yield
            self._commit()
            self._live(context=False)
        except BaseException:
            self._failed = True
            try:
                self._db.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise

    def _seal(self, purpose, payload):
        self._live()
        self._window.check(self._binding)
        material, key_hash = self._keys[purpose]
        request = canonical(dict(
            schema="external-signing-request/1",
            context_sha256=_sha(self._header),
            binding=self._binding.document(purpose, key_hash),
            payload_sha256=_sha(payload),
            payload_base64=base64.b64encode(payload).decode(),
            public_material_base64=base64.b64encode(material).decode()))
        with self._transaction():
            if self._db.execute("SELECT 1 FROM handoffs WHERE purpose=?", (purpose,)).fetchone():
                raise SigningRefused("handoff-export-already-consumed")
            self._db.execute("INSERT INTO handoffs VALUES (?, ?, ?, 'EXPORTED', NULL, NULL)",
                             (purpose, request, payload))
        self._sealed[purpose] = (request, payload)
        # A post-commit timeout loses the export; it cannot be retried.
        self._window.check(self._binding)
        return request

    def request_controller(self, unsigned_public_body):
        with self._lock:
            try:
                payload = controller_payload(unsigned_public_body, self._binding,
                                             self._keys["controller-receipt"][1])
                return self._seal("controller-receipt", payload)
            except BaseException:
                self._failed = True
                raise

    def request_candidate(self, unsigned_commit):
        with self._lock:
            try:
                if (type(unsigned_commit) is not bytes or
                        not 0 < len(unsigned_commit) <= MAX_PAYLOAD // 2 or
                        b"\0" in unsigned_commit or b"\r" in unsigned_commit):
                    raise SigningRefused("handoff-candidate-size")
                try:
                    headers, message = unsigned_commit.split(b"\n\n", 1)
                except ValueError as exc:
                    raise SigningRefused("handoff-candidate-structure") from exc
                lines = headers.split(b"\n")
                if (len(lines) != 4 or not re.fullmatch(rb"tree [0-9a-f]{40}", lines[0])
                        or not re.fullmatch(rb"parent [0-9a-f]{40}", lines[1])
                        or not lines[2].startswith(b"author ") or not lines[3].startswith(b"committer ")):
                    raise SigningRefused("handoff-candidate-headers")
                payload = headers + b"\n\n" + candidate_message(
                    message, self._binding, self._keys["candidate-commit"][1])
                return self._seal("candidate-commit", payload)
            except BaseException:
                self._failed = True
                raise

    def _accept(self, purpose, reply):
        with self._lock:
            try:
                self._live()
                expected = self._sealed.get(purpose)
                if expected is None:
                    raise SigningRefused("handoff-no-retained-request")
                with self._transaction():
                    row = self._db.execute(
                        "SELECT request, payload, status FROM handoffs WHERE purpose=?", (purpose,)).fetchone()
                    if row != (*expected, "EXPORTED"):
                        raise SigningRefused("handoff-consumed-or-request-drift")
                    self._db.execute("UPDATE handoffs SET status='CONSUMED' WHERE purpose=?", (purpose,))
                # Consume durably before parsing or verifying even a bad/late reply.
                if type(reply) is not bytes or not 0 < len(reply) <= MAX_PAYLOAD + MAX_SIGNATURE:
                    raise SigningRefused("handoff-reply-size")
                self._window.check(self._binding)
                material, key_hash = self._keys[purpose]
                options = dict(key_sha256=key_hash, binding=self._binding, window=self._window)
                payload = expected[1]
                if purpose == "controller-receipt":
                    identity = verify_controller_reply(payload, reply, public_key=material, **options)
                else:
                    identity = verify_candidate_reply(payload, reply, allowed_signers=material, **options)
                self._live()
                with self._transaction():
                    row = self._db.execute(
                        "SELECT request, payload, status FROM handoffs WHERE purpose=?", (purpose,)).fetchone()
                    if row != (*expected, "CONSUMED"):
                        raise SigningRefused("handoff-state-drift-during-verification")
                    self._db.execute(
                        "UPDATE handoffs SET status='SIGNATURE_VERIFIED', reply=?, verified_identity=? WHERE purpose=?",
                        (reply, identity, purpose))
                # SIGNATURE_VERIFIED records crypto validity, not timely delivery/GO.
                self._window.check(self._binding)
                return VerifiedPublicReply(purpose, _sha(payload), _sha(reply), identity, reply)
            except BaseException:
                self._failed = True
                raise

    def accept_controller(self, reply):
        return self._accept("controller-receipt", reply)

    def accept_candidate(self, signed_commit):
        return self._accept("candidate-commit", signed_commit)

    def close(self):
        with self._lock:
            self._closed = True
            if self._db is not None:
                self._db.close()
                self._db = None
