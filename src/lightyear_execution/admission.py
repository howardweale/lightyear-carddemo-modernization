from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import timedelta
from pathlib import Path
from typing import Any

from lightyear_factory.contracts import WorkOrder

from .contracts import (
    EXECUTION_SCHEMA_VERSION,
    ExecutionContractError,
    ExecutionPolicy,
    canonical_hash,
    parse_timestamp,
    safe_name,
)


def sign_work_order(
    order: WorkOrder,
    policy: ExecutionPolicy,
    issuer_id: str,
    key_id: str,
    signing_key: bytes,
    issued_at: str,
    expires_at: str,
    nonce: str,
) -> dict[str, Any]:
    _validate_key(signing_key)
    issued = parse_timestamp(issued_at)
    expiry = parse_timestamp(expires_at)
    ttl = (expiry - issued).total_seconds()
    if ttl <= 0 or ttl > policy.max_work_order_ttl_seconds:
        raise ExecutionContractError("Signed work-order TTL violates admission policy")
    if key_id not in policy.trusted_key_ids:
        raise ExecutionContractError("Signing key id is not trusted by execution policy")
    envelope: dict[str, Any] = {
        "schema_version": EXECUTION_SCHEMA_VERSION,
        "envelope_type": "lightyear-signed-work-order",
        "issuer": {"id": safe_name(issuer_id, "issuer id"), "key_id": key_id},
        "issued_at": issued_at,
        "expires_at": expires_at,
        "nonce": safe_name(nonce, "admission nonce"),
        "execution_policy_sha256": policy.content_sha256,
        "work_order": order.to_dict(),
        "work_order_sha256": order.content_sha256,
        "signature": {"algorithm": "HMAC-SHA256", "key_id": key_id, "value": None},
    }
    envelope["signature"]["value"] = hmac.new(
        signing_key, canonical_hash(envelope).encode("ascii"), hashlib.sha256
    ).hexdigest()
    envelope["content_sha256"] = canonical_hash(envelope)
    return envelope


def verify_work_order(
    envelope: dict[str, Any],
    policy: ExecutionPolicy,
    trusted_keys: dict[str, bytes],
    now: str,
    nonce_store: "AdmissionNonceStore | None" = None,
) -> tuple[WorkOrder, dict[str, Any]]:
    if envelope.get("schema_version") != EXECUTION_SCHEMA_VERSION:
        raise ExecutionContractError("Unsupported signed work-order schema")
    if envelope.get("envelope_type") != "lightyear-signed-work-order":
        raise ExecutionContractError("Invalid signed work-order envelope type")
    if envelope.get("content_sha256") != canonical_hash(envelope, {"content_sha256"}):
        raise ExecutionContractError("Signed work-order envelope hash is invalid")
    issuer = envelope.get("issuer", {})
    signature = envelope.get("signature", {})
    key_id = str(signature.get("key_id", ""))
    if key_id != issuer.get("key_id") or key_id not in policy.trusted_key_ids:
        raise ExecutionContractError("Signed work-order key identity is not trusted")
    if signature.get("algorithm") != policy.signature_algorithm:
        raise ExecutionContractError("Signed work-order algorithm is not allowed")
    key = trusted_keys.get(key_id)
    if key is None:
        raise ExecutionContractError("No verification key is configured for work-order issuer")
    _validate_key(key)
    unsigned = json.loads(json.dumps(envelope))
    supplied_signature = str(unsigned["signature"].get("value", ""))
    unsigned["signature"]["value"] = None
    unsigned.pop("content_sha256", None)
    expected = hmac.new(
        key, canonical_hash(unsigned).encode("ascii"), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(supplied_signature, expected):
        raise ExecutionContractError("Signed work-order signature is invalid")
    if envelope.get("execution_policy_sha256") != policy.content_sha256:
        raise ExecutionContractError("Signed work order targets a different execution policy")
    issued = parse_timestamp(str(envelope.get("issued_at", "")))
    expiry = parse_timestamp(str(envelope.get("expires_at", "")))
    current = parse_timestamp(now)
    if current < issued or current >= expiry:
        raise ExecutionContractError("Signed work order is not currently valid")
    if (expiry - issued) > timedelta(seconds=policy.max_work_order_ttl_seconds):
        raise ExecutionContractError("Signed work-order TTL exceeds admission policy")
    order = WorkOrder.from_dict(envelope.get("work_order", {}))
    if envelope.get("work_order_sha256") != order.content_sha256:
        raise ExecutionContractError("Signed work order content hash is invalid")
    nonce = safe_name(envelope.get("nonce"), "admission nonce")
    if nonce_store is not None:
        nonce_store.consume(nonce)
    receipt = {
        "schema_version": EXECUTION_SCHEMA_VERSION,
        "receipt_type": "lightyear-work-order-admission",
        "status": "passed",
        "issuer_id": issuer.get("id"),
        "key_id": key_id,
        "work_order_id": order.order_id,
        "work_order_sha256": order.content_sha256,
        "execution_policy_sha256": policy.content_sha256,
        "issued_at": envelope["issued_at"],
        "expires_at": envelope["expires_at"],
        "nonce_sha256": hashlib.sha256(nonce.encode("utf-8")).hexdigest(),
        "signature_sha256": hashlib.sha256(supplied_signature.encode("ascii")).hexdigest(),
    }
    receipt["content_sha256"] = canonical_hash(receipt)
    return order, receipt


class AdmissionNonceStore:
    """Atomic append-only replay ledger containing nonce hashes, never raw nonces."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def consume(self, nonce: str) -> None:
        identity = hashlib.sha256(nonce.encode("utf-8")).hexdigest()
        known = set()
        if self.path.is_file():
            known = {line.strip() for line in self.path.read_text(encoding="ascii").splitlines()}
        if identity in known:
            raise ExecutionContractError("Signed work-order nonce has already been consumed")
        descriptor = os.open(self.path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
        try:
            os.write(descriptor, (identity + "\n").encode("ascii"))
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _validate_key(key: bytes) -> None:
    if len(key) < 32:
        raise ExecutionContractError("Signing keys must contain at least 32 bytes")
