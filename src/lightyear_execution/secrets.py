from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from typing import Any

from .contracts import ExecutionContractError, ExecutionPolicy, canonical_hash
from .identity import IdentityAuthority


@dataclass
class SecretLease:
    lease_id: str
    name: str
    _value: str
    _consumed: bool = False

    def consume(self) -> str:
        if self._consumed:
            raise ExecutionContractError("Secret lease has already been consumed")
        self._consumed = True
        value = self._value
        self._value = ""
        return value


class SecretBroker:
    """Issues one-use in-memory values and receipts that never contain secret material."""

    def __init__(
        self,
        policy: ExecutionPolicy,
        identity_authority: IdentityAuthority,
        values: dict[str, str],
    ) -> None:
        self.policy = policy
        self.identity_authority = identity_authority
        self.values = values

    def lease(
        self,
        token: str,
        name: str,
        work_order_sha256: str,
        now: str,
    ) -> tuple[SecretLease, dict[str, Any]]:
        if name not in self.policy.allowed_secret_names:
            raise ExecutionContractError("Secret name is not allowed by execution policy")
        claims = self.identity_authority.verify(
            token, f"secret:lease:{name}", work_order_sha256, now
        )
        if name not in self.values or not self.values[name]:
            raise ExecutionContractError("Requested secret is unavailable")
        lease_id = "lease:" + secrets.token_hex(12)
        lease = SecretLease(lease_id, name, self.values[name])
        receipt: dict[str, Any] = {
            "schema_version": "1.0",
            "receipt_type": "lightyear-secret-lease",
            "lease_id_sha256": hashlib.sha256(lease_id.encode("utf-8")).hexdigest(),
            "secret_name": name,
            "subject": claims["subject"],
            "work_order_sha256": work_order_sha256,
            "issued_at": now,
            "one_use": True,
            "value_persisted": False,
        }
        receipt["content_sha256"] = canonical_hash(receipt)
        return lease, receipt
