"""Public request validation and reply formatting for the isolated human tool.

No device imports or private operations. The request/digest/context and current
revocations must arrive through the human's independently authenticated channel.
"""
import base64
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import re
import struct
import time

from lightyear_control_tower.decisions import canonical
from .external_signing import (
    BEGIN, END, MAX_PAYLOAD, SigningBinding, SigningRefused, SigningWindow,
    _hex, _json, _sha, _ssh_public, _string, _time,
    verify_candidate_reply, verify_controller_reply,
)
from .signing_designation import verify_designation
from .signing_key_a import DESIGNATION_ID, require_key_a_designation

REQUEST_LIMIT = 2 * MAX_PAYLOAD
# Conservative ceiling until an attended Mac/PIV interoperability result exists.
MAX_DIRECT_ED25519_BYTES = 1024


def decode(value):
    if type(value) is not str:
        raise SigningRefused("base64-string-required")
    try:
        raw = base64.b64decode(value, validate=True)
        if base64.b64encode(raw).decode() != value:
            raise ValueError()
        return raw
    except (ValueError, UnicodeError) as exc:
        raise SigningRefused("canonical-base64-required") from exc


def checked(raw, expected, maximum):
    if type(raw) is not bytes or not 0 < len(raw) <= maximum or _sha(raw) != _hex(expected, 64):
        raise SigningRefused("independent-packet-digest-mismatch")
    return raw


@dataclass(frozen=True)
class HumanPacket:
    purpose: str
    request_sha256: str
    context_sha256: str
    binding: SigningBinding
    payload: bytes
    material: bytes
    key_sha256: str
    window: SigningWindow
    revocations_expires_at: str

    def check(self):
        self.window.check(self.binding)
        if datetime.now(timezone.utc) >= _time(self.revocations_expires_at):
            raise SigningRefused("revocations-expired")

    def signing_bytes(self):
        if self.purpose == "controller-receipt":
            return self.payload
        return (b"SSHSIG" + _string(b"git") + _string(b"") + _string(b"sha512")
                + _string(hashlib.sha512(self.payload).digest()))

    def reply(self, signature):
        self.check()
        if type(signature) is not bytes or len(signature) != 64:
            raise SigningRefused("hardware-signature-size")
        if self.purpose == "controller-receipt":
            body = _json(self.payload)
            reply = canonical(dict(
                body, content_sha256=_sha(self.payload),
                signature=dict(algorithm="Ed25519", key_id=self.key_sha256,
                               value=base64.b64encode(signature).decode())))
            verify_controller_reply(self.payload, reply, public_key=self.material,
                                    key_sha256=self.key_sha256, binding=self.binding,
                                    window=self.window)
        else:
            blob, _ = _ssh_public(self.material, self.key_sha256)
            binary = (b"SSHSIG" + struct.pack(">I", 1) + _string(blob)
                      + _string(b"git") + _string(b"") + _string(b"sha512")
                      + _string(_string(b"ssh-ed25519") + _string(signature)))
            encoded = base64.b64encode(binary)
            armor = (BEGIN + b"\n" + b"\n".join(encoded[n:n + 70]
                     for n in range(0, len(encoded), 70)) + b"\n" + END)
            headers, message = self.payload.split(b"\n\n", 1)
            reply = headers + b"\ngpgsig " + armor.replace(b"\n", b"\n ") + b"\n\n" + message
            verify_candidate_reply(self.payload, reply, allowed_signers=self.material,
                                   key_sha256=self.key_sha256, binding=self.binding,
                                   window=self.window)
        self.check()
        return reply


