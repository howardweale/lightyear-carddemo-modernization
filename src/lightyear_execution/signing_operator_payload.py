"""Public payloads for the future attended signing command; no private operations.

Inputs must come from independently authenticated, retained handoff state.
Preparing bytes is not authorization to sign. This module neither accesses PIV
nor supplies PINs, creates signatures, persists attempts, admits or updates refs.
The integrating human command must enforce its one-attempt journal and original
window; hardware compatibility and per-operation touch need separate evidence.
"""
import base64
from dataclasses import dataclass
import hashlib
import re
import struct

from lightyear_control_tower.decisions import canonical
from .external_signing import (
    BEGIN, END, MAX_PAYLOAD, MAX_SIGNATURE, SigningBinding, SigningRefused,
    SigningWindow, _hex, _json, _pem, _ssh_public,
    verify_candidate_reply, verify_controller_reply,
)

SLOTS = {"controller-receipt": "9c", "candidate-commit": "9a"}
MAX_REQUEST = 2 * MAX_PAYLOAD + 8192


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _string(raw):
    return struct.pack(">I", len(raw)) + raw


def _decode(value, maximum):
    if type(value) is not str or not 0 < len(value) <= 4 * ((maximum + 2) // 3):
        raise SigningRefused("operator-base64-size")
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, UnicodeError) as exc:
        raise SigningRefused("operator-base64-format") from exc
    if not 0 < len(raw) <= maximum or base64.b64encode(raw).decode() != value:
        raise SigningRefused("operator-base64-canonical")
    return raw


def _candidate(payload, binding_document):
    if (len(payload) > MAX_PAYLOAD - MAX_SIGNATURE
            or b"\0" in payload or b"\r" in payload):
        raise SigningRefused("operator-candidate-size-or-encoding")
    try:
        headers, message = payload.split(b"\n\n", 1)
    except ValueError as exc:
        raise SigningRefused("operator-candidate-structure") from exc
    lines = headers.split(b"\n")
    if (len(lines) != 4 or not re.fullmatch(rb"tree [0-9a-f]{40}", lines[0])
            or not re.fullmatch(rb"parent [0-9a-f]{40}", lines[1])
            or not lines[2].startswith(b"author ") or not lines[3].startswith(b"committer ")):
        raise SigningRefused("operator-candidate-headers")
    trailer = b"Custody-Signing: " + canonical(binding_document) + b"\n"
    if message.count(b"Custody-Signing:") != 1 or not message.endswith(b"\n\n" + trailer):
        raise SigningRefused("operator-candidate-binding")
    return headers, message


@dataclass(frozen=True)
class OperatorPayload:
    """Immutable public data; slot labels are intentions, not device attestation."""

    request: bytes
    request_sha256: str
    context_sha256: str
    purpose: str
    public_material: bytes
    binding: SigningBinding
    window: SigningWindow
    payload: bytes
    message_to_sign: bytes
    piv_slot: str


