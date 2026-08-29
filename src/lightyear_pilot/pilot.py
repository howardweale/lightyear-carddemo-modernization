from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

from lightyear_common.io import normalize_logical_source


SCHEMA_VERSION = "1.0"
INTAKE_TYPE = "lightyear-source-only-pilot-intake"
PREFLIGHT_TYPE = "lightyear-mainframe-evidence-preflight"
DOSSIER_TYPE = "lightyear-source-only-pilot-dossier"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_APPROVAL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{2,127}$")
_SECRET_PATTERNS = (
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", re.I),
    re.compile(rb"authorization\s*:\s*bearer\s+[A-Za-z0-9._~+/-]{12,}", re.I),
    re.compile(rb"aws_secret_access_key\s*[=:]\s*\S+", re.I),
    re.compile(rb"(?:password|passwd|api[_-]?key|access[_-]?token)\s*[=:]\s*['\"]?[^\s'\"]{8,}", re.I),
)


class PilotError(ValueError):
    """Raised when pilot evidence violates an intake or trust boundary."""


def canonical_hash(payload: Mapping[str, Any], excluded: set[str] | None = None) -> str:
    excluded = excluded or set()
    normalized = {key: value for key, value in payload.items() if key not in excluded}
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PilotError(f"JSON object required: {path}")
    return payload


def _require_content_hash(payload: Mapping[str, Any], label: str) -> None:
    actual = payload.get("content_sha256")
    if actual != canonical_hash(payload, {"content_sha256"}):
        raise PilotError(f"stale-or-tampered-content-hash:{label}")


