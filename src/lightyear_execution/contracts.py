from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EXECUTION_SCHEMA_VERSION = "1.0"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")


class ExecutionContractError(ValueError):
    """An execution-plane contract is unsafe or internally inconsistent."""


def canonical_hash(payload: dict[str, Any], excluded: set[str] | None = None) -> str:
    normalized = {
        key: value for key, value in payload.items() if key not in (excluded or set())
    }
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def parse_timestamp(value: str) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ExecutionContractError(f"Invalid execution timestamp: {value}") from error
    if result.tzinfo is None:
        raise ExecutionContractError("Execution timestamps require a timezone")
    return result.astimezone(timezone.utc)


def safe_name(value: Any, field: str) -> str:
    result = str(value or "").strip()
    if not _NAME.fullmatch(result):
        raise ExecutionContractError(f"Invalid {field}: {result!r}")
    return result


@dataclass(frozen=True)
class ExecutionPolicy:
    policy_id: str
    version: str
    runtimes: tuple[str, ...]
    image: str
    image_digest: str
    network_mode: str
    read_only_root: bool
    workspace_read_only: bool
    run_as_user: str
    cap_drop_all: bool
    no_new_privileges: bool
    pids_limit: int
    memory_mb: int
    cpus: float
    tmpfs_mb: int
    allowed_commands: tuple[str, ...]
    allowed_environment: tuple[str, ...]
    admission_required: bool
    signature_algorithm: str
    trusted_key_ids: tuple[str, ...]
    max_work_order_ttl_seconds: int
    identity_ttl_seconds: int
    role_actions: dict[str, tuple[str, ...]]
    allowed_secret_names: tuple[str, ...]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ExecutionPolicy":
        if payload.get("schema_version") != EXECUTION_SCHEMA_VERSION:
            raise ExecutionContractError("Unsupported execution policy schema")
        runtime = payload.get("runtime", {})
        isolation = payload.get("isolation", {})
        admission = payload.get("admission", {})
        identities = payload.get("identities", {})
        secrets = payload.get("secrets", {})
        runtimes = tuple(runtime.get("allowed", []))
        if not runtimes or any(item not in {"docker", "podman"} for item in runtimes):
            raise ExecutionContractError("Execution policy allows an unsupported OCI runtime")
        image = str(runtime.get("image", ""))
        digest = str(runtime.get("image_digest", ""))
        if not image or "@" in image or not _SHA256.fullmatch(digest):
            raise ExecutionContractError("Execution image must have a separate SHA-256 digest")
        if isolation.get("network_mode") != "none":
            raise ExecutionContractError("v0.11 hardened execution requires network_mode none")
        user = str(isolation.get("run_as_user", ""))
        if not re.fullmatch(r"[1-9][0-9]*:[1-9][0-9]*", user):
            raise ExecutionContractError("Container must run as a numeric non-root uid:gid")
        required_true = (
            "read_only_root", "workspace_read_only", "cap_drop_all", "no_new_privileges"
        )
        if any(isolation.get(item) is not True for item in required_true):
            raise ExecutionContractError("Hardened isolation controls cannot be disabled")
        pids = int(isolation.get("pids_limit", 0))
        memory = int(isolation.get("memory_mb", 0))
        cpus = float(isolation.get("cpus", 0))
        tmpfs = int(isolation.get("tmpfs_mb", 0))
        if not 16 <= pids <= 1024 or not 64 <= memory <= 32768:
            raise ExecutionContractError("Execution resource limits are outside policy bounds")
        if not 0.1 <= cpus <= 16 or not 8 <= tmpfs <= 1024:
            raise ExecutionContractError("Execution CPU or tmpfs limit is outside policy bounds")
        commands = tuple(str(item) for item in runtime.get("allowed_commands", []))
        environment = tuple(str(item) for item in runtime.get("allowed_environment", []))
        if not commands or any("/" in item or not item for item in commands):
            raise ExecutionContractError("Allowed commands must be executable basenames")
        if any(not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", item) for item in environment):
            raise ExecutionContractError("Invalid allowed environment variable")
        if admission.get("required") is not True:
            raise ExecutionContractError("Hardened execution requires signed admission")
        if admission.get("signature_algorithm") != "HMAC-SHA256":
            raise ExecutionContractError("Unsupported work-order signature algorithm")
        key_ids = tuple(str(item) for item in admission.get("trusted_key_ids", []))
        if not key_ids:
            raise ExecutionContractError("Admission policy requires at least one trusted key id")
        ttl = int(admission.get("max_ttl_seconds", 0))
        identity_ttl = int(identities.get("credential_ttl_seconds", 0))
        if not 60 <= ttl <= 86400 or not 30 <= identity_ttl <= ttl:
            raise ExecutionContractError("Admission or identity TTL is outside policy bounds")
        roles = identities.get("roles", {})
        required_roles = {"planner", "builder", "verifier"}
        if not required_roles.issubset(roles):
            raise ExecutionContractError("Identity policy must define planner, builder, and verifier")
        role_actions = {
            role: tuple(str(item) for item in roles[role].get("actions", []))
            for role in sorted(roles)
        }
        if any(not actions for actions in role_actions.values()):
            raise ExecutionContractError("Every agent role requires authorized actions")
        secret_names = tuple(str(item) for item in secrets.get("allowed_names", []))
        if any(not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", item) for item in secret_names):
            raise ExecutionContractError("Invalid secret name in execution policy")
        if secrets.get("persist_values") is not False:
            raise ExecutionContractError("Secret values must never be persisted")
        return cls(
            safe_name(payload.get("id"), "execution policy id"),
            str(payload.get("version", "")),
            runtimes,
            image,
            digest,
            "none",
            True,
            True,
            user,
            True,
            True,
            pids,
            memory,
            cpus,
            tmpfs,
            commands,
            environment,
            True,
            "HMAC-SHA256",
            key_ids,
            ttl,
            identity_ttl,
            role_actions,
            secret_names,
        )

    @classmethod
    def load(cls, path: Path) -> "ExecutionPolicy":
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))

    @property
    def image_reference(self) -> str:
        return f"{self.image}@sha256:{self.image_digest}"

    @property
    def content_sha256(self) -> str:
        return canonical_hash(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": EXECUTION_SCHEMA_VERSION,
            "id": self.policy_id,
            "version": self.version,
            "runtime": {
                "allowed": list(self.runtimes),
                "image": self.image,
                "image_digest": self.image_digest,
                "allowed_commands": list(self.allowed_commands),
                "allowed_environment": list(self.allowed_environment),
            },
            "isolation": {
                "network_mode": self.network_mode,
                "read_only_root": self.read_only_root,
                "workspace_read_only": self.workspace_read_only,
                "run_as_user": self.run_as_user,
                "cap_drop_all": self.cap_drop_all,
                "no_new_privileges": self.no_new_privileges,
                "pids_limit": self.pids_limit,
                "memory_mb": self.memory_mb,
                "cpus": self.cpus,
                "tmpfs_mb": self.tmpfs_mb,
            },
            "admission": {
                "required": self.admission_required,
                "signature_algorithm": self.signature_algorithm,
                "trusted_key_ids": list(self.trusted_key_ids),
                "max_ttl_seconds": self.max_work_order_ttl_seconds,
            },
            "identities": {
                "credential_ttl_seconds": self.identity_ttl_seconds,
                "roles": {
                    role: {"actions": list(actions)}
                    for role, actions in self.role_actions.items()
                },
            },
            "secrets": {
                "allowed_names": list(self.allowed_secret_names),
                "persist_values": False,
            },
        }
