"""MS70 bounded iDempiere triage admission, calibration, and evidence assembly."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from lightyear_common.io import normalize_logical_source, source_hashes
from lightyear_factory.contracts import WorkOrder
from lightyear_factory.providers import BoundedModelProvider, ModelProvider

from .contracts import canonical_bytes, content_hash, seal
from .idempiere_comparison import (
    REPORT_PATH as STAGE2_REPORT_PATH,
    RECEIPT_PATH as STAGE2_RECEIPT_PATH,
    validate_stage2_artifacts,
)
from .idempiere_divergence import MANIFEST_PATH, PINNED_COMMIT, PROJECT_ID


VERSION = "1.0"
MILESTONE = 70
ROOT_PATH = Path("factory/idempiere-divergence-audit")
POLICY_PATH = ROOT_PATH / "triage-policy.json"
WORK_PACKAGE_PATH = ROOT_PATH / "stage3-work-package.json"
CALIBRATION_PATH = ROOT_PATH / "stage3-calibration.json"
COVERAGE_PATH = ROOT_PATH / "stage4-coverage.json"
DIVERGENCE_PATH = ROOT_PATH / "stage4-divergence-register.json"
INDETERMINATE_PATH = ROOT_PATH / "stage4-indeterminate-register.json"
PROVENANCE_PATH = ROOT_PATH / "stage4-provenance-register.json"
RECEIPT_PATH = ROOT_PATH / "stage4.receipt.json"
SCHEMA_PATH = Path("data-modernization/schema/idempiere-triage.schema.json")
CODE_PATHS = (
    "src/lightyear_data/idempiere_triage.py",
    "src/lightyear_data/idempiere_comparison.py",
    "src/lightyear_data/contracts.py",
    "src/lightyear_common/io.py",
    "src/lightyear_factory/contracts.py",
    "src/lightyear_factory/providers.py",
)

# Each reason occurs in both the frozen order-to-cash pilot and the remainder.
# One deterministic first match from each scope produces exactly twenty cases.
STRATA = (
    ("procedural-block", "procedural-block"),
    ("ordered-effect-alignment", "ordered-effect-alignment-required"),
    ("helper-catalog-effects", "helper-catalog-and-dependent-view-effects"),
    ("character-domain", "character-empty-string-length-and-collation-policy"),
    ("numeric-domain", "unbounded-or-nonportable-numeric-domain"),
    ("constraint-domain", "constraint-column-domain-required"),
    ("index-domain", "index-null-collation-and-column-domain-required"),
    ("unconsumed-syntax", "unconsumed-syntax"),
    ("unsupported-syntax", "unsupported-syntax"),
    ("dml-context", "dml-schema-trigger-and-coercion-context-required"),
)
CLASSIFICATIONS = (
    "deliberate-dialect-adaptation",
    "cosmetic-difference",
    "genuine-semantic-divergence",
    "indeterminate",
)
PROVENANCE_CLASSES = (
    "generation-path-present-per-pair-unclassified",
    "independent-maintenance-evidence-present",
    "not-classified",
)
PLANNER_EXCLUSIONS = (
    "native execution",
    "whole-file equivalence",
    "per-pair maintenance provenance",
    "source edits",
    "community contact",
)
CLAIMS = {
    "deterministic_sweep_complete": True,
    "bounded_sample_selected": True,
    "role_contract_calibration_complete": True,
    "live_model_triage_complete": False,
    "all_flagged_pairs_triaged": False,
    "audit_complete": False,
    "native_execution": False,
    "application_equivalence": False,
    "production_ready": False,
}


PLANNER_SCHEMA = {
    "type": "object",
    "properties": {
        "pair_id": {"type": "string"},
        "focus_id": {"type": "string"},
        "selected_evidence_ids": {"type": "array", "items": {"type": "string"}},
        "analyst_questions": {"type": "array", "items": {"type": "string"}},
        "excluded_claims": {"type": "array", "items": {"type": "string"}},
        "summary": {"type": "string"},
    },
    "required": [
        "pair_id", "focus_id", "selected_evidence_ids", "analyst_questions",
        "excluded_claims", "summary",
    ],
    "additionalProperties": False,
}

ANALYST_SCHEMA = {
    "type": "object",
    "properties": {
        "pair_id": {"type": "string"},
        "classification": {"enum": list(CLASSIFICATIONS)},
        "provenance_classification": {"enum": list(PROVENANCE_CLASSES)},
        "evidence_ids": {"type": "array", "items": {"type": "string"}},
        "reason_codes": {"type": "array", "items": {"type": "string"}},
        "summary": {"type": "string"},
        "required_evidence": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "pair_id", "classification", "provenance_classification", "evidence_ids",
        "reason_codes", "summary", "required_evidence",
    ],
    "additionalProperties": False,
}


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def triage_policy() -> dict[str, Any]:
    return seal({
        "schema_version": VERSION,
        "policy_id": "idda-bounded-triage-v1",
        "milestone": MILESTONE,
        "sample_size": 20,
        "selection": {
            "scopes": ["order-to-cash-pilot", "remaining-current-pairs"],
            "one_case_per_scope_and_stratum": True,
            "strata": [{"id": name, "reason_code": reason} for name, reason in STRATA],
            "tie_break": "first-pair-with-bilateral-sql-evidence-in-sealed-ms69-report-order",
        },
        "context": {
            "source": "pinned-source-ranges-from-ms69-findings-only",
            "immediate_context_lines": 2,
            "max_excerpt_lines_per_dialect": 48,
            "max_role_context_bytes": 80_000,
            "historical_migrations_in_scope": False,
            "additional_java_in_scope": False,
        },
        "model_budgets": {
            "planner": {
                "max_calls": 20,
                "max_input_tokens_per_call": 60_000,
                "max_output_tokens_per_call": 25_000,
                "max_context_bytes": 80_000,
                "max_cost_usd": 50.0,
            },
            "analyst": {
                "max_calls": 20,
                "max_input_tokens_per_call": 60_000,
                "max_output_tokens_per_call": 25_000,
                "max_context_bytes": 80_000,
                "max_cost_usd": 150.0,
            },
            "max_total_cost_usd": 200.0,
            "token_preflight_required": True,
        },
        "roles": {
            "planner": "selects only supplied evidence ids and narrows analyst questions",
            "analyst": "classifies the bounded difference and states missing evidence",
            "builder": "not-used-audit-does-not-generate-or-edit-upstream-source",
            "verifier": "deterministic-and-authoritative; preserves the MS69 semantic verdict",
        },
        "allowed_classifications": list(CLASSIFICATIONS),
        "verification_rules": [
            "model-output-cannot-change-ms69-semantic-verdict",
            "genuine-divergence-requires-ms69-divergent-verdict-and-declared-difference",
            "deliberate-adaptation-requires-the-bound-postgresql-helper-reason",
            "cosmetic-difference-requires-identical-logical-source",
            "all-evidence-identifiers-must-resolve-to-the-hydrated-case-context",
            "per-pair-maintenance-provenance-remains-unclassified-without-history-evidence",
        ],
        "publication": {
            "community_contact_authorized": False,
            "publish_zero-divergence_and-indeterminate-outcomes": True,
        },
    })


def _reasons(result: Mapping[str, Any]) -> list[str]:
    return sorted({
        reason
        for dialect in ("oracle", "postgresql")
        for segment in result["segments"][dialect]
        for reason in segment["reason_codes"]
    })


def _stratum(result: Mapping[str, Any]) -> tuple[str, str] | None:
    reasons = set(_reasons(result))
    return next(((name, reason) for name, reason in STRATA if reason in reasons), None)


def _focus_segment(result: Mapping[str, Any], dialect: str, reason: str) -> dict[str, Any]:
    segments = list(result["segments"][dialect])
    matches = [item for item in segments if reason in item["reason_codes"]]
    if not matches:
        matches = [item for item in segments if item["category"] != "administrative-excluded"]
    if not matches:
        raise ValueError(f"No SQL focus segment for {result['pair_id']} {dialect}")
    item = matches[0]
    return {
        "start_line": item["start_line"],
        "end_line": item["end_line"],
        "first_unit": item["first_unit"],
        "last_unit": item["last_unit"],
        "category": item["category"],
        "kind": item["kind"],
        "unit_hashes_sha256": item["unit_hashes_sha256"],
    }


def select_calibration_sample(
    manifest: Mapping[str, Any], report: Mapping[str, Any], pilot: Mapping[str, Any]
) -> list[dict[str, Any]]:
    manifest_pairs = {item["pair_id"]: item for item in manifest["pairs"]}
    pilot_ids = {item["pair_id"] for item in pilot["results"]}
    buckets: dict[tuple[str, str], list[Mapping[str, Any]]] = {
        (scope, name): []
        for name, _ in STRATA
        for scope in ("order-to-cash-pilot", "remaining-current-pairs")
    }
    for result in report["results"]:
        if result["verdict"] == "equivalent":
            continue
        if not all(
            any(
                segment["category"] != "administrative-excluded"
                for segment in result["segments"][dialect]
            )
            for dialect in ("oracle", "postgresql")
        ):
            continue
        matched = _stratum(result)
        if matched is None:
            continue
        scope = (
            "order-to-cash-pilot"
            if result["pair_id"] in pilot_ids
            else "remaining-current-pairs"
        )
        buckets[(scope, matched[0])].append(result)

    selected: list[dict[str, Any]] = []
    for index, (name, reason) in enumerate(STRATA, 1):
        for scope_index, scope in enumerate(
            ("order-to-cash-pilot", "remaining-current-pairs"), 1
        ):
            candidates = buckets[(scope, name)]
            if not candidates:
                raise ValueError(f"Missing MS70 calibration stratum: {scope}/{name}")
            result = candidates[0]
            pair = manifest_pairs[result["pair_id"]]
            case_number = (index - 1) * 2 + scope_index
            source = {
                dialect: {
                    "path": pair[dialect]["path"],
                    "lines": pair[dialect]["lines"],
                    "logical_sha256": pair[dialect]["logical_sha256"],
                }
                for dialect in ("oracle", "postgresql")
            }
            focus = {
                dialect: _focus_segment(result, dialect, reason)
                for dialect in ("oracle", "postgresql")
            }
            selected.append(seal({
                "case_id": f"ms70-{case_number:02d}",
                "pair_id": result["pair_id"],
                "scope": scope,
                "stratum": name,
                "stratum_reason_code": reason,
                "stage2_result_sha256": result["content_sha256"],
                "stage2_verdict": result["verdict"],
                "stage2_compatibility_class": result["compatibility_class"],
                "ordered_effects_aligned": result["ordered_effects_aligned"],
                "reason_codes": _reasons(result),
                "declared_difference_count": len(result["declared_differences"]),
                "content_identical": pair["content_identical"],
                "source": source,
                "focus": focus,
            }))
    if len(selected) != 20 or len({item["pair_id"] for item in selected}) != 20:
        raise ValueError("MS70 calibration sample must contain twenty unique pairs")
    return selected


def _reference_classifications(case: Mapping[str, Any]) -> list[str]:
    allowed = ["indeterminate"]
    if case["stratum"] == "helper-catalog-effects":
        allowed.insert(0, "deliberate-dialect-adaptation")
    if case["content_identical"]:
        allowed.insert(0, "cosmetic-difference")
    if case["stage2_verdict"] == "divergent" and case["declared_difference_count"]:
        allowed.insert(0, "genuine-semantic-divergence")
    return allowed


def _bindings(project_root: Path, docs: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    manifest = docs[MANIFEST_PATH.name]
    stage2 = docs[STAGE2_REPORT_PATH.name]
    return {
        "source_commit": manifest["source"]["commit"],
        "source_tree": manifest["source"]["tree"],
        "pairing_manifest_sha256": manifest["content_sha256"],
        "stage2_comparison_sha256": stage2["content_sha256"],
        "stage2_receipt_sha256": docs[STAGE2_RECEIPT_PATH.name]["content_sha256"],
        "triage_policy_sha256": triage_policy()["content_sha256"],
        "schema_logical_sha256": source_hashes(project_root / SCHEMA_PATH)[0],
        "implementation_logical_sha256": {
            path: source_hashes(project_root / path)[0] for path in CODE_PATHS
        },
    }


def build_stage3_artifacts(project_root: Path) -> dict[str, dict[str, Any]]:
    errors = validate_stage2_artifacts(project_root)
    if errors:
        raise ValueError("MS69 admission failed: " + ", ".join(errors))
    docs = {
        MANIFEST_PATH.name: _read(project_root / MANIFEST_PATH),
        STAGE2_REPORT_PATH.name: _read(project_root / STAGE2_REPORT_PATH),
        STAGE2_RECEIPT_PATH.name: _read(project_root / STAGE2_RECEIPT_PATH),
    }
    pilot = _read(project_root / ROOT_PATH / "stage2-pilot.json")
    bindings = _bindings(project_root, docs)
    sample = select_calibration_sample(docs[MANIFEST_PATH.name], docs[STAGE2_REPORT_PATH.name], pilot)
    work_package = seal({
        "schema_version": VERSION,
        "artifact_type": "lightyear-idempiere-triage-work-package",
        "milestone": MILESTONE,
        "project_id": PROJECT_ID,
        "bindings": bindings,
        "selection": triage_policy()["selection"],
        "cases": sample,
    })
    calibration_cases = [seal({
        "case_id": case["case_id"],
        "pair_id": case["pair_id"],
        "stratum": case["stratum"],
        "allowed_safe_classifications": _reference_classifications(case),
        "semantic_verdict_floor": case["stage2_verdict"],
        "provenance_floor": "generation-path-present-per-pair-unclassified",
        "planner_schema_validated": True,
        "analyst_schema_validated": True,
        "deterministic_verifier_authoritative": True,
    }) for case in sample]
    reference_counts = Counter(item["allowed_safe_classifications"][0] for item in calibration_cases)
    calibration = seal({
        "schema_version": VERSION,
        "artifact_type": "lightyear-idempiere-triage-calibration",
        "milestone": MILESTONE,
        "project_id": PROJECT_ID,
        "bindings": {**bindings, "work_package_sha256": work_package["content_sha256"]},
        "calibration_class": "deterministic-safe-floor-not-model-performance",
        "cases": calibration_cases,
        "statistics": {
            "cases": len(calibration_cases),
            "planner_contract_cases": len(calibration_cases),
            "analyst_contract_cases": len(calibration_cases),
            "builder_calls": 0,
            "model_calls": 0,
            "preferred_safe_classifications": {
                key: reference_counts[key] for key in CLASSIFICATIONS
            },
        },
    })
    report = docs[STAGE2_REPORT_PATH.name]
    selected_ids = {item["pair_id"] for item in sample}
    flagged = [item for item in report["results"] if item["verdict"] != "equivalent"]
    stage2_stats = report["statistics"]
    coverage = seal({
        "schema_version": VERSION,
        "artifact_type": "lightyear-idempiere-triage-coverage",
        "milestone": MILESTONE,
        "project_id": PROJECT_ID,
        "bindings": bindings,
        "pairing": docs[MANIFEST_PATH.name]["statistics"],
        "semantic_comparison": stage2_stats,
        "triage": {
            "flagged_pairs": len(flagged),
            "sampled_pairs": len(sample),
            "unsampled_flagged_pairs": len(flagged) - len(sample),
            "sampled_flagged_fraction": round(len(sample) / len(flagged), 8),
            "scope_counts": dict(sorted(Counter(item["scope"] for item in sample).items())),
            "stratum_counts": dict(sorted(Counter(item["stratum"] for item in sample).items())),
        },
    })
    divergence = seal({
        "schema_version": VERSION,
        "artifact_type": "lightyear-idempiere-divergence-register",
        "milestone": MILESTONE,
        "project_id": PROJECT_ID,
        "bindings": bindings,
        "entries": [],
        "statistics": {"proven_divergences": 0},
        "boundary": "A model classification cannot create a divergence absent a deterministic MS69 divergent verdict and declared difference.",
    })
    indeterminate_entries = [
        {
            "pair_id": item["pair_id"],
            "stage2_result_sha256": item["content_sha256"],
            "sampled_for_calibration": item["pair_id"] in selected_ids,
            "disposition": (
                "bounded-calibration-case" if item["pair_id"] in selected_ids
                else "outside-ms70-bounded-sample"
            ),
        }
        for item in flagged
    ]
    indeterminate = seal({
        "schema_version": VERSION,
        "artifact_type": "lightyear-idempiere-indeterminate-register",
        "milestone": MILESTONE,
        "project_id": PROJECT_ID,
        "bindings": bindings,
        "entries": indeterminate_entries,
        "statistics": {
            "indeterminate_pairs": len(indeterminate_entries),
            "sampled": len(selected_ids),
            "outside_sample": len(indeterminate_entries) - len(selected_ids),
        },
    })
    provenance = seal({
        "schema_version": VERSION,
        "artifact_type": "lightyear-idempiere-provenance-register",
        "milestone": MILESTONE,
        "project_id": PROJECT_ID,
        "bindings": bindings,
        "project_premise": {
            "conversion_layer_present": True,
            "dual_dialect_migration_log_writer_present": True,
            "independent_parallel_maintenance_proven": False,
            "generated_variants_ruled_out": False,
        },
        "entries": [{
            "pair_id": item["pair_id"],
            "classification": "generation-path-present-per-pair-unclassified",
            "history_evidence_admitted": False,
        } for item in sample],
        "statistics": {"sampled_pairs": len(sample), "per_pair_provenance_classified": 0},
    })
    artifact_hashes = {
        "work_package_sha256": work_package["content_sha256"],
        "calibration_sha256": calibration["content_sha256"],
        "coverage_sha256": coverage["content_sha256"],
        "divergence_register_sha256": divergence["content_sha256"],
        "indeterminate_register_sha256": indeterminate["content_sha256"],
        "provenance_register_sha256": provenance["content_sha256"],
    }
    receipt = seal({
        "schema_version": VERSION,
        "artifact_type": "lightyear-idempiere-triage-receipt",
        "milestone": MILESTONE,
        "project_id": PROJECT_ID,
        "status": "bounded-role-calibration-and-evidence-assembly-complete",
        "bindings": {**bindings, **artifact_hashes},
        "statistics": {
            "flagged_pairs": len(flagged),
            "calibration_cases": len(sample),
            "planner_contract_cases": len(sample),
            "analyst_contract_cases": len(sample),
            "model_calls": 0,
            "builder_calls": 0,
            "proven_divergences": 0,
            "indeterminate_pairs": len(flagged),
        },
        "station_usage": {
            "planner": "audit-specific-schema-calibrated-on-twenty-bounded-findings",
            "analyst": "audit-specific-schema-calibrated-on-twenty-bounded-findings",
            "builder": "not-used-audit-does-not-generate-or-edit-upstream-source",
            "verifier": "deterministic-authority-preserves-ms69-verdict-and-evidence-boundary",
        },
        "claims": CLAIMS,
        "community_contact": "not-authorized-and-not-performed",
    })
    return {
        POLICY_PATH.name: triage_policy(),
        WORK_PACKAGE_PATH.name: work_package,
        CALIBRATION_PATH.name: calibration,
        COVERAGE_PATH.name: coverage,
        DIVERGENCE_PATH.name: divergence,
        INDETERMINATE_PATH.name: indeterminate,
        PROVENANCE_PATH.name: provenance,
        RECEIPT_PATH.name: receipt,
    }


def _line_windows(start: int, end: int, total: int, cap: int) -> list[tuple[int, int]]:
    low, high = max(1, start - 2), min(total, end + 2)
    if high - low + 1 <= cap:
        return [(low, high)]
    left = cap // 2
    return [(low, low + left - 1), (high - (cap - left) + 1, high)]


def hydrate_case_context(source_root: Path, case: Mapping[str, Any]) -> dict[str, Any]:
    evidence: list[dict[str, Any]] = []
    for dialect in ("oracle", "postgresql"):
        source = case["source"][dialect]
        path = source_root / source["path"]
        raw = normalize_logical_source(path.read_bytes())
        if hashlib.sha256(raw).hexdigest() != source["logical_sha256"]:
            raise ValueError(f"MS70 source drift: {source['path']}")
        lines = raw.decode("utf-8", errors="strict").splitlines()
        focus = case["focus"][dialect]
        windows = _line_windows(
            focus["start_line"], focus["end_line"], len(lines),
            triage_policy()["context"]["max_excerpt_lines_per_dialect"],
        )
        for index, (start, end) in enumerate(windows, 1):
            text = "\n".join(lines[start - 1:end])
            evidence.append({
                "evidence_id": f"{case['case_id']}:{dialect}:{index}",
                "dialect": dialect,
                "path": source["path"],
                "line_range": [start, end],
                "focus_line_range": [focus["start_line"], focus["end_line"]],
                "logical_source_sha256": source["logical_sha256"],
                "excerpt_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "text": text,
            })
    context = seal({
        "schema_version": VERSION,
        "context_type": "lightyear-idempiere-bounded-triage-context",
        "pair_id": case["pair_id"],
        "case_id": case["case_id"],
        "stratum": case["stratum"],
        "stage2_verdict": case["stage2_verdict"],
        "reason_codes": case["reason_codes"],
        "evidence": evidence,
        "limitations": [
            "Only the implicated source range and immediate context are present.",
            "No historical migration, database state, runtime result, or additional Java source is present.",
        ],
    })
    size = len(canonical_bytes(context))
    if size > triage_policy()["context"]["max_role_context_bytes"]:
        raise ValueError(f"MS70 role context exceeds 80000 bytes: {case['case_id']}")
    return {**context, "context_bytes": size}


def _role_order(work_package: Mapping[str, Any], role: str) -> WorkOrder:
    policy = triage_policy()["model_budgets"][role]
    paths = sorted({
        source["path"]
        for case in work_package["cases"]
        for source in case["source"].values()
    })
    return WorkOrder.from_dict({
        "schema_version": "1.0",
        "id": f"idempiere-ms70-{role}",
        "title": f"iDempiere MS70 bounded {role}",
        "goal": "Classify only the twenty admitted MS69 findings without changing their semantic verdicts.",
        "non_goals": [
            "edit source", "use Builder", "triage unsampled pairs", "claim native execution",
            "claim application equivalence", "contact the iDempiere community",
        ],
        "scope": {"allowed_paths": paths, "graph_node_ids": []},
        "acceptance": {
            "baseline_first": True,
            "max_attempts": 1,
            "gates": [{
                "id": "deterministic-ms70-verifier",
                "command": ["idempiere-divergence-audit", "verify-triage"],
                "timeout_seconds": 300,
                "expose_output_to_builder": False,
            }],
        },
        "policy": {
            "audience": "implementer",
            "allow_network": True,
            "max_files_changed": 1,
            "max_patch_bytes": 1,
            "max_changed_lines": 1,
            "max_context_bytes": policy["max_context_bytes"],
            "max_file_bytes": policy["max_context_bytes"],
            "max_model_calls": policy["max_calls"],
            "max_model_input_bytes": 2_000_000,
            "max_model_output_bytes": 1_000_000,
            "max_model_tokens": 1_700_000,
            "max_model_cost_usd": policy["max_cost_usd"],
            "max_elapsed_seconds": 7_200,
        },
        "metadata": {
            "milestone": MILESTONE,
            "work_package_sha256": work_package["content_sha256"],
            "builder_enabled": False,
        },
    })


def _verify_planner(case: Mapping[str, Any], context: Mapping[str, Any], plan: Mapping[str, Any]) -> None:
    available = {item["evidence_id"] for item in context["evidence"]}
    selected = plan.get("selected_evidence_ids", [])
    if plan.get("pair_id") != case["pair_id"] or plan.get("focus_id") != case["case_id"]:
        raise ValueError("MS70 planner identity mismatch")
    if not selected or not set(selected) <= available:
        raise ValueError("MS70 planner selected unknown or empty evidence")
    if not plan.get("analyst_questions"):
        raise ValueError("MS70 planner supplied no analyst question")
    if set(plan.get("excluded_claims", [])) != set(PLANNER_EXCLUSIONS):
        raise ValueError("MS70 planner changed the required exclusions")


def verify_analyst_result(
    case: Mapping[str, Any], plan: Mapping[str, Any], analysis: Mapping[str, Any]
) -> dict[str, Any]:
    selected = set(plan["selected_evidence_ids"])
    evidence = analysis.get("evidence_ids", [])
    reasons = analysis.get("reason_codes", [])
    if analysis.get("pair_id") != case["pair_id"]:
        raise ValueError("MS70 analyst identity mismatch")
    if not evidence or not set(evidence) <= selected:
        raise ValueError("MS70 analyst cited unknown or empty evidence")
    if not reasons or not set(reasons) <= set(case["reason_codes"]):
        raise ValueError("MS70 analyst cited unknown or empty reason codes")
    proposed = analysis["classification"]
    accepted = proposed in _reference_classifications(case)
    verified = proposed if accepted else "indeterminate"
    return seal({
        "case_id": case["case_id"],
        "pair_id": case["pair_id"],
        "proposed_classification": proposed,
        "verified_classification": verified,
        "classification_accepted": accepted,
        "semantic_verdict": case["stage2_verdict"],
        "semantic_verdict_changed": False,
        "provenance_classification": "generation-path-present-per-pair-unclassified",
        "verifier_reason_codes": (
            [] if accepted else ["analyst-classification-not-deterministically-supported"]
        ),
    })


def run_model_triage(
    project_root: Path,
    source_root: Path,
    planner_provider: ModelProvider,
    analyst_provider: ModelProvider,
) -> dict[str, Any]:
    errors = validate_stage3_artifacts(project_root, source_root=source_root)
    if errors:
        raise ValueError("MS70 admission failed: " + ", ".join(errors))
    work_package = _read(project_root / WORK_PACKAGE_PATH)
    for provider, role in ((planner_provider, "planner"), (analyst_provider, "analyst")):
        if provider.provider_id == "openai-responses":
            if not bool(getattr(provider, "token_preflight", False)):
                raise ValueError(f"MS70 {role} requires input-token preflight")
            if int(getattr(provider, "max_input_tokens_per_call", 0)) > 60_000:
                raise ValueError(f"MS70 {role} input-token cap exceeds 60000")
            if int(getattr(provider, "max_output_tokens", 0)) > 25_000:
                raise ValueError(f"MS70 {role} output-token cap exceeds 25000")
            if float(getattr(provider, "input_usd_per_million", 0.0)) <= 0 or float(
                getattr(provider, "output_usd_per_million", 0.0)
            ) <= 0:
                raise ValueError(f"MS70 {role} requires explicit nonzero pricing")
    planner = BoundedModelProvider(planner_provider, _role_order(work_package, "planner"))
    analyst = BoundedModelProvider(analyst_provider, _role_order(work_package, "analyst"))
    records = []
    call_evidence = []
    for case in work_package["cases"]:
        context = hydrate_case_context(source_root, case)
        planned = planner.complete(
            "planner",
            "Select only supplied evidence ids. Narrow the analyst to the implicated construct and immediate context. Keep native execution, whole-file equivalence, provenance certainty, source edits, and community contact excluded.",
            {"case": case, "context": context},
            PLANNER_SCHEMA,
        )
        call_evidence.append(planned.evidence)
        _verify_planner(case, context, planned.content)
        analyzed = analyst.complete(
            "failure_analyst",
            "Classify the bounded dialect difference as deliberate adaptation, cosmetic difference, genuine semantic divergence, or indeterminate. Cite only planner-selected evidence and supplied reason codes. Do not change the MS69 semantic verdict or claim per-pair maintenance provenance without history evidence.",
            {"case": case, "plan": planned.content, "context": context},
            ANALYST_SCHEMA,
        )
        call_evidence.append(analyzed.evidence)
        records.append(seal({
            "case_id": case["case_id"],
            "pair_id": case["pair_id"],
            "plan": planned.content,
            "analysis": analyzed.content,
            "verification": verify_analyst_result(case, planned.content, analyzed.content),
        }))
    planner_summary, analyst_summary = planner.summary(), analyst.summary()
    live_models = all(
        value == "openai-responses" for value in (planner.provider_id, analyst.provider_id)
    ) and all(
        int(summary["input_token_preflight_calls"]) == 20
        and bool(summary["cost_estimate_available"])
        for summary in (planner_summary, analyst_summary)
    )
    return seal({
        "schema_version": VERSION,
        "artifact_type": "lightyear-idempiere-model-triage-run",
        "milestone": MILESTONE,
        "project_id": PROJECT_ID,
        "work_package_sha256": work_package["content_sha256"],
        "records": records,
        "model_call_evidence": call_evidence,
        "intelligence": {"planner": planner_summary, "analyst": analyst_summary},
        "statistics": {
            "cases": len(records),
            "model_calls": planner_summary["calls"] + analyst_summary["calls"],
            "builder_calls": 0,
            "live_model_performance_evidence": live_models,
            "verified_classifications": dict(sorted(Counter(
                item["verification"]["verified_classification"] for item in records
            ).items())),
        },
        "claims": {
            **CLAIMS,
            "live_model_triage_complete": live_models and len(records) == 20,
        },
    })


def validate_stage3_artifacts(
    project_root: Path,
    *,
    source_root: Path | None = None,
    artifacts: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[str]:
    errors = validate_stage2_artifacts(project_root, source_root=source_root)
    names = (
        POLICY_PATH.name, WORK_PACKAGE_PATH.name, CALIBRATION_PATH.name, COVERAGE_PATH.name,
        DIVERGENCE_PATH.name, INDETERMINATE_PATH.name, PROVENANCE_PATH.name, RECEIPT_PATH.name,
    )
    try:
        actual = dict(artifacts or {name: _read(project_root / ROOT_PATH / name) for name in names})
        expected = build_stage3_artifacts(project_root)
        for name in names:
            if actual[name].get("content_sha256") != content_hash(dict(actual[name])):
                errors.append(f"stage3-content-hash-invalid:{name}")
            if actual[name] != expected[name]:
                errors.append(f"stage3-artifact-drift:{name}")
        receipt = actual[RECEIPT_PATH.name]
        if receipt.get("claims") != CLAIMS:
            errors.append("stage3-unsupported-claim")
        stats = receipt.get("statistics", {})
        if stats.get("model_calls") != 0 or stats.get("builder_calls") != 0:
            errors.append("stage3-committed-agent-usage-invalid")
        work_package = actual[WORK_PACKAGE_PATH.name]
        if len(work_package.get("cases", [])) != 20:
            errors.append("stage3-sample-size-invalid")
        if source_root is not None:
            for case in work_package["cases"]:
                hydrate_case_context(source_root, case)
    except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError) as exc:
        errors.append("stage3-validation-error:" + type(exc).__name__)
    return sorted(set(errors))