def _profile_intake(profile: Mapping[str, Any]) -> Mapping[str, Any]:
    if profile.get("schema_version") != SCHEMA_VERSION:
        raise PilotError("unsupported-pilot-profile-schema")
    if profile.get("profile_type") != "lightyear-source-only-pilot-profile":
        raise PilotError("invalid-pilot-profile-type")
    _require_content_hash(profile, "pilot-profile")
    if not all(isinstance(profile.get(field), str) and profile[field] for field in ("pilot_id", "release")):
        raise PilotError("pilot-profile-release-identity-missing")
    intake = profile.get("intake")
    if not isinstance(intake, dict):
        raise PilotError("pilot-profile-intake-missing")
    artifacts = profile.get("evidence_artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise PilotError("pilot-profile-evidence-registry-missing")
    ids: set[str] = set()
    paths: set[str] = set()
    for item in artifacts:
        if not isinstance(item, dict) or not all(isinstance(item.get(field), str) and item[field] for field in ("id", "role", "path")):
            raise PilotError("pilot-profile-evidence-entry-invalid")
        path = str(item["path"])
        if path.startswith(("/", "\\")) or ".." in Path(path).parts:
            raise PilotError("pilot-profile-evidence-path-unsafe")
        if item["id"] in ids or path in paths:
            raise PilotError("pilot-profile-evidence-entry-duplicate")
        if not _SHA256.fullmatch(str(item.get("sha256", ""))):
            raise PilotError("pilot-profile-evidence-hash-invalid")
        ids.add(item["id"])
        paths.add(path)
    boundary = profile.get("claim_boundary")
    if not isinstance(boundary, dict) or boundary != {
        "source_only_pilot": True,
        "live_mainframe_observed": False,
        "model_qualified": False,
        "mainframe_equivalent": False,
        "production_ready": False,
    }:
        raise PilotError("pilot-profile-claim-boundary-invalid")
    return intake


def _classify(path: Path, intake: Mapping[str, Any]) -> str | None:
    suffix = path.suffix.lower()
    file_name = path.name.lower()
    for item in intake.get("file_classes", []):
        if not isinstance(item, dict) or not isinstance(item.get("kind"), str):
            continue
        extensions = {str(value).lower() for value in item.get("extensions", [])}
        names = {str(value).lower() for value in item.get("names", [])}
        if suffix in extensions or file_name in names:
            return item["kind"]
    return None


def _source_files(source_root: Path) -> Iterable[Path]:
    for path in sorted(source_root.rglob("*"), key=lambda value: value.as_posix().lower()):
        if path.is_symlink():
            raise PilotError(f"symbolic-links-are-not-accepted:{path.relative_to(source_root).as_posix()}")
        if path.is_file():
            yield path


def build_intake_manifest(
    source_root: Path,
    profile: Mapping[str, Any],
    *,
    approval_id: str,
    source_label: str,
) -> dict[str, Any]:
    intake = _profile_intake(profile)
    if not source_root.is_dir():
        raise PilotError(f"source-root-not-directory:{source_root}")
    if not _SAFE_APPROVAL.fullmatch(approval_id):
        raise PilotError("approval-id-is-not-safe")
    if not source_label or len(source_label) > 80 or any(char in source_label for char in "\\\r\n\t"):
        raise PilotError("source-label-is-not-safe")

    max_files = int(intake.get("max_files", 0))
    max_file_bytes = int(intake.get("max_file_bytes", 0))
    max_total_bytes = int(intake.get("max_total_bytes", 0))
    if not (1 <= max_files <= 100_000 and 1 <= max_file_bytes <= max_total_bytes):
        raise PilotError("pilot-profile-bounds-invalid")

    files: list[dict[str, Any]] = []
    total_bytes = 0
    for path in _source_files(source_root):
        relative = path.relative_to(source_root)
        if any(part.startswith(".") for part in relative.parts):
            raise PilotError(f"hidden-path-is-not-accepted:{relative.as_posix()}")
        kind = _classify(path, intake)
        if kind is None:
            raise PilotError(f"unsupported-source-file:{relative.as_posix()}")
        raw = path.read_bytes()
        if len(raw) > max_file_bytes:
            raise PilotError(f"source-file-too-large:{relative.as_posix()}")
        if b"\x00" in raw:
            raise PilotError(f"binary-source-is-not-accepted:{relative.as_posix()}")
        try:
            logical = normalize_logical_source(raw)
            text = logical.decode("utf-8")
        except UnicodeDecodeError as error:
            raise PilotError(f"source-is-not-utf8:{relative.as_posix()}") from error
        if any(pattern.search(raw) for pattern in _SECRET_PATTERNS):
            raise PilotError(f"credential-shaped-material-detected:{relative.as_posix()}")
        total_bytes += len(raw)
        if total_bytes > max_total_bytes:
            raise PilotError("source-intake-total-size-exceeded")
        files.append(
            {
                "path": relative.as_posix(),
                "kind": kind,
                "bytes": len(raw),
                "lines": len(text.splitlines()),
                "logical_sha256": hashlib.sha256(logical).hexdigest(),
                "raw_sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
        if len(files) > max_files:
            raise PilotError("source-intake-file-count-exceeded")

    if not files:
        raise PilotError("source-intake-is-empty")
    counts = Counter(item["kind"] for item in files)
    required = sorted(str(value) for value in intake.get("required_reference_classes", []))
    missing = sorted(kind for kind in required if counts[kind] == 0)
    if approval_id == "repository-reference-fixture" and missing:
        raise PilotError(f"required-source-classes-missing:{','.join(missing)}")

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "manifest_type": INTAKE_TYPE,
        "pilot_id": str(profile["pilot_id"]),
        "profile_sha256": str(profile["content_sha256"]),
        "source_label": source_label,
        "approval": {
            "approval_id": approval_id,
            "approved_for_source_only_analysis": True,
            "customer_data_allowed": False,
            "runtime_credentials_allowed": False,
        },
        "scope": {
            "source_only": True,
            "read_only": True,
            "live_system_contact": False,
        },
        "files": files,
        "statistics": {
            "files": len(files),
            "bytes": total_bytes,
            "by_kind": dict(sorted(counts.items())),
        },
        "source_tree_sha256": canonical_hash({"files": files}),
        "limitations": [
            "Inventory proves bounded source custody, not source compilation or runtime behavior.",
            "No customer data, credentials, binaries, dumps, or live-system observations are accepted.",
        ],
    }
    payload["content_sha256"] = canonical_hash(payload)
    return payload


def validate_intake_manifest(
    manifest: Mapping[str, Any], profile: Mapping[str, Any], source_root: Path | None = None
) -> list[str]:
    errors: list[str] = []
    try:
        intake = _profile_intake(profile)
    except PilotError as error:
        return [str(error)]
    required = {
        "schema_version", "manifest_type", "pilot_id", "profile_sha256", "source_label",
        "approval", "scope", "files", "statistics", "source_tree_sha256", "limitations",
        "content_sha256",
    }
    missing = sorted(required - set(manifest))
    if missing:
        return [f"intake-missing-fields:{','.join(missing)}"]
    if manifest.get("schema_version") != SCHEMA_VERSION or manifest.get("manifest_type") != INTAKE_TYPE:
        errors.append("intake-contract-identity-invalid")
    if manifest.get("pilot_id") != profile.get("pilot_id") or manifest.get("profile_sha256") != profile.get("content_sha256"):
        errors.append("intake-profile-binding-invalid")
    if manifest.get("content_sha256") != canonical_hash(manifest, {"content_sha256"}):
        errors.append("intake-content-hash-invalid")
    approval = manifest.get("approval")
    if not isinstance(approval, dict) or approval.get("approved_for_source_only_analysis") is not True:
        errors.append("source-analysis-approval-missing")
    elif approval.get("customer_data_allowed") is not False or approval.get("runtime_credentials_allowed") is not False:
        errors.append("intake-approval-overclaims-source-only-boundary")
    scope = manifest.get("scope")
    if not isinstance(scope, dict) or scope != {"source_only": True, "read_only": True, "live_system_contact": False}:
        errors.append("intake-scope-is-not-source-only")
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        errors.append("intake-file-inventory-empty")
        files = []
    paths: set[str] = set()
    counts: Counter[str] = Counter()
    total_bytes = 0
    for index, item in enumerate(files):
        if not isinstance(item, dict):
            errors.append(f"intake-file-invalid:{index}")
            continue
        path = str(item.get("path", ""))
        if not path or path.startswith(("/", "\\")) or ".." in Path(path).parts or path in paths:
            errors.append(f"intake-file-path-invalid:{index}")
        paths.add(path)
        counts[str(item.get("kind", ""))] += 1
        total_bytes += int(item.get("bytes", 0))
        for field in ("logical_sha256", "raw_sha256"):
            if not _SHA256.fullmatch(str(item.get(field, ""))):
                errors.append(f"intake-file-hash-invalid:{index}:{field}")
    required_classes = {str(value) for value in intake.get("required_reference_classes", [])}
    approval_id = approval.get("approval_id") if isinstance(approval, dict) else None
    if approval_id == "repository-reference-fixture" and any(counts[kind] == 0 for kind in required_classes):
        errors.append("intake-required-source-class-missing")
    if manifest.get("source_tree_sha256") != canonical_hash({"files": files}):
        errors.append("intake-source-tree-hash-invalid")
    statistics = manifest.get("statistics")
    if not isinstance(statistics, dict) or statistics.get("files") != len(files) or statistics.get("bytes") != total_bytes or statistics.get("by_kind") != dict(sorted(counts.items())):
        errors.append("intake-statistics-invalid")
    if source_root is not None and not errors:
        try:
            rebuilt = build_intake_manifest(
                source_root,
                profile,
                approval_id=str(approval["approval_id"]),
                source_label=str(manifest["source_label"]),
            )
            if rebuilt != manifest:
                errors.append("intake-no-longer-matches-source-root")
        except (KeyError, PilotError) as error:
            errors.append(str(error))
    return sorted(set(errors))


_LIVE_REQUIREMENTS: dict[str, list[str]] = {
    "CICS": ["authorized test region and transaction", "CSD/CMCI observation", "signed terminal and side-effect capture"],
    "VSAM": ["approved non-production clusters and alternate indexes", "record-byte capture", "locking and recovery observation"],
    "IMS": ["authorized BMP region, DBD and PSB", "test database and JES output", "status, checkpoint and restart evidence"],
    "HLASM": ["assembler and binder listings", "load-module digest", "authorized Language Environment caller execution"],
    "PL/I": ["IBM Enterprise PL/I compile listing", "Db2 precompile and package bind", "actual PL/I-to-COBOL execution capture"],
    "Db2/Data": ["approved catalog and package projection", "bounded source-row profile", "log-based CDC, cutover and rollback observation"],
}


def build_preflight(project_root: Path, intake: Mapping[str, Any], profile: Mapping[str, Any]) -> dict[str, Any]:
    capability_path = project_root / "knowledge/capabilities/mainframe-readiness.json"
    appliance_path = project_root / "extensions/adapters/appliance/appliance.receipt.json"
    capability = load_json(capability_path)
    appliance = load_json(appliance_path)
    _require_content_hash(capability, "capability-projection")
    _require_content_hash(appliance, "collection-appliance")
    if intake.get("content_sha256") is None:
        raise PilotError("intake-content-hash-missing")

    technologies: list[dict[str, Any]] = []
    for item in capability.get("capabilities", []):
        technology = str(item.get("technology", ""))
        gates = {int(gate.get("gate", 0)): gate for gate in item.get("gates", [])}
        technologies.append(
            {
                "technology": technology,
                "gate_6": gates.get(6, {}).get("status"),
                "gate_7": gates.get(7, {}).get("status"),
                "gate_8": gates.get(8, {}).get("status"),
                "mainframe_equivalent": bool(item.get("mainframe_equivalent", False)),
                "required_live_evidence": _LIVE_REQUIREMENTS.get(technology, ["authorized original-system execution"]),
            }
        )
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "preflight_type": PREFLIGHT_TYPE,
        "pilot_id": str(profile["pilot_id"]),
        "intake_sha256": str(intake["content_sha256"]),
        "capability_sha256": str(capability["content_sha256"]),
        "appliance_sha256": str(appliance["content_sha256"]),
        "collection_mechanism": {
            "enterprise_mechanism_ready": appliance.get("enterprise_mechanism_ready") is True,
            "live_observed": appliance.get("live_observed") is True,
        },
        "global_requirements": [
            "written authorization naming non-production systems, programs and data",
            "customer evidence custodian identity and independent verifier identity",
            "approved TLS endpoints, certificates and out-of-band credentials",
            "customer-controlled evidence signing key and trusted time source",
            "approved test data, retention, redaction and evidence export policy",
            "approved execution, rollback, recovery and incident runbooks",
        ],
        "technologies": technologies,
        "gates": {
            "6_authorized_original_execution": "blocked",
            "7_independent_comparison": "mechanism_ready",
            "8_signed_equivalence": "blocked",
        },
        "ready_for_authorized_onboarding": True,
        "ready_for_gates_6_8": False,
        "mainframe_equivalent": False,
        "production_ready": False,
        "limitations": [
            "Preflight describes prerequisites; it is not an authorization or live observation.",
            "The collection appliance cannot promote source-only or simulated evidence to equivalence.",
        ],
    }
    payload["content_sha256"] = canonical_hash(payload)
    return payload


def validate_preflight(preflight: Mapping[str, Any], intake: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if preflight.get("schema_version") != SCHEMA_VERSION or preflight.get("preflight_type") != PREFLIGHT_TYPE:
        errors.append("preflight-contract-identity-invalid")
    if preflight.get("intake_sha256") != intake.get("content_sha256"):
        errors.append("preflight-intake-binding-invalid")
    if preflight.get("content_sha256") != canonical_hash(preflight, {"content_sha256"}):
        errors.append("preflight-content-hash-invalid")
    gates = preflight.get("gates")
    expected = {
        "6_authorized_original_execution": "blocked",
        "7_independent_comparison": "mechanism_ready",
        "8_signed_equivalence": "blocked",
    }
    if gates != expected:
        errors.append("preflight-live-gate-posture-invalid")
    if preflight.get("ready_for_gates_6_8") is not False or preflight.get("mainframe_equivalent") is not False or preflight.get("production_ready") is not False:
        errors.append("preflight-promotes-unproven-readiness")
    technologies = preflight.get("technologies")
    if not isinstance(technologies, list) or {item.get("technology") for item in technologies if isinstance(item, dict)} != set(_LIVE_REQUIREMENTS):
        errors.append("preflight-technology-checklist-incomplete")
    elif any(item.get("gate_6") != "blocked" or item.get("gate_8") != "blocked" or item.get("mainframe_equivalent") is not False for item in technologies):
        errors.append("preflight-technology-overclaim")
    return sorted(set(errors))


def _artifact_record(project_root: Path, item: Mapping[str, Any]) -> dict[str, Any]:
    relative = str(item.get("path", ""))
    path = project_root / relative
    if not path.is_file():
        raise PilotError(f"pilot-evidence-missing:{relative}")
    raw = path.read_bytes()
    raw_sha256 = hashlib.sha256(raw).hexdigest()
    if raw_sha256 != item.get("sha256"):
        raise PilotError(f"pilot-evidence-release-drift:{relative}")
    record: dict[str, Any] = {
        "id": str(item.get("id", "")),
        "role": str(item.get("role", "")),
        "path": relative,
        "sha256": raw_sha256,
        "bytes": len(raw),
    }
    if path.suffix == ".json":
        payload = load_json(path)
        if isinstance(payload.get("content_sha256"), str):
            record["content_sha256"] = payload["content_sha256"]
        for field in (
            "status", "development_ready", "enterprise_mechanism_ready", "live_observed",
            "mainframe_equivalent", "production_ready", "promotion_allowed",
        ):
            if field in payload:
                record[field] = payload[field]
    return record


def build_dossier(
    project_root: Path,
    intake: Mapping[str, Any],
    preflight: Mapping[str, Any],
    profile: Mapping[str, Any],
    compatibility: Mapping[str, Any],
) -> dict[str, Any]:
    _profile_intake(profile)
    compatibility_errors = validate_compatibility_policy(compatibility)
    if compatibility_errors:
        raise PilotError(compatibility_errors[0])
    artifacts = [_artifact_record(project_root, item) for item in profile.get("evidence_artifacts", [])]
    artifact_by_id = {item["id"]: item for item in artifacts}
    capability = load_json(project_root / "knowledge/capabilities/mainframe-readiness.json")
    composite = load_json(project_root / "knowledge/composite/estate.receipt.json")
    appliance = load_json(project_root / "extensions/adapters/appliance/appliance.receipt.json")
    rehearsal = load_json(project_root / "data-modernization/rehearsal/receipt.json")

    capabilities = [
        {
            "technology": item.get("technology"),
            "kind": item.get("capability_kind"),
            "discovery_ready": item.get("discovery_ready"),
            "development_ready": item.get("development_ready"),
            "mainframe_equivalent": item.get("mainframe_equivalent"),
            "gate_6": next((gate.get("status") for gate in item.get("gates", []) if gate.get("gate") == 6), None),
            "gate_8": next((gate.get("status") for gate in item.get("gates", []) if gate.get("gate") == 8), None),
        }
        for item in capability.get("capabilities", [])
    ]
    model_manifest = load_json(project_root / "factory/qualification/manifest.json")
    required_model_evaluations = len(model_manifest.get("workloads", [])) * int(model_manifest.get("policy", {}).get("minimum_runs_per_workload", 0))
    model_qualified = False
    readiness_checks = {
        "intake_valid": not validate_intake_manifest(intake, profile),
        "preflight_valid": not validate_preflight(preflight, intake),
        "compatibility_policy_valid": not compatibility_errors,
        "all_evidence_present": len(artifacts) == len(profile.get("evidence_artifacts", [])),
        "composite_estate_passed": (
            isinstance(composite.get("composite_graph_id"), str)
            and int(composite.get("statistics", {}).get("node_count", 0)) > 0
            and int(composite.get("statistics", {}).get("edge_count", 0)) > 0
        ),
        "development_capabilities_visible": all(item.get("development_ready") is True for item in capabilities),
        "collection_mechanism_ready": appliance.get("enterprise_mechanism_ready") is True,
        "migration_rehearsal_passed": rehearsal.get("status") == "passed",
        "model_qualification_not_overclaimed": model_qualified is False,
        "live_equivalence_not_overclaimed": all(item.get("mainframe_equivalent") is False for item in capabilities),
    }
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "dossier_type": DOSSIER_TYPE,
        "pilot_id": str(profile["pilot_id"]),
        "release": str(profile["release"]),
        "intake_sha256": str(intake["content_sha256"]),
        "preflight_sha256": str(preflight["content_sha256"]),
        "compatibility_policy_sha256": str(compatibility["content_sha256"]),
        "estate": {
            "graph_id": composite.get("composite_graph_id"),
            "composite_sha256": composite.get("content_sha256"),
            "nodes": composite.get("statistics", {}).get("node_count"),
            "relationships": composite.get("statistics", {}).get("edge_count"),
            "source_files": intake.get("statistics", {}).get("files"),
        },
        "capabilities": capabilities,
        "proofs": {
            "model_qualification": {
                "qualified": model_qualified,
                "required_independently_sealed_evaluations": required_model_evaluations,
                "committed_qualifying_evaluations": 0,
                "approved_successful_portfolio_run": False,
            },
            "migration_rehearsal": {
                "status": rehearsal.get("status"),
                "live_source_log_observed": False,
                "production_cutover_authorized": False,
            },
            "collection_appliance": {
                "enterprise_mechanism_ready": appliance.get("enterprise_mechanism_ready"),
                "live_observed": appliance.get("live_observed"),
            },
        },
        "evidence_artifacts": artifacts,
        "readiness_checks": readiness_checks,
        "pilot_ready": all(readiness_checks.values()),
        "mainframe_equivalent": False,
        "production_ready": False,
        "claim_unlocked": "LIGHTYEAR is ready for a governed source-only pilot and subsequent authorized mainframe evidence collection.",
        "claims_prohibited": [
            "LIGHTYEAR is production-ready.",
            "LIGHTYEAR has completed a live modernization.",
            "A model is qualified for autonomous modernization.",
            "Offline rehearsal proves customer Db2 CDC or cutover.",
        ],
        "limitations": [
            "All original-system execution and signed live-equivalence gates remain blocked.",
            "Development readiness applies only to explicitly bounded proof cells and supported subsets.",
            "The pilot dossier retains hashes and bounded summaries, not customer credentials or raw runtime responses.",
        ],
    }
    payload["content_sha256"] = canonical_hash(payload)
    if not payload["pilot_ready"]:
        raise PilotError("pilot-readiness-check-failed")
    return payload


def validate_dossier(
    dossier: Mapping[str, Any],
    intake: Mapping[str, Any],
    preflight: Mapping[str, Any],
    project_root: Path | None = None,
    profile: Mapping[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []
    if dossier.get("schema_version") != SCHEMA_VERSION or dossier.get("dossier_type") != DOSSIER_TYPE:
        errors.append("dossier-contract-identity-invalid")
    if dossier.get("intake_sha256") != intake.get("content_sha256") or dossier.get("preflight_sha256") != preflight.get("content_sha256"):
        errors.append("dossier-input-binding-invalid")
    if dossier.get("content_sha256") != canonical_hash(dossier, {"content_sha256"}):
        errors.append("dossier-content-hash-invalid")
    checks = dossier.get("readiness_checks")
    if not isinstance(checks, dict) or not checks or not all(value is True for value in checks.values()):
        errors.append("dossier-readiness-checks-invalid")
    if dossier.get("pilot_ready") is not True:
        errors.append("dossier-pilot-readiness-invalid")
    if dossier.get("mainframe_equivalent") is not False or dossier.get("production_ready") is not False:
        errors.append("dossier-overclaims-live-readiness")
    proofs = dossier.get("proofs")
    if not isinstance(proofs, dict) or proofs.get("model_qualification", {}).get("qualified") is not False:
        errors.append("dossier-overclaims-model-qualification")
    if profile is not None:
        expected = {
            (item.get("id"), item.get("path"), item.get("sha256"))
            for item in profile.get("evidence_artifacts", [])
            if isinstance(item, dict)
        }
        actual = {
            (item.get("id"), item.get("path"), item.get("sha256"))
            for item in dossier.get("evidence_artifacts", [])
            if isinstance(item, dict)
        }
        if actual != expected:
            errors.append("dossier-evidence-registry-incomplete-or-foreign")
    if project_root is not None:
        for item in dossier.get("evidence_artifacts", []):
            if not isinstance(item, dict):
                errors.append("dossier-artifact-record-invalid")
                continue
            path = project_root / str(item.get("path", ""))
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != item.get("sha256"):
                errors.append(f"dossier-artifact-drift:{item.get('id', 'unknown')}")
    return sorted(set(errors))


def validate_compatibility_policy(policy: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy.get("schema_version") != SCHEMA_VERSION or policy.get("policy_type") != "lightyear-pilot-compatibility-policy":
        errors.append("compatibility-policy-identity-invalid")
    if policy.get("content_sha256") != canonical_hash(policy, {"content_sha256"}):
        errors.append("compatibility-policy-content-hash-invalid")
    rules = policy.get("rules")
    if not isinstance(rules, dict) or rules.get("same_major_schema_versions") is not True or rules.get("reject_unknown_required_fields") is not True or rules.get("preserve_content_identities_on_upgrade") is not True:
        errors.append("compatibility-policy-rules-incomplete")
    formats = policy.get("formats")
    required = {INTAKE_TYPE, PREFLIGHT_TYPE, DOSSIER_TYPE}
    if not isinstance(formats, dict) or set(formats) != required or any(value != [SCHEMA_VERSION] for value in formats.values()):
        errors.append("compatibility-policy-format-matrix-invalid")
    if policy.get("production_ready") is not False:
        errors.append("compatibility-policy-overclaims-production-readiness")
    return sorted(set(errors))


def render_dossier_markdown(dossier: Mapping[str, Any]) -> str:
    estate = dossier["estate"]
    proofs = dossier["proofs"]
    rows = [
        "# LIGHTYEAR source-only pilot dossier",
        "",
        f"**Release:** {dossier['release']}  ",
        f"**Pilot:** `{dossier['pilot_id']}`  ",
        f"**Dossier identity:** `{dossier['content_sha256']}`",
        "",
        "## Executive result",
        "",
        "The governed source-only pilot is ready. This result proves deterministic offline intake,",
        "evidence assembly, verification, and mainframe-onboarding preflight. It does not prove live",
        "mainframe equivalence or production readiness.",
        "",
        "| Posture | Result |",
        "|---|---:|",
        f"| Source-only pilot ready | **{str(dossier['pilot_ready']).lower()}** |",
        f"| Model qualified | **{str(proofs['model_qualification']['qualified']).lower()}** |",
        f"| Mainframe equivalent | **{str(dossier['mainframe_equivalent']).lower()}** |",
        f"| Production ready | **{str(dossier['production_ready']).lower()}** |",
        "",
        "## Estate summary",
        "",
        f"The composite estate binds **{estate['nodes']} nodes** and **{estate['relationships']} relationships**",
        f"to **{estate['source_files']} approved source files** in this reference intake.",
        "",
        "## Capability gates",
        "",
        "| Capability | Kind | Discovery | Development | Gate 6 | Gate 8 | Equivalent |",
        "|---|---|---:|---:|---|---|---:|",
    ]
    for item in dossier["capabilities"]:
        rows.append(
            f"| {item['technology']} | {item['kind']} | {str(item['discovery_ready']).lower()} | "
            f"{str(item['development_ready']).lower()} | {item['gate_6']} | {item['gate_8']} | "
            f"{str(item['mainframe_equivalent']).lower()} |"
        )
    rows.extend(
        [
            "",
            "## Model and migration posture",
            "",
            f"Model qualification requires **{proofs['model_qualification']['required_independently_sealed_evaluations']}** ",
            "independently sealed evaluations plus an approved successful portfolio run. None are",
            "committed as current qualifying evidence, so no model is declared qualified.",
            "",
            "The data-movement rehearsal passed against deterministic Db2-shaped events, but no live",
            "Db2 log or production cutover authorization was observed.",
            "",
            "## Bound evidence",
            "",
            "| Role | Artifact | SHA-256 |",
            "|---|---|---|",
        ]
    )
    for item in dossier["evidence_artifacts"]:
        rows.append(f"| {item['role']} | `{item['path']}` | `{item['sha256']}` |")
    rows.extend(["", "## Prohibited claims", ""])
    rows.extend(f"- {claim}" for claim in dossier["claims_prohibited"])
    rows.extend(["", "## Limitations", ""])
    rows.extend(f"- {item}" for item in dossier["limitations"])
    return "\n".join(rows) + "\n"
