"""One-attempt public delivery outbox for the supervised Mac owner route.

This component does not open a network connection, authenticate a Tower, own
native processes, sign, decrypt, admit work or resume after restart. The admitted
owner must allocate one directory/path per attempt and supply independently
authenticated Tower context and acknowledgment identifiers. SQLite durability
settings are not native power-loss, rollback or all-process ownership proof.
"""
from contextlib import contextmanager
from dataclasses import asdict
import base64
import hashlib
import os
from pathlib import Path
import sqlite3
import stat
from threading import RLock

from lightyear_control_tower.decisions import canonical
from .external_signing import (
    MAX_PAYLOAD, SigningBinding, SigningRefused, SigningWindow, _hex, _json,
)

ACK_SCHEMA = "mac-owner-public-ack/1"


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _plain(path, directory=False):
    info = path.lstat()
    if (stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400
            or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
            or (not directory and info.st_nlink != 1)):
        raise SigningRefused("outbox-path-not-owned-plain-file")
    return info.st_dev, info.st_ino


class MacOwnerPublicOutbox:
    """Persist sealed bytes, consume delivery before release, then bind one ack.

    No existing database can be reopened by this API. An uncertain delivery or
    acknowledgment is fail-stop; creating a fresh path to resend the same
    attempt is forbidden by the integrating controller. Delivery release is
    permission to hand exact public bytes to that owner, not proof of a send.
    """

    def __init__(self, path, *, binding, window, attempt_identity_sha256,
                 tower_context_sha256, public_receipt):
        if type(binding) is not SigningBinding or type(window) is not SigningWindow:
            raise SigningRefused("outbox-original-binding-required")
        window.check(binding)
        _hex(attempt_identity_sha256, 64)
        _hex(tower_context_sha256, 64)
        _json(public_receipt, MAX_PAYLOAD)
        self._binding, self._window = binding, window
        self._attempt, self._tower = attempt_identity_sha256, tower_context_sha256
        self._receipt_sha = _sha(public_receipt)
        self._delivery = canonical(dict(
            schema="mac-owner-public-delivery/1", binding=asdict(binding),
            attempt_identity_sha256=attempt_identity_sha256,
            tower_context_sha256=tower_context_sha256,
            receipt_sha256=self._receipt_sha,
            receipt_base64=base64.b64encode(public_receipt).decode()))
        self._delivery_sha = _sha(self._delivery)
        self._path = Path(path).absolute()
        self._parents = {p: _plain(p, True) for p in (self._path.parent, *self._path.parents[1:])}
        for suffix in ("-journal", "-wal", "-shm"):
            if os.path.lexists(str(self._path) + suffix):
                raise SigningRefused("outbox-existing-sidecar")
        self._pid, self._lock = os.getpid(), RLock()
        self._failed, self._closed, self._db = False, False, None
        try:
            fd = os.open(self._path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise SigningRefused("outbox-existing-no-resume") from exc
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        self._identity = _plain(self._path)
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
                raise SigningRefused("outbox-durability-profile")
            self._header = canonical(dict(
                delivery_sha256=self._delivery_sha,
                original_monotonic_deadline=window.monotonic_deadline,
                restart_authorized=False, automatic_resend=False))
            with self._transaction():
                self._db.execute("""CREATE TABLE delivery (
                    id INTEGER PRIMARY KEY CHECK(id=1), header BLOB NOT NULL,
                    payload BLOB NOT NULL, state TEXT NOT NULL, ack BLOB)""")
                self._db.execute("INSERT INTO delivery VALUES (1, ?, ?, 'sealed', NULL)",
                                 (self._header, self._delivery))
            window.check(binding)
        except BaseException:
            self._failed = True
            self.close()
            raise

    @contextmanager
    def _transaction(self):
        self._db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self._db.execute("COMMIT")
        except BaseException:
            if self._db.in_transaction:
                self._db.execute("ROLLBACK")
            raise

    def _check(self, state):
        if self._closed or self._failed or os.getpid() != self._pid:
            raise SigningRefused("outbox-owner-unavailable")
        if (any(_plain(p, True) != identity for p, identity in self._parents.items())
                or _plain(self._path) != self._identity):
            raise SigningRefused("outbox-path-replaced")
        self._window.check(self._binding)
        row = self._db.execute("SELECT header, payload, state, ack FROM delivery WHERE id=1").fetchone()
        if (row is None or row[0] != self._header or row[1] != self._delivery
                or row[2] != state or row[3] is not None):
            raise SigningRefused("outbox-state-or-content-mismatch")

    def release_once(self):
        """Durably consume the sole release before returning exact public bytes.

        A crash between commit and return leaves the attempt consumed. There is
        deliberately no second release, recovery or delivery-success inference.
        """
        with self._lock:
            try:
                self._check("sealed")
                with self._transaction():
                    self._check("sealed")
                    self._db.execute("UPDATE delivery SET state='released' WHERE id=1")
                self._window.check(self._binding)
                return self._delivery
            except BaseException:
                self._failed = True
                raise

    def acknowledge_once(self, ack, *, authenticated_ack_sha256,
                         authenticated_journal_entry_sha256):
        """Bind one already-authenticated acknowledgment to the original bytes.

        Authentication must happen in the trusted Tower transport integration,
        which supplies both identifiers independently of untrusted response
        fields. A matching caller-supplied hash alone is not authentication.
        """
        with self._lock:
            try:
                self._check("released")
                # Consume before parsing: malformed/late/substituted replies cannot retry.
                with self._transaction():
                    self._check("released")
                    self._db.execute("UPDATE delivery SET state='ack-consumed' WHERE id=1")
                _hex(authenticated_ack_sha256, 64)
                _hex(authenticated_journal_entry_sha256, 64)
                value = _json(ack, 8192)
                if _sha(ack) != authenticated_ack_sha256:
                    raise SigningRefused("outbox-unauthenticated-ack-bytes")
                expected = dict(
                    schema=ACK_SCHEMA, attempt_identity_sha256=self._attempt,
                    tower_context_sha256=self._tower,
                    delivery_sha256=self._delivery_sha,
                    receipt_sha256=self._receipt_sha,
                    journal_entry_sha256=authenticated_journal_entry_sha256)
                if value != expected:
                    raise SigningRefused("outbox-ack-binding")
                self._window.check(self._binding)
                with self._transaction():
                    self._check("ack-consumed")
                    self._db.execute("UPDATE delivery SET state='acknowledged', ack=? WHERE id=1",
                                     (ack,))
                self._window.check(self._binding)
                return authenticated_journal_entry_sha256
            except BaseException:
                self._failed = True
                raise

    def close(self):
        with self._lock:
            if not self._closed:
                self._closed = True
                if self._db is not None:
                    self._db.close()
                    self._db = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
