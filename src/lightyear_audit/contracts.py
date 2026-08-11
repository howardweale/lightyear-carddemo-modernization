from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


AUDIT_SCHEMA_VERSION = "1.0"
ACTOR_ROLES = {
    "system", "planner", "builder", "verifier", "operator", "approver", "auditor"
}
VISIBILITIES = {"shared", "auditor_private"}
DECISION_STATUSES = {"passed", "blocked", "overridden"}
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/$#-]{0,199}$")
_SENSITIVE = re.compile(r"password|token|authorization|cookie|secret|credential|private[_-]?key", re.I)


class AuditContractError(ValueError):
    """Raised when an audit record is incomplete, unsafe, or internally inconsistent."""


def canonical_hash(payload: dict[str, Any], excluded: set[str] | None = None) -> str:
    excluded = excluded or set()
    normalized = {key: value for key, value in payload.items() if key not in excluded}
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def parse_timestamp(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    try:
        result = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise AuditContractError(f"Invalid audit timestamp: {value}") from error
    if result.tzinfo is None:
        raise AuditContractError("Audit timestamps must contain a timezone")
    return result.astimezone(timezone.utc)


def safe_identifier(value: Any, field: str) -> str:
    result = str(value or "").strip()
    if not _IDENTIFIER.fullmatch(result):
        raise AuditContractError(f"Invalid {field}: {result!r}")
    return result


def reject_secrets(value: Any, path: str = "payload") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if _SENSITIVE.search(str(key)):
                raise AuditContractError(f"Sensitive field is forbidden in audit records: {path}.{key}")
            reject_secrets(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            reject_secrets(item, f"{path}[{index}]")


@dataclass(frozen=True)
class Actor:
    actor_id: str
    role: str
    kind: str = "service"

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Actor":
        actor_id = safe_identifier(payload.get("id"), "actor id")
        role = str(payload.get("role", "")).strip()
        kind = str(payload.get("kind", "service")).strip()
        if role not in ACTOR_ROLES:
            raise AuditContractError(f"Invalid audit actor role: {role}")
        if kind not in {"human", "service", "agent"}:
            raise AuditContractError(f"Invalid audit actor kind: {kind}")
        return cls(actor_id, role, kind)

    def to_dict(self) -> dict[str, str]:
        return {"id": self.actor_id, "kind": self.kind, "role": self.role}


@dataclass(frozen=True)
class Subject:
    subject_id: str
    kind: str

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Subject":
        subject_id = safe_identifier(payload.get("id"), "subject id")
        kind = safe_identifier(payload.get("kind"), "subject kind")
        return cls(subject_id, kind)

    def to_dict(self) -> dict[str, str]:
        return {"id": self.subject_id, "kind": self.kind}


@dataclass(frozen=True)
class EvidenceReference:
    evidence_id: str
    kind: str
    sha256: str

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "EvidenceReference":
        evidence_id = safe_identifier(payload.get("id"), "evidence id")
        kind = safe_identifier(payload.get("kind"), "evidence kind")
        sha256 = str(payload.get("sha256", ""))
        if not re.fullmatch(r"[0-9a-f]{64}", sha256):
            raise AuditContractError("Evidence reference requires a lowercase SHA-256 identity")
        return cls(evidence_id, kind, sha256)

    def to_dict(self) -> dict[str, str]:
        return {"id": self.evidence_id, "kind": self.kind, "sha256": self.sha256}


@dataclass(frozen=True)
class EventDraft:
    occurred_at: str
    actor: Actor
    action: str
    subject: Subject
    evidence: tuple[EvidenceReference, ...]
    details: dict[str, Any]
    visibility: str = "shared"

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "EventDraft":
        occurred_at = str(payload.get("occurred_at", "")).strip()
        parse_timestamp(occurred_at)
        actor_payload = payload.get("actor")
        subject_payload = payload.get("subject")
        evidence_payload = payload.get("evidence", [])
        details = payload.get("details", {})
        if not isinstance(actor_payload, dict) or not isinstance(subject_payload, dict):
            raise AuditContractError("Audit event requires actor and subject objects")
        if not isinstance(evidence_payload, list):
            raise AuditContractError("Audit event evidence must be an array")
        if not isinstance(details, dict):
            raise AuditContractError("Audit event details must be an object")
        reject_secrets(details)
        encoded = json.dumps(details, sort_keys=True).encode("utf-8")
        if len(encoded) > 64 * 1024:
            raise AuditContractError("Audit event details exceed 64 KiB")
        action = safe_identifier(payload.get("action"), "audit action")
        visibility = str(payload.get("visibility", "shared"))
        if visibility not in VISIBILITIES:
            raise AuditContractError(f"Invalid audit visibility: {visibility}")
        actor = Actor.from_dict(actor_payload)
        if action == "policy.decision_recorded" and actor.role not in {
            "system", "verifier", "approver"
        }:
            raise AuditContractError("Builders and planners cannot record policy decisions")
        return cls(
            occurred_at,
            actor,
            action,
            Subject.from_dict(subject_payload),
            tuple(EvidenceReference.from_dict(item) for item in evidence_payload),
            details,
            visibility,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "actor": self.actor.to_dict(),
            "details": self.details,
            "evidence": [item.to_dict() for item in self.evidence],
            "occurred_at": self.occurred_at,
            "subject": self.subject.to_dict(),
            "visibility": self.visibility,
        }


@dataclass(frozen=True)
class ExceptionGrant:
    exception_id: str
    policy_id: str
    subject_id: str
    owner: str
    approved_by: Actor
    justification: str
    expires_at: str
    compensating_controls: tuple[str, ...]

    @classmethod
    def from_dict(cls, payload: dict[str, Any], now: str | None = None) -> "ExceptionGrant":
        controls = payload.get("compensating_controls", [])
        if not isinstance(controls, list) or not controls or not all(
            isinstance(item, str) and item.strip() for item in controls
        ):
            raise AuditContractError("Exception requires compensating controls")
        approved_by = Actor.from_dict(payload.get("approved_by", {}))
        if approved_by.role != "approver" or approved_by.kind != "human":
            raise AuditContractError("Exception approval requires a human approver")
        expires_at = str(payload.get("expires_at", ""))
        expiry = parse_timestamp(expires_at)
        if now is not None and expiry <= parse_timestamp(now):
            raise AuditContractError("Exception is expired")
        justification = str(payload.get("justification", "")).strip()
        owner = safe_identifier(payload.get("owner"), "exception owner")
        if len(justification) < 20:
            raise AuditContractError("Exception justification must contain at least 20 characters")
        reject_secrets(payload)
        return cls(
            safe_identifier(payload.get("id"), "exception id"),
            safe_identifier(payload.get("policy_id"), "exception policy id"),
            safe_identifier(payload.get("subject_id"), "exception subject id"),
            owner,
            approved_by,
            justification,
            expires_at,
            tuple(controls),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "approved_by": self.approved_by.to_dict(),
            "compensating_controls": list(self.compensating_controls),
            "expires_at": self.expires_at,
            "id": self.exception_id,
            "justification": self.justification,
            "owner": self.owner,
            "policy_id": self.policy_id,
            "subject_id": self.subject_id,
        }
