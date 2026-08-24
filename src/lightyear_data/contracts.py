from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any


SCHEMA_VERSION = "1.0"


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def content_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes({k: v for k, v in payload.items() if k not in {"content_sha256", "signature"}})).hexdigest()


def seal(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    result["content_sha256"] = content_hash(result)
    return result


def sign(payload: dict[str, Any], key: str, signer: str) -> dict[str, Any]:
    if not key:
        raise ValueError("A non-empty data-equivalence signing key is required")
    result = dict(payload)
    result.pop("signature", None)
    result = seal(result)
    result["signature"] = {
        "algorithm": "hmac-sha256",
        "signer": signer,
        "value": hmac.new(key.encode(), canonical_bytes(result), hashlib.sha256).hexdigest(),
    }
    return result


def verify_signature(payload: dict[str, Any], key: str) -> bool:
    signature = payload.get("signature") or {}
    unsigned = dict(payload)
    unsigned.pop("signature", None)
    expected = hmac.new(key.encode(), canonical_bytes(unsigned), hashlib.sha256).hexdigest()
    return signature.get("algorithm") == "hmac-sha256" and hmac.compare_digest(
        str(signature.get("value", "")), expected
    )