def prepare_packet(request, designation, revocations, *, request_sha256,
                   designation_sha256, revocations_sha256, purpose,
                   source_commit, work_order_sha256, context_sha256):
    """Validate all public inputs before any PIN prompt, device access or signing."""
    request = _json(checked(request, request_sha256, REQUEST_LIMIT), REQUEST_LIMIT)
    if (set(request) != {"schema", "context_sha256", "binding", "payload_sha256",
                        "payload_base64", "public_material_base64"}
            or request["schema"] != "external-signing-request/1"
            or request["context_sha256"] != _hex(context_sha256, 64)
            or purpose not in {"controller-receipt", "candidate-commit"}):
        raise SigningRefused("request-schema-context-or-role")
    document = request["binding"]
    if type(document) is not dict:
        raise SigningRefused("request-binding")
    try:
        binding = SigningBinding(source_commit, work_order_sha256, document["run_id"],
                                 document["case_id"], document["attempt"], document["expires_at"])
        key_sha256 = _hex(document["public_key_sha256"], 64)
    except (KeyError, TypeError) as exc:
        raise SigningRefused("request-binding") from exc
    if document != binding.document(purpose, key_sha256):
        raise SigningRefused("request-independent-binding")
    # This is a local upper bound, not a replacement for the controller's
    # original same-process monotonic deadline, which the owner still enforces.
    wall = datetime.now(timezone.utc)
    deadline = time.monotonic() + (_time(binding.expires_at) - wall).total_seconds()
    window = SigningWindow(binding.expires_at, deadline)
    window.check(binding)
    rev = _json(checked(revocations, revocations_sha256, 16384), 16384)
    if (set(rev) != {"schema", "designation_sha256", "issued_at", "expires_at",
                    "revoked_raw_key_sha256"}
            or rev["schema"] != "human-signing-revocations/1"
            or rev["designation_sha256"] != designation_sha256
            or type(rev["revoked_raw_key_sha256"]) is not list
            or not _time(rev["issued_at"]) <= wall < _time(rev["expires_at"])):
        raise SigningRefused("current-revocations-required")
    ids = rev["revoked_raw_key_sha256"]
    for value in ids:
        _hex(value, 64)
    if len(set(ids)) != len(ids):
        raise SigningRefused("duplicate-revocation-id")
    prepared = verify_designation(
        designation, expected_sha256=designation_sha256,
        expected_designation_id=DESIGNATION_ID, binding=binding,
        revoked_raw_key_sha256=frozenset(ids))
    require_key_a_designation(prepared, binding)
    material = (prepared.controller_public_key if purpose == "controller-receipt"
                else prepared.candidate_allowed_signers)
    if decode(request["public_material_base64"]) != material or _sha(material) != key_sha256:
        raise SigningRefused("request-designated-material")
    payload = decode(request["payload_base64"])
    checked(payload, request["payload_sha256"], MAX_PAYLOAD // 2)
    if purpose == "controller-receipt":
        body = _json(payload)
        if (body.get("custody_signing") != document
                or {"signature", "content_sha256"} & body.keys()):
            raise SigningRefused("controller-request-binding")
        if len(payload) > MAX_DIRECT_ED25519_BYTES:
            raise SigningRefused("direct-ed25519-size-not-qualified")
    else:
        if b"\0" in payload or b"\r" in payload:
            raise SigningRefused("candidate-encoding")
        try:
            headers, message = payload.split(b"\n\n", 1)
        except ValueError as exc:
            raise SigningRefused("candidate-structure") from exc
        lines = headers.split(b"\n")
        trailer = b"Custody-Signing: " + canonical(document) + b"\n"
        if (len(lines) != 4 or not re.fullmatch(rb"tree [0-9a-f]{40}", lines[0])
                or not re.fullmatch(rb"parent [0-9a-f]{40}", lines[1])
                or not lines[2].startswith(b"author ")
                or not lines[3].startswith(b"committer ")
                or message.count(b"Custody-Signing:") != 1
                or not message.endswith(b"\n\n" + trailer)):
            raise SigningRefused("candidate-request-binding")
    return HumanPacket(purpose, request_sha256, context_sha256, binding, payload,
                       material, key_sha256, window, rev["expires_at"])