def prepare_operator_payload(request, *, expected_request_sha256,
                             expected_context_sha256, expected_purpose,
                             designated_public_material, binding, window):
    """Validate a retained request and produce raw Ed25519 signing input.

    For candidate commits the raw signing input is SSHSIG domain-separated with
    namespace git and SHA512. For controller receipts it is the exact canonical
    payload. No hashing substitution or domain choice is delegated to a signer.
    The request/context digests and designation must NOT be taken from the
    received packet itself; the caller supplies its independently retained state.
    """
    if type(binding) is not SigningBinding or type(window) is not SigningWindow:
        raise SigningRefused("operator-original-window-required")
    window.check(binding)
    if type(expected_purpose) is not str or expected_purpose not in SLOTS:
        raise SigningRefused("operator-purpose")
    _hex(expected_context_sha256, 64)
    if (type(request) is not bytes or len(request) > MAX_REQUEST
            or _sha(request) != _hex(expected_request_sha256, 64)):
        raise SigningRefused("operator-retained-request-mismatch")
    if type(designated_public_material) is not bytes or len(designated_public_material) > 1024:
        raise SigningRefused("operator-designated-public-material")
    value = _json(request, MAX_REQUEST)
    if (set(value) != {"schema", "context_sha256", "binding", "payload_sha256",
                       "payload_base64", "public_material_base64"}
            or value["schema"] != "external-signing-request/1"
            or value["context_sha256"] != expected_context_sha256):
        raise SigningRefused("operator-request-context")
    material = _decode(value["public_material_base64"], 1024)
    if material != designated_public_material:
        raise SigningRefused("operator-role-key-substitution")
    key_sha = _sha(material)
    expected_binding = binding.document(expected_purpose, key_sha)
    if canonical(value["binding"]) != canonical(expected_binding):
        raise SigningRefused("operator-request-binding")
    payload = _decode(value["payload_base64"], MAX_PAYLOAD)
    if _sha(payload) != _hex(value["payload_sha256"], 64):
        raise SigningRefused("operator-payload-digest")
    if expected_purpose == "controller-receipt":
        _pem(material, key_sha)
        body = _json(payload)
        if (canonical(body.get("custody_signing")) != canonical(expected_binding)
                or {"signature", "content_sha256"} & body.keys()):
            raise SigningRefused("operator-controller-binding")
        signing_input = payload
    else:
        _ssh_public(material, key_sha)
        _candidate(payload, expected_binding)
        signing_input = (b"SSHSIG" + _string(b"git") + _string(b"")
                         + _string(b"sha512") + _string(hashlib.sha512(payload).digest()))
    window.check(binding)
    return OperatorPayload(request, expected_request_sha256, expected_context_sha256,
                           expected_purpose, material, binding, window, payload,
                           signing_input, SLOTS[expected_purpose])


def assemble_operator_reply(prepared, raw_signature):
    """Assemble and publicly verify an externally supplied Ed25519 signature.

    No private signing operation happens here. Invalid/late signatures return no
    reply. Persistent one-shot consumption remains the handoff owner's duty.
    """
    if type(prepared) is not OperatorPayload:
        raise SigningRefused("operator-prepared-payload-required")
    checked = prepare_operator_payload(
        prepared.request, expected_request_sha256=prepared.request_sha256,
        expected_context_sha256=prepared.context_sha256, expected_purpose=prepared.purpose,
        designated_public_material=prepared.public_material,
        binding=prepared.binding, window=prepared.window)
    if checked != prepared:
        raise SigningRefused("operator-prepared-payload-drift")
    if type(raw_signature) is not bytes or len(raw_signature) != 64:
        raise SigningRefused("operator-ed25519-signature-length")
    key_sha = _sha(checked.public_material)
    options = dict(key_sha256=key_sha, binding=checked.binding, window=checked.window)
    if checked.purpose == "controller-receipt":
        body = _json(checked.payload)
        reply = canonical(dict(
            body, content_sha256=_sha(checked.payload),
            signature=dict(algorithm="Ed25519", key_id=key_sha,
                           value=base64.b64encode(raw_signature).decode())))
        verify_controller_reply(checked.payload, reply, public_key=checked.public_material, **options)
    else:
        public_blob, _ = _ssh_public(checked.public_material, key_sha)
        signature_blob = _string(b"ssh-ed25519") + _string(raw_signature)
        signature_file = (b"SSHSIG" + struct.pack(">I", 1) + _string(public_blob)
                          + _string(b"git") + _string(b"") + _string(b"sha512")
                          + _string(signature_blob))
        encoded = base64.b64encode(signature_file)
        armor = [BEGIN] + [encoded[i:i + 70] for i in range(0, len(encoded), 70)] + [END]
        header = b"gpgsig " + armor[0] + b"\n" + b"\n".join(b" " + line for line in armor[1:])
        headers, message = _candidate(checked.payload, checked.binding.document(checked.purpose, key_sha))
        reply = headers + b"\n" + header + b"\n\n" + message
        verify_candidate_reply(checked.payload, reply, allowed_signers=checked.public_material, **options)
    checked.window.check(checked.binding)
    return reply
