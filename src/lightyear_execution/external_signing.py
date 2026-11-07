"""Public-only verification for the isolated human signing handoff.

This module has no signer, key loader, transport, admission or native capability.
The admitted controller must retain the exact request in its durable one-attempt
journal. Reconstructing a request from a returned packet is not verification.
Passing these checks proves signatures and bindings, not controller provenance,
process ownership, qualification, or permission to advance an attempt.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import re
import struct
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from lightyear_control_tower.decisions import canonical

MAX_PAYLOAD = 1024 * 1024
MAX_SIGNATURE = 4096
PRINCIPAL = "factory@lightyear.invalid"
BEGIN = b"-----BEGIN SSH SIGNATURE-----"
END = b"-----END SSH SIGNATURE-----"


class SigningRefused(ValueError):
    """Public handoff is invalid, mismatched, or outside its original window."""


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _hex(value: str, size: int) -> str:
    if type(value) is not str or not re.fullmatch(r"[0-9a-f]{%d}" % size, value):
        raise SigningRefused("invalid-binding-digest")
    return value


def _time(value: str) -> datetime:
    if type(value) is not str or not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})", value):
        raise SigningRefused("offset-timestamp-required")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SigningRefused("invalid-timestamp") from exc


def _json(raw: bytes, maximum: int = MAX_PAYLOAD) -> dict:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise SigningRefused("duplicate-json-key")
            result[key] = value
        return result

    if type(raw) is not bytes or not 0 < len(raw) <= maximum:
        raise SigningRefused("public-packet-size")
    try:
        value = json.loads(raw, object_pairs_hook=pairs)
        if type(value) is not dict or canonical(value) != raw:
            raise SigningRefused("canonical-object-required")
        return value
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise SigningRefused("invalid-canonical-json") from exc


@dataclass(frozen=True)
class SigningBinding:
    """Expected values supplied by admitted controller state, never the reply."""

    source_commit: str
    work_order_sha256: str
    run_id: str
    case_id: str
    attempt: int
    expires_at: str

    def __post_init__(self):
        _hex(self.source_commit, 40)
        _hex(self.work_order_sha256, 64)
        for value in (self.run_id, self.case_id):
            if type(value) is not str or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", value):
                raise SigningRefused("invalid-case-or-run")
        if type(self.attempt) is not int or not 1 <= self.attempt <= 2147483647:
            raise SigningRefused("invalid-attempt")
        _time(self.expires_at)

    def document(self, purpose: str, key_sha256: str) -> dict:
        if purpose not in {"controller-receipt", "candidate-commit"}:
            raise SigningRefused("unsupported-signing-purpose")
        return dict(schema="external-custody-signing/1", purpose=purpose,
                    source_commit=self.source_commit, work_order_sha256=self.work_order_sha256,
                    run_id=self.run_id, case_id=self.case_id, attempt=self.attempt,
                    expires_at=self.expires_at, public_key_sha256=_hex(key_sha256, 64))


@dataclass(frozen=True)
class SigningWindow:
    """Original wall deadline AND original same-process monotonic deadline.

    The owner supplies both when the case is admitted, not when a signature is
    requested. Do not rebase this object on resume, restart, or human handoff.
    Clock injection is for CI; production uses the process clocks below.
    """

    expires_at: str
    monotonic_deadline: float

    def __post_init__(self):
        _time(self.expires_at)
        if (type(self.monotonic_deadline) not in (int, float)
                or not math.isfinite(self.monotonic_deadline)):
            raise SigningRefused("finite-original-deadline-required")

    def check(self, binding: SigningBinding, *, wall=None, monotonic=None):
        wall = datetime.now(timezone.utc) if wall is None else wall
        monotonic = time.monotonic() if monotonic is None else monotonic
        if (binding.expires_at != self.expires_at or not isinstance(wall, datetime)
                or wall.tzinfo is None or wall.utcoffset() is None
                or type(monotonic) not in (int, float) or not math.isfinite(monotonic)
                or wall >= _time(self.expires_at) or monotonic >= self.monotonic_deadline):
            raise SigningRefused("original-signing-window-closed")


def _pem(raw: bytes, expected_sha256: str) -> Ed25519PublicKey:
    if type(raw) is not bytes or len(raw) > 1024 or _sha(raw) != _hex(expected_sha256, 64):
        raise SigningRefused("designated-public-key-mismatch")
    try:
        key = serialization.load_pem_public_key(raw)
        if (not isinstance(key, Ed25519PublicKey)
                or key.public_bytes(serialization.Encoding.PEM,
                                    serialization.PublicFormat.SubjectPublicKeyInfo) != raw):
            raise SigningRefused("canonical-ed25519-public-pem-required")
        return key
    except (ValueError, TypeError) as exc:
        raise SigningRefused("invalid-public-pem") from exc


def controller_payload(body: bytes, binding: SigningBinding, key_sha256: str) -> bytes:
    """Bind exact controller body before sealing/journaling and external signing.

    The extra field must be integrated into the final controller schema before
    qualification. This helper does not mark disposable evidence as production.
    """
    value = _json(body)
    if {"signature", "content_sha256", "custody_signing"} & value.keys():
        raise SigningRefused("controller-body-already-wrapped")
    value["custody_signing"] = binding.document("controller-receipt", key_sha256)
    result = canonical(value)
    if len(result) > MAX_PAYLOAD:
        raise SigningRefused("public-packet-size")
    return result


def verify_controller_reply(expected_payload: bytes, reply: bytes, *, public_key: bytes,
                            key_sha256: str, binding: SigningBinding,
                            window: SigningWindow) -> str:
    """Verify the existing Ed25519 envelope format against retained exact bytes.

    Returns only the payload digest. It does not confer admission or P5 success.
    The public key and its designated digest come from independent trusted state.
    """
    window.check(binding)
    key = _pem(public_key, key_sha256)
    expected = _json(expected_payload)
    if (canonical(expected.get("custody_signing")) != canonical(binding.document("controller-receipt", key_sha256))
            or {"signature", "content_sha256"} & expected.keys()):
        raise SigningRefused("controller-request-binding")
    envelope = _json(reply, MAX_PAYLOAD + MAX_SIGNATURE)
    if set(envelope) != set(expected) | {"signature", "content_sha256"}:
        raise SigningRefused("controller-reply-fields")
    body = {k: v for k, v in envelope.items() if k not in {"signature", "content_sha256"}}
    if canonical(body) != expected_payload or envelope["content_sha256"] != _sha(expected_payload):
        raise SigningRefused("controller-payload-substitution")
    signature = envelope["signature"]
    if (type(signature) is not dict or set(signature) != {"algorithm", "key_id", "value"}
            or signature["algorithm"] != "Ed25519" or signature["key_id"] != key_sha256
            or type(signature["value"]) is not str or len(signature["value"]) != 88):
        raise SigningRefused("controller-signature-format")
    try:
        raw = base64.b64decode(signature["value"], validate=True)
        if len(raw) != 64 or base64.b64encode(raw).decode() != signature["value"]:
            raise SigningRefused("controller-signature-format")
        key.verify(raw, expected_payload)
    except (ValueError, InvalidSignature) as exc:
        raise SigningRefused("controller-signature-invalid") from exc
    window.check(binding)
    return _sha(expected_payload)


def candidate_message(message: bytes, binding: SigningBinding, key_sha256: str) -> bytes:
    """Add the complete binding as one canonical trailer before commit sealing."""
    if (type(message) is not bytes or not message or len(message) > MAX_PAYLOAD // 2
            or b"\0" in message or b"\r" in message or b"Custody-Signing:" in message):
        raise SigningRefused("candidate-message-format")
    trailer = canonical(binding.document("candidate-commit", key_sha256))
    return message.rstrip(b"\n") + b"\n\nCustody-Signing: " + trailer + b"\n"


class _Reader:
    def __init__(self, raw):
        self.raw, self.pos = raw, 0

    def take(self, length):
        if length < 0 or length > len(self.raw) - self.pos:
            raise SigningRefused("truncated-ssh-signature")
        result = self.raw[self.pos:self.pos + length]
        self.pos += length
        return result

    def uint(self):
        return struct.unpack(">I", self.take(4))[0]

    def string(self):
        return self.take(self.uint())

    def end(self):
        if self.pos != len(self.raw):
            raise SigningRefused("trailing-ssh-data")


def _string(raw):
    return struct.pack(">I", len(raw)) + raw


def _ssh_public(allowed_signers: bytes, key_sha256: str):
    if (type(allowed_signers) is not bytes or len(allowed_signers) > 1024
            or _sha(allowed_signers) != _hex(key_sha256, 64)):
        raise SigningRefused("designated-allowed-signers-mismatch")
    pattern = re.escape(PRINCIPAL.encode()) + rb" ssh-ed25519 ([A-Za-z0-9+/]+={0,2})\n"
    match = re.fullmatch(pattern, allowed_signers)
    if match is None:
        raise SigningRefused("single-factory-ed25519-signer-required")
    try:
        blob = base64.b64decode(match[1], validate=True)
        if base64.b64encode(blob) != match[1]:
            raise SigningRefused("noncanonical-ssh-public-key")
        reader = _Reader(blob)
        if reader.string() != b"ssh-ed25519":
            raise SigningRefused("ed25519-required")
        key = Ed25519PublicKey.from_public_bytes(reader.string())
        reader.end()
        return blob, key
    except ValueError as exc:
        raise SigningRefused("invalid-ssh-public-key") from exc


def _verify_sshsig(payload, armor, public_blob, key):
    if (len(armor) > MAX_SIGNATURE or b"\r" in armor
            or not armor.startswith(BEGIN + b"\n") or not armor.endswith(b"\n" + END + b"\n")):
        raise SigningRefused("ssh-armor-format")
    lines = armor.split(b"\n")[1:-2]
    if not lines or any(not line or len(line) > 76 for line in lines):
        raise SigningRefused("ssh-armor-lines")
    try:
        encoded = b"".join(lines)
        blob = base64.b64decode(encoded, validate=True)
        if base64.b64encode(blob) != encoded:
            raise SigningRefused("ssh-armor-base64")
        reader = _Reader(blob)
        if reader.take(6) != b"SSHSIG" or reader.uint() != 1 or reader.string() != public_blob:
            raise SigningRefused("ssh-signature-key-or-version")
        namespace, reserved, algorithm = reader.string(), reader.string(), reader.string()
        if namespace != b"git" or reserved != b"" or algorithm not in (b"sha256", b"sha512"):
            raise SigningRefused("ssh-signature-domain")
        signature = _Reader(reader.string())
        reader.end()
        if signature.string() != b"ssh-ed25519":
            raise SigningRefused("ssh-signature-algorithm")
        raw = signature.string()
        signature.end()
        if len(raw) != 64:
            raise SigningRefused("ssh-signature-length")
        signed = (b"SSHSIG" + _string(namespace) + _string(reserved) + _string(algorithm)
                  + _string(hashlib.new(algorithm.decode(), payload).digest()))
        key.verify(raw, signed)
    except (ValueError, InvalidSignature) as exc:
        raise SigningRefused("candidate-signature-invalid") from exc


def verify_candidate_reply(expected_payload: bytes, signed_commit: bytes, *,
                           allowed_signers: bytes, key_sha256: str,
                           binding: SigningBinding, window: SigningWindow) -> str:
    """Verify a Git commit returned by the human, with no git/SSH subprocess.

    The trusted caller retains the exact unsigned commit object bytes, including
    tree, single parent, authorship, provenance and custody trailer. Nothing is
    written into a repository here. Return value is the verified SHA-1 object ID
    for this repository's current object format, not a permission to update refs.
    """
    window.check(binding)
    public_blob, key = _ssh_public(allowed_signers, key_sha256)
    for raw in (expected_payload, signed_commit):
        if type(raw) is not bytes or not 0 < len(raw) <= MAX_PAYLOAD or b"\0" in raw or b"\r" in raw:
            raise SigningRefused("candidate-commit-size-or-encoding")
    try:
        headers, message = expected_payload.split(b"\n\n", 1)
        signed_headers, signed_message = signed_commit.split(b"\n\n", 1)
    except ValueError as exc:
        raise SigningRefused("candidate-commit-structure") from exc
    lines = headers.split(b"\n")
    # This narrow profile excludes merge commits, extra headers and signatures
    # in the request; such formats require a separately reviewed implementation.
    if (len(lines) != 4 or not re.fullmatch(rb"tree [0-9a-f]{40}", lines[0])
            or not re.fullmatch(rb"parent [0-9a-f]{40}", lines[1])
            or not lines[2].startswith(b"author ") or not lines[3].startswith(b"committer ")):
        raise SigningRefused("candidate-commit-headers")
    trailer = b"Custody-Signing: " + canonical(binding.document("candidate-commit", key_sha256)) + b"\n"
    if message.count(b"Custody-Signing:") != 1 or not message.endswith(b"\n\n" + trailer):
        raise SigningRefused("candidate-custody-binding")
    retained, armor, in_signature = [], [], False
    for line in signed_headers.split(b"\n"):
        if line.startswith(b"gpgsig "):
            if armor:
                raise SigningRefused("duplicate-git-signature")
            in_signature = True
            armor.append(line[7:])
        elif line.startswith(b" "):
            if not in_signature:
                raise SigningRefused("unexpected-git-continuation")
            armor.append(line[1:])
        else:
            in_signature = False
            retained.append(line)
    if b"\n".join(retained) + b"\n\n" + signed_message != expected_payload:
        raise SigningRefused("candidate-payload-substitution")
    _verify_sshsig(expected_payload, b"\n".join(armor) + b"\n", public_blob, key)
    window.check(binding)
    return hashlib.sha1(b"commit " + str(len(signed_commit)).encode() + b"\0" + signed_commit).hexdigest()
