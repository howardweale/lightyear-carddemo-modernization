"""Ed25519 envelopes compatible with Tower canonical JSON; no private-key files.

The transport is injected: production callers supply an authenticated KMS REST
transport obtained through workload identity, never a service-account key file.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
from typing import Callable, Protocol

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def seal(value: object) -> str:
    return sha256(canonical(value))


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def crc32c(data: bytes) -> int:
    """Castagnoli checksum, independent of optional native CRC packages."""
    crc = 0xFFFFFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0x82F63B78 if crc & 1 else 0)
    return crc ^ 0xFFFFFFFF


def public_key(pem: str) -> Ed25519PublicKey:
    key = serialization.load_pem_public_key(pem.encode())
    require(isinstance(key, Ed25519PublicKey), "Only Ed25519 public keys are admitted")
    return key


def verify(envelope: dict, trusted_pem: str) -> dict:
    """Trust comes from operator-controlled policy, never the envelope itself."""
    require(set(envelope) == {"body", "content_sha256", "signature"}, "Envelope fields differ")
    body = envelope["body"]
    require(seal(body) == envelope["content_sha256"], "Envelope content hash differs")
    signature = envelope["signature"]
    require(set(signature) == {"algorithm", "key_id", "value"}, "Signature fields differ")
    require(signature["algorithm"] == "Ed25519", "Signature algorithm differs")
    require(signature["key_id"] == sha256(trusted_pem.encode()), "Untrusted signing key")
    public_key(trusted_pem).verify(base64.b64decode(signature["value"], validate=True), canonical(body))
    return body


class Signer(Protocol):
    def sign(self, body: dict) -> dict: ...


class GcpKmsSigner:
    """PureEdDSA: send raw canonical bytes, NOT a SHA-256 digest to KMS.

    Supply a pinned public PEM and numeric CryptoKeyVersion. Verify both the KMS
    transport checksums and the resulting signature. No retries are implicit.
    """
    def __init__(self, version: str, scope: str, trusted_pem: str,
                 post: Callable[[str, dict], dict]):
        require(bool(re.fullmatch(
            r"projects/[^/]+/locations/[^/]+/keyRings/[^/]+/cryptoKeys/[^/]+/cryptoKeyVersions/[1-9][0-9]*",
            version)), "A specific KMS key version is required")
        require(scope in {"engineering", "qualification", "factory"}, "Unknown key scope")
        self.version, self.scope, self.pem, self.post = version, scope, trusted_pem, post
        self.public = public_key(trusted_pem)

    def sign(self, body: dict) -> dict:
        require(body.get("scope") == self.scope, "Cross-scope signing refused")
        require(body.get("purpose") in {"cloud-run-go", "cloud-memory-witness", "cloud-run-ledger"},
                "Unknown signing purpose")
        data = canonical(body)
        require(len(data) <= 65536, "KMS message exceeds the bounded signing size")
        response = self.post(
            "https://cloudkms.googleapis.com/v1/" + self.version + ":asymmetricSign",
            {"data": base64.b64encode(data).decode(), "dataCrc32c": str(crc32c(data))})
        require(response.get("name") == self.version, "KMS key version differs")
        require(response.get("protectionLevel") == "SOFTWARE", "KMS protection level differs")
        require(response.get("verifiedDataCrc32c") is True, "KMS did not verify request checksum")
        signature = base64.b64decode(response["signature"], validate=True)
        require(len(signature) == 64, "Invalid Ed25519 signature length")
        require(str(crc32c(signature)) == str(response.get("signatureCrc32c")),
                "KMS response checksum differs")
        self.public.verify(signature, data)
        return {"body": body, "content_sha256": seal(body),
                "signature": {"algorithm": "Ed25519", "key_id": sha256(self.pem.encode()),
                              "value": base64.b64encode(signature).decode()}}
