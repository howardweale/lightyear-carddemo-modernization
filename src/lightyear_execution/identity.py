from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import timedelta
from typing import Any

from .contracts import ExecutionContractError, ExecutionPolicy, canonical_hash, parse_timestamp


class IdentityAuthority:
    """Issues short-lived, action-scoped credentials for replaceable worker roles."""

    def __init__(self, policy: ExecutionPolicy, signing_key: bytes) -> None:
        if len(signing_key) < 32:
            raise ExecutionContractError("Identity signing key must contain at least 32 bytes")
        self.policy = policy
        self.signing_key = signing_key

    def issue(
        self,
        role: str,
        work_order_sha256: str,
        issued_at: str,
        credential_id: str,
    ) -> tuple[str, dict[str, Any]]:
        if role not in self.policy.role_actions:
            raise ExecutionContractError(f"Unknown agent role: {role}")
        issued = parse_timestamp(issued_at)
        expires = issued + timedelta(seconds=self.policy.identity_ttl_seconds)
        claims = {
            "schema_version": "1.0",
            "credential_id": credential_id,
            "subject": f"agent:{role}",
            "role": role,
            "actions": list(self.policy.role_actions[role]),
            "audience": "lightyear-factory-controller",
            "work_order_sha256": work_order_sha256,
            "issued_at": issued_at,
            "expires_at": expires.isoformat().replace("+00:00", "Z"),
            "execution_policy_sha256": self.policy.content_sha256,
        }
        encoded = base64.urlsafe_b64encode(
            json.dumps(claims, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).rstrip(b"=")
        signature = hmac.new(self.signing_key, encoded, hashlib.sha256).hexdigest().encode("ascii")
        token = encoded.decode("ascii") + "." + signature.decode("ascii")
        receipt = {
            "credential_id": credential_id,
            "role": role,
            "actions": claims["actions"],
            "work_order_sha256": work_order_sha256,
            "expires_at": claims["expires_at"],
            "token_sha256": hashlib.sha256(token.encode("ascii")).hexdigest(),
        }
        receipt["content_sha256"] = canonical_hash(receipt)
        return token, receipt

    def verify(
        self,
        token: str,
        required_action: str,
        work_order_sha256: str,
        now: str,
    ) -> dict[str, Any]:
        try:
            encoded_text, supplied = token.split(".", 1)
            encoded = encoded_text.encode("ascii")
            expected = hmac.new(self.signing_key, encoded, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(supplied, expected):
                raise ExecutionContractError("Agent credential signature is invalid")
            padded = encoded + b"=" * (-len(encoded) % 4)
            claims = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        except (ValueError, UnicodeError, json.JSONDecodeError) as error:
            raise ExecutionContractError("Agent credential is malformed") from error
        if claims.get("audience") != "lightyear-factory-controller":
            raise ExecutionContractError("Agent credential audience is invalid")
        if claims.get("execution_policy_sha256") != self.policy.content_sha256:
            raise ExecutionContractError("Agent credential targets a different policy")
        if claims.get("work_order_sha256") != work_order_sha256:
            raise ExecutionContractError("Agent credential targets a different work order")
        if required_action not in claims.get("actions", []):
            raise ExecutionContractError("Agent credential does not authorize this action")
        current = parse_timestamp(now)
        if current < parse_timestamp(claims["issued_at"]) or current >= parse_timestamp(claims["expires_at"]):
            raise ExecutionContractError("Agent credential is expired or not yet valid")
        return claims
