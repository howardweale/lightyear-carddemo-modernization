from __future__ import annotations

import base64
import hashlib
import json
from typing import Any, Mapping


SHA256_DIGEST_INFO_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")


def canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def rsa_pkcs1v15_sha256_sign(payload: Mapping[str, Any], modulus_hex: str, private_exponent_hex: str) -> str:
    modulus = int(modulus_hex, 16)
    private_exponent = int(private_exponent_hex, 16)
    size = (modulus.bit_length() + 7) // 8
    digest_info = SHA256_DIGEST_INFO_PREFIX + hashlib.sha256(canonical_bytes(payload)).digest()
    padding = b"\xff" * (size - len(digest_info) - 3)
    encoded = b"\x00\x01" + padding + b"\x00" + digest_info
    signature = pow(int.from_bytes(encoded, "big"), private_exponent, modulus)
    return base64.b64encode(signature.to_bytes(size, "big")).decode("ascii")


def rsa_pkcs1v15_sha256_verify(
    payload: Mapping[str, Any], signature_b64: str, modulus_hex: str, public_exponent: int
) -> bool:
    try:
        modulus = int(modulus_hex, 16)
        signature = base64.b64decode(signature_b64, validate=True)
    except (ValueError, TypeError):
        return False
    size = (modulus.bit_length() + 7) // 8
    if len(signature) != size:
        return False
    decoded = pow(int.from_bytes(signature, "big"), public_exponent, modulus).to_bytes(size, "big")
    digest_info = SHA256_DIGEST_INFO_PREFIX + hashlib.sha256(canonical_bytes(payload)).digest()
    expected_padding = size - len(digest_info) - 3
    return expected_padding >= 8 and decoded == b"\x00\x01" + b"\xff" * expected_padding + b"\x00" + digest_info
