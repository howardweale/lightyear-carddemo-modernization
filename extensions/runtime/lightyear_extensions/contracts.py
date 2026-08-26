from __future__ import annotations

import copy
import hashlib
import hmac
import json
import re
from datetime import datetime
from typing import Any, Mapping


SCHEMA_VERSION = "1.0"
EVIDENCE_CLASSES = {"live", "recorded", "simulated", "inferred"}
ASSERTIONS = {"observed", "contradicted", "inferred"}
ENTITY_KINDS = {"node", "edge"}
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:._/@-]{0,255}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SENSITIVE_KEY = re.compile(
    r"password|token|authorization|cookie|secret|credential|private[_-]?key", re.I
)


class ExtensionContractError(ValueError):
    """Raised when adapter or extension evidence violates a trust boundary."""


def canonical_hash(payload: Mapping[str, Any], excluded: set[str] | None = None) -> str:
    excluded = excluded or set()
    normalized = {key: value for key, value in payload.items() if key not in excluded}
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def redact(value: Any) -> Any:
    """Recursively remove credential-shaped values before they cross the adapter boundary."""

    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if _SENSITIVE_KEY.search(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def finalize_envelope(
    payload: Mapping[str, Any],
    *,
    signing_key: bytes | None = None,
    key_id: str | None = None,
) -> dict[str, Any]:
    envelope = redact(copy.deepcopy(dict(payload)))
    envelope.pop("content_sha256", None)
    envelope.pop("signature", None)
    envelope["content_sha256"] = canonical_hash(envelope)
    if signing_key is not None:
        if len(signing_key) < 32:
            raise ExtensionContractError("Evidence signing keys must be at least 32 bytes")
        if not key_id or not _valid_identifier(key_id):
            raise ExtensionContractError("A safe key_id is required when signing evidence")
        value = hmac.new(
            signing_key,
            envelope["content_sha256"].encode("ascii"),
            hashlib.sha256,
        ).hexdigest()
        envelope["signature"] = {
            "algorithm": "HMAC-SHA256",
            "key_id": key_id,
            "value": value,
        }
    else:
        envelope["signature"] = None
    return envelope


def validate_envelope(
    envelope: Mapping[str, Any],
    *,
    graph: Mapping[str, Any] | None = None,
    trusted_keys: Mapping[str, bytes] | None = None,
) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version",
        "envelope_type",
        "envelope_id",
        "adapter",
        "source",
        "collected_at",
        "evidence_class",
        "graph_binding",
        "scope",
        "claims",
        "artifacts",
        "limitations",
        "content_sha256",
        "signature",
    }
    missing = sorted(required - set(envelope))
    if missing:
        errors.append(f"capture is missing required fields: {', '.join(missing)}")
        return errors
    if envelope.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"unsupported capture schema_version: {envelope.get('schema_version')}")
    if envelope.get("envelope_type") != "lightyear-adapter-evidence":
        errors.append("capture envelope_type is invalid")
    if not _valid_identifier(envelope.get("envelope_id")):
        errors.append("capture envelope_id is invalid")
    if envelope.get("evidence_class") not in EVIDENCE_CLASSES:
        errors.append(f"invalid evidence_class: {envelope.get('evidence_class')}")
    if not _timestamp(envelope.get("collected_at")):
        errors.append("capture collected_at must be an ISO-8601 timestamp with timezone")

    adapter = envelope.get("adapter")
    if not isinstance(adapter, dict) or not all(
        isinstance(adapter.get(field), str) and adapter[field].strip()
        for field in ("id", "version")
    ):
        errors.append("capture adapter requires id and version")
    source = envelope.get("source")
    if not isinstance(source, dict) or not all(
        isinstance(source.get(field), str) and source[field].strip()
        for field in ("system", "kind", "attestation")
    ):
        errors.append("capture source requires system, kind, and attestation")
    evidence_class = envelope.get("evidence_class")
    if evidence_class == "live" and isinstance(source, dict) and source.get("attestation") not in {
        "remote-verified",
        "operator-signed",
    }:
        errors.append("live evidence requires remote-verified or operator-signed attestation")
    if evidence_class == "recorded" and not _SHA256.fullmatch(
        str(envelope.get("recorded_from_sha256", ""))
    ):
        errors.append("recorded evidence requires recorded_from_sha256")
    scope = envelope.get("scope")
    if not isinstance(scope, dict) or scope.get("read_only") is not True:
        errors.append("capture scope must explicitly declare read_only true")

    binding = envelope.get("graph_binding")
    if not isinstance(binding, dict) or not _SHA256.fullmatch(
        str(binding.get("content_sha256", ""))
    ):
        errors.append("capture graph_binding requires a SHA-256 content identity")
    elif graph is not None:
        if binding.get("graph_id") != graph.get("graph_id"):
            errors.append("capture targets a different graph_id")
        if binding.get("content_sha256") != graph.get("content_sha256"):
            errors.append("capture targets a different graph content identity")

    claims = envelope.get("claims")
    if not isinstance(claims, list) or not claims:
        errors.append("capture requires at least one claim")
        claims = []
    graph_nodes = {item["id"] for item in graph.get("nodes", [])} if graph else set()
    graph_edges = {item["id"] for item in graph.get("edges", [])} if graph else set()
    for index, claim in enumerate(claims):
        if not isinstance(claim, dict):
            errors.append(f"claim {index} must be an object")
            continue
        kind = claim.get("entity_kind")
        entity_id = claim.get("entity_id")
        if kind not in ENTITY_KINDS:
            errors.append(f"claim {index} has invalid entity_kind")
        if not _valid_identifier(entity_id):
            errors.append(f"claim {index} has invalid entity_id")
        if claim.get("assertion") not in ASSERTIONS:
            errors.append(f"claim {index} has invalid assertion")
        if not isinstance(claim.get("operation"), str) or not claim["operation"].strip():
            errors.append(f"claim {index} requires an operation")
        if not isinstance(claim.get("details"), dict):
            errors.append(f"claim {index} details must be an object")
        if graph is not None and _valid_identifier(entity_id):
            valid = graph_nodes if kind == "node" else graph_edges
            if entity_id not in valid:
                errors.append(f"claim {index} references absent graph {kind}: {entity_id}")

    artifacts = envelope.get("artifacts")
    if not isinstance(artifacts, list):
        errors.append("capture artifacts must be an array")
    else:
        for index, artifact in enumerate(artifacts):
            if not isinstance(artifact, dict) or not _SHA256.fullmatch(
                str(artifact.get("sha256", ""))
            ):
                errors.append(f"artifact {index} requires a SHA-256 identity")
            if isinstance(artifact, dict) and artifact.get("content_retained") is not False:
                errors.append(f"artifact {index} must declare content_retained false")
    limitations = envelope.get("limitations")
    if not isinstance(limitations, list) or not all(
        isinstance(item, str) and item.strip() for item in limitations
    ):
        errors.append("capture limitations must be an array of non-empty strings")

    expected_hash = canonical_hash(envelope, {"content_sha256", "signature"})
    if envelope.get("content_sha256") != expected_hash:
        errors.append("capture content_sha256 is invalid")
    signature = envelope.get("signature")
    if evidence_class == "live" and signature is None:
        errors.append("live evidence requires a trusted signature")
    if signature is not None:
        if not isinstance(signature, dict) or signature.get("algorithm") != "HMAC-SHA256":
            errors.append("capture signature contract is invalid")
        else:
            key_id = str(signature.get("key_id", ""))
            key = (trusted_keys or {}).get(key_id)
            if key is None:
                errors.append(f"capture signature key is not trusted: {key_id}")
            elif len(key) < 32:
                errors.append(f"trusted capture key is too short: {key_id}")
            else:
                expected = hmac.new(
                    key,
                    str(envelope.get("content_sha256", "")).encode("ascii"),
                    hashlib.sha256,
                ).hexdigest()
                if not hmac.compare_digest(str(signature.get("value", "")), expected):
                    errors.append("capture signature is invalid")
    if _contains_sensitive_key(envelope):
        errors.append("capture contains a credential-shaped field")
    return errors


def _contains_sensitive_key(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            (_SENSITIVE_KEY.search(str(key)) and item != "[REDACTED]")
            or _contains_sensitive_key(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_sensitive_key(item) for item in value)
    return False


def _valid_identifier(value: Any) -> bool:
    return isinstance(value, str) and bool(_IDENTIFIER.fullmatch(value))


def _timestamp(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None
