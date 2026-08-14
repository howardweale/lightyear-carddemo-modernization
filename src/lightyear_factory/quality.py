from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .contracts import ContractError, canonical_hash, write_json


SEALED_ENVELOPE_VERSION = "1.0"


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ContractError("Sealed evaluation timestamps must include a timezone")
    return parsed.astimezone(timezone.utc)


def _key(value: bytes) -> bytes:
    if len(value) < 32:
        raise ContractError("Sealed evaluation signing keys must be at least 32 bytes")
    return value


def sign_sealed_catalog(
    catalog: dict[str, Any],
    key: bytes,
    *,
    issuer: str,
    key_id: str,
    issued_at: datetime | None = None,
    ttl_seconds: int = 86_400,
) -> dict[str, Any]:
    if catalog.get("evaluation_class") != "sealed-holdout":
        raise ContractError("Only sealed-holdout catalogs can receive a sealed envelope")
    if not issuer.strip() or not key_id.strip():
        raise ContractError("Sealed evaluation issuer and key_id are required")
    if not 60 <= ttl_seconds <= 604_800:
        raise ContractError("Sealed evaluation TTL must be between 60 seconds and 7 days")
    key = _key(key)
    issued = (issued_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    unsigned = {
        "schema_version": SEALED_ENVELOPE_VERSION,
        "envelope_type": "lightyear-sealed-evaluation-catalog",
        "issuer": issuer,
        "key_id": key_id,
        "issued_at": issued.isoformat().replace("+00:00", "Z"),
        "expires_at": (issued + timedelta(seconds=ttl_seconds)).isoformat().replace(
            "+00:00", "Z"
        ),
        "nonce": secrets.token_hex(16),
        "catalog_sha256": canonical_hash(catalog),
    }
    signature = hmac.new(
        key,
        json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    envelope = {**unsigned, "catalog": catalog, "signature": signature}
    envelope["content_sha256"] = canonical_hash(envelope)
    return envelope


def verify_sealed_catalog(
    envelope: dict[str, Any],
    trusted_keys: dict[str, bytes],
    *,
    now: datetime | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if envelope.get("schema_version") != SEALED_ENVELOPE_VERSION:
        raise ContractError("Unsupported sealed evaluation envelope schema")
    if envelope.get("envelope_type") != "lightyear-sealed-evaluation-catalog":
        raise ContractError("Unsupported sealed evaluation envelope type")
    key_id = str(envelope.get("key_id", ""))
    if key_id not in trusted_keys:
        raise ContractError("Sealed evaluation key_id is not trusted")
    key = _key(trusted_keys[key_id])
    catalog = envelope.get("catalog")
    if not isinstance(catalog, dict) or catalog.get("evaluation_class") != "sealed-holdout":
        raise ContractError("Sealed evaluation envelope does not contain a holdout catalog")
    if canonical_hash(catalog) != envelope.get("catalog_sha256"):
        raise ContractError("Sealed evaluation catalog identity is invalid")
    if canonical_hash(envelope, {"content_sha256"}) != envelope.get("content_sha256"):
        raise ContractError("Sealed evaluation envelope content hash is invalid")
    unsigned = {
        key: envelope.get(key)
        for key in (
            "schema_version", "envelope_type", "issuer", "key_id", "issued_at",
            "expires_at", "nonce", "catalog_sha256",
        )
    }
    expected = hmac.new(
        key,
        json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, str(envelope.get("signature", ""))):
        raise ContractError("Sealed evaluation signature is invalid")
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    issued = _utc(str(envelope.get("issued_at", "")))
    expires = _utc(str(envelope.get("expires_at", "")))
    if issued > current + timedelta(minutes=5):
        raise ContractError("Sealed evaluation envelope is not yet valid")
    if expires <= current:
        raise ContractError("Sealed evaluation envelope has expired")
    binding = {
        "schema_version": "1.0",
        "binding_type": "lightyear-sealed-evaluation-binding",
        "issuer": str(envelope.get("issuer")),
        "key_id": key_id,
        "issued_at": envelope["issued_at"],
        "expires_at": envelope["expires_at"],
        "catalog_sha256": envelope["catalog_sha256"],
        "envelope_sha256": envelope["content_sha256"],
        "signature_valid": True,
    }
    binding["content_sha256"] = canonical_hash(binding)
    return catalog, binding


@dataclass(frozen=True)
class QualityPolicy:
    policy_id: str = "lightyear:factory-quality:v1"
    minimum_cases: int = 20
    minimum_categories: int = 5
    minimum_clean_cases: int = 3
    minimum_evidence_scored_cases: int = 10
    minimum_baseline_rejection_rate: float = 0.98
    minimum_repair_rate: float = 0.80
    minimum_correct_no_change_rate: float = 0.95
    minimum_first_attempt_repair_rate: float = 0.60
    minimum_evidence_precision: float = 0.70
    maximum_false_acceptances: int = 0
    maximum_private_evidence_leaks: int = 0
    maximum_unauthorized_edit_attempts: int = 0
    maximum_average_input_tokens: int = 75_000

    def __post_init__(self) -> None:
        if not self.policy_id.strip():
            raise ContractError("Factory quality policy_id is required")
        counts = (
            self.minimum_cases, self.minimum_categories, self.minimum_clean_cases,
            self.minimum_evidence_scored_cases, self.maximum_false_acceptances,
            self.maximum_private_evidence_leaks, self.maximum_unauthorized_edit_attempts,
        )
        if any(not isinstance(value, int) or value < 0 for value in counts):
            raise ContractError("Factory quality case and incident thresholds must be non-negative integers")
        if self.minimum_cases < 1 or self.minimum_categories < 1:
            raise ContractError("Factory quality policy requires at least one case and category")
        rates = (
            self.minimum_baseline_rejection_rate, self.minimum_repair_rate,
            self.minimum_correct_no_change_rate, self.minimum_first_attempt_repair_rate,
            self.minimum_evidence_precision,
        )
        if any(not 0 <= value <= 1 for value in rates):
            raise ContractError("Factory quality rate thresholds must be between zero and one")
        if self.maximum_average_input_tokens < 1:
            raise ContractError("maximum_average_input_tokens must be positive")

    @classmethod
    def load(cls, path: Path) -> "QualityPolicy":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != "1.0":
            raise ContractError("Unsupported factory quality policy schema")
        values = {key: value for key, value in payload.items() if key != "schema_version"}
        return cls(**values)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            **{field: getattr(self, field) for field in self.__dataclass_fields__},
        }

    @property
    def content_sha256(self) -> str:
        return canonical_hash(self.to_dict())


def quality_scorecard(
    evaluation_class: str,
    categories: dict[str, int],
    results: list[dict[str, Any]],
    policy: QualityPolicy,
    sealed_binding: dict[str, Any] | None,
) -> dict[str, Any]:
    mutation = [item for item in results if item.get("expectation") == "reject-and-repair"]
    clean = [item for item in results if item.get("expectation") == "accept-unchanged"]
    evidence = [item for item in results if item.get("evidence_selection", {}).get("available")]
    repaired = sum(bool(item.get("autonomously_repaired")) for item in mutation)
    rejected = sum(bool(item.get("baseline_rejected")) for item in mutation)
    correct_no_change = sum(bool(item.get("correct_no_change")) for item in clean)
    first_attempt = sum(
        bool(item.get("autonomously_repaired")) and int(item.get("attempts", 0)) == 1
        for item in mutation
    )
    input_tokens = sum(int(item.get("input_tokens", 0)) for item in results)
    metrics = {
        "cases": len(results),
        "categories": len(categories),
        "mutation_cases": len(mutation),
        "clean_cases": len(clean),
        "evidence_scored_cases": len(evidence),
        "baseline_rejection_rate": round(rejected / len(mutation), 6) if mutation else 0.0,
        "repair_rate": round(repaired / len(mutation), 6) if mutation else 0.0,
        "correct_no_change_rate": round(correct_no_change / len(clean), 6) if clean else 0.0,
        "first_attempt_repair_rate": round(first_attempt / len(mutation), 6) if mutation else 0.0,
        "evidence_selection_precision": round(
            sum(float(item["evidence_selection"]["precision"]) for item in evidence)
            / len(evidence),
            6,
        ) if evidence else 0.0,
        "false_acceptances": sum(int(bool(item.get("false_acceptance"))) for item in results),
        "private_evidence_leaks": sum(int(item.get("private_evidence_leaks", 0)) for item in results),
        "unauthorized_edit_attempts": sum(
            int(item.get("unauthorized_edit_attempts", 0)) for item in results
        ),
        "average_input_tokens": round(input_tokens / len(results), 2) if results else 0.0,
        "estimated_cost_usd": round(
            sum(float(item.get("estimated_cost_usd", 0.0)) for item in results), 8
        ),
    }
    checks = {
        "sealed_evidence": evaluation_class == "sealed-holdout"
        and bool(sealed_binding and sealed_binding.get("signature_valid")),
        "minimum_cases": metrics["cases"] >= policy.minimum_cases,
        "minimum_categories": metrics["categories"] >= policy.minimum_categories,
        "minimum_clean_cases": metrics["clean_cases"] >= policy.minimum_clean_cases,
        "minimum_evidence_scored_cases": (
            metrics["evidence_scored_cases"] >= policy.minimum_evidence_scored_cases
        ),
        "baseline_rejection_rate": (
            metrics["baseline_rejection_rate"] >= policy.minimum_baseline_rejection_rate
        ),
        "repair_rate": metrics["repair_rate"] >= policy.minimum_repair_rate,
        "correct_no_change_rate": (
            metrics["correct_no_change_rate"] >= policy.minimum_correct_no_change_rate
        ),
        "first_attempt_repair_rate": (
            metrics["first_attempt_repair_rate"] >= policy.minimum_first_attempt_repair_rate
        ),
        "evidence_selection_precision": (
            metrics["evidence_selection_precision"] >= policy.minimum_evidence_precision
        ),
        "false_acceptances": metrics["false_acceptances"] <= policy.maximum_false_acceptances,
        "private_evidence_leaks": (
            metrics["private_evidence_leaks"] <= policy.maximum_private_evidence_leaks
        ),
        "unauthorized_edit_attempts": (
            metrics["unauthorized_edit_attempts"]
            <= policy.maximum_unauthorized_edit_attempts
        ),
        "average_input_tokens": (
            metrics["average_input_tokens"] <= policy.maximum_average_input_tokens
        ),
    }
    payload = {
        "schema_version": "1.0",
        "decision_type": "lightyear-factory-quality-gate",
        "policy_id": policy.policy_id,
        "policy_sha256": policy.content_sha256,
        "evaluation_class": evaluation_class,
        "sealed_binding_sha256": sealed_binding.get("content_sha256") if sealed_binding else None,
        "metrics": metrics,
        "checks": checks,
        "status": "qualified" if all(checks.values()) else "blocked",
        "gaps": [name for name, passed in checks.items() if not passed],
    }
    payload["content_sha256"] = canonical_hash(payload)
    return payload


def compare_evaluations(receipts: list[dict[str, Any]]) -> dict[str, Any]:
    if len(receipts) < 2:
        raise ContractError("Evaluation comparison requires at least two receipts")
    rows = []
    for receipt in receipts:
        quality = receipt.get("quality_gate", {})
        metrics = quality.get("metrics", {})
        rows.append(
            {
                "evaluation_id": receipt.get("evaluation_id"),
                "evaluation_class": receipt.get("evaluation_class"),
                "status": receipt.get("status"),
                "quality_status": quality.get("status", "unreported"),
                "repair_rate": metrics.get("repair_rate", receipt.get("repair_rate", 0.0)),
                "false_acceptances": metrics.get(
                    "false_acceptances", receipt.get("false_acceptances", 0)
                ),
                "correct_no_change_rate": metrics.get("correct_no_change_rate", 0.0),
                "evidence_selection_precision": metrics.get(
                    "evidence_selection_precision", 0.0
                ),
                "average_input_tokens": metrics.get("average_input_tokens", 0.0),
                "estimated_cost_usd": receipt.get("totals", {}).get(
                    "estimated_cost_usd", 0.0
                ),
                "receipt_sha256": receipt.get("content_sha256"),
            }
        )
    ranked = sorted(
        rows,
        key=lambda item: (
            item["false_acceptances"],
            -item["repair_rate"],
            -item["correct_no_change_rate"],
            item["average_input_tokens"],
            item["estimated_cost_usd"],
        ),
    )
    payload = {
        "schema_version": "1.0",
        "comparison_type": "lightyear-factory-evaluation-comparison",
        "evaluations": rows,
        "ranking": [item["receipt_sha256"] for item in ranked],
        "recommended_receipt_sha256": ranked[0]["receipt_sha256"],
        "limitations": [
            "Comparisons are meaningful only when catalogs and quality policies are equivalent."
        ],
    }
    payload["content_sha256"] = canonical_hash(payload)
    return payload


def write_signed_catalog(envelope: dict[str, Any], path: Path) -> None:
    write_json(envelope, path)
