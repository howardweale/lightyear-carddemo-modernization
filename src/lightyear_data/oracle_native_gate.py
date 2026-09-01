from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from .contracts import content_hash, seal, verify_signature
from .oracle_core_sql import validate_oracle_core_sql_artifacts
from .oracle_coverage import build_behavior_catalog
from .oracle_plsql import validate_oracle_plsql_artifacts
from .oracle_schema_structured import validate_oracle_schema_structured_artifacts
from .oracle_transaction_cdc import validate_oracle_transaction_cdc_artifacts


OUTPUT_ROOT = Path("data-modernization/oracle-native-execution-gate")
RELEASE = "0.51.0"
VERSION_LANES = ("19c", "26ai")
RECEIPT_TYPE = "lightyear-oracle-native-execution-receipt"
MANIFEST_TYPE = "lightyear-oracle-native-case-manifest"
HEX_64 = re.compile(r"^[0-9a-f]{64}$")
SAFE_IDENTITY = re.compile(r"^[A-Za-z0-9._:@/+,-]{1,256}$")

CORPUS_SOURCES = (
    ("core-sql", Path("data-modernization/oracle-core-sql-coverage/core-sql-corpus.json")),
    ("plsql", Path("data-modernization/oracle-plsql-coverage/plsql-corpus.json")),
    (
        "transaction-cdc",
        Path("data-modernization/oracle-transaction-cdc-coverage/transaction-cdc-corpus.json"),
    ),
    (
        "schema-structured",
        Path(
            "data-modernization/oracle-schema-structured-coverage/"
            "schema-structured-corpus.json"
        ),
    ),
)

REQUIRED_DATABASE_IDENTITY_FIELDS = (
    "database_lane",
    "version_full",
    "version_banner_sha256",
    "dbid_sha256",
    "container_name",
    "character_set",
    "national_character_set",
    "database_timezone",
    "option_set_sha256",
)
REQUIRED_SESSION_FIELDS = (
    "current_schema",
    "current_edition",
    "session_timezone",
    "nls_date_format",
    "nls_timestamp_format",
    "nls_numeric_characters",
    "nls_sort",
    "nls_comp",
    "isolation_level",
)
REQUIRED_RESULT_FIELDS = (
    "case_id",
    "behavior_id",
    "status",
    "bounded_expectation_sha256",
    "harness_sql_sha256",
    "observed_result_sha256",
    "diagnostic_codes",
    "started_at",
    "completed_at",
)
REQUIRED_RECEIPT_FIELDS = (
    "run_id",
    "runner_identity",
    "raw_stdout_sha256",
    "raw_stderr_sha256",
)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _corpora(project_root: Path) -> list[tuple[str, Path, dict[str, Any]]]:
    return [
        (name, relative, _read_json(project_root / relative))
        for name, relative in CORPUS_SOURCES
    ]


def _expectation_sha(value: Any) -> str:
    return content_hash({"expected": value})


def build_native_case_manifest(project_root: Path) -> dict[str, Any]:
    catalog = build_behavior_catalog(project_root)
    behavior_by_id = {item["id"]: item for item in catalog["behaviors"]}
    cases: list[dict[str, Any]] = []
    corpus_bindings = []
    for tranche, relative, corpus in _corpora(project_root):
        corpus_bindings.append(
            {
                "tranche": tranche,
                "path": relative.as_posix(),
                "content_sha256": corpus["content_sha256"],
                "case_count": corpus["case_count"],
                "status": corpus["status"],
            }
        )
        for result in corpus["results"]:
            behavior = behavior_by_id[result["behavior_id"]]
            cases.append(
                {
                    "case_id": result["id"],
                    "behavior_id": result["behavior_id"],
                    "domain_id": result["domain_id"],
                    "topic": result["topic"],
                    "focus": result["focus"],
                    "dimension": result["dimension"],
                    "documentation": behavior["documentation"],
                    "bounded_expectation_sha256": _expectation_sha(result["expected"]),
                    "bounded_corpus_status": result["status"],
                    "native_lanes": [
                        {
                            "database_lane": lane,
                            "harness_path": f"cases/{lane}/{result['id']}.sql",
                            "harness_status": "required-not-materialized",
                            "execution_status": "not-executed",
                        }
                        for lane in VERSION_LANES
                    ],
                    "native_oracle_verified": False,
                    "target_equivalent": False,
                }
            )
    cases.sort(key=lambda item: item["case_id"])
    return seal(
        {
            "schema_version": "1.0",
            "manifest_type": MANIFEST_TYPE,
            "release": RELEASE,
            "catalog_id": catalog["catalog_id"],
            "catalog_sha256": catalog["content_sha256"],
            "version_lanes": list(VERSION_LANES),
            "corpus_bindings": corpus_bindings,
            "behavior_count": len({item["behavior_id"] for item in cases}),
            "case_count": len(cases),
            "required_native_case_execution_count": len(cases) * len(VERSION_LANES),
            "materialized_harness_count": 0,
            "native_executed_case_count": 0,
            "native_verified_behavior_count": 0,
            "cases": cases,
            "native_oracle_execution_observed": False,
            "native_oracle_conformance": False,
            "target_equivalence_observed": False,
            "production_ready": False,
        }
    )


def build_execution_contract(manifest: Mapping[str, Any]) -> dict[str, Any]:
    return seal(
        {
            "schema_version": "1.0",
            "contract_type": "lightyear-oracle-native-execution-contract",
            "release": RELEASE,
            "manifest_sha256": manifest["content_sha256"],
            "version_lanes": list(VERSION_LANES),
            "transport": {
                "client": "sqlplus-or-sqlcl",
                "authentication": "external-wallet-alias-only",
                "username_or_password_arguments_allowed": False,
                "credential_files_allowed_in_repository": False,
                "stdout_persisted": False,
                "stderr_persisted": False,
                "raw_output_policy": "hash-and-redact-after-marker-validation",
            },
            "required_database_identity_fields": list(REQUIRED_DATABASE_IDENTITY_FIELDS),
            "required_session_fields": list(REQUIRED_SESSION_FIELDS),
            "required_receipt_fields": list(REQUIRED_RECEIPT_FIELDS),
            "required_result_fields": list(REQUIRED_RESULT_FIELDS),
            "result_statuses": ["passed-native", "failed-native", "blocked-native"],
            "result_marker": "LY_NATIVE_RESULT=<base64url-canonical-json>",
            "receipt_security": {
                "content_addressed": True,
                "signature_algorithm": "hmac-sha256",
                "verification_key_source": "runtime-environment-only",
                "unsigned_receipts_admitted": False,
            },
            "conformance_rule": (
                "A database lane is conformant only when all 2,000 manifest cases have unique, "
                "signed, passed-native results bound to one database identity and the exact "
                "materialized SQL harness hashes."
            ),
            "target_equivalence_rule": (
                "Native Oracle conformance does not establish source-to-target equivalence."
            ),
        }
    )


def build_run_pack_index(manifest: Mapping[str, Any]) -> dict[str, Any]:
    counts = Counter(item["domain_id"] for item in manifest["cases"])
    batches = [
        {
            "batch_id": f"oracle-{lane}-{domain}",
            "database_lane": lane,
            "domain_id": domain,
            "case_count": count,
            "required_harness_count": count,
            "materialized_harness_count": 0,
            "execution_status": "blocked-harness-and-authorized-database-required",
        }
        for lane in VERSION_LANES
        for domain, count in sorted(counts.items())
    ]
    return seal(
        {
            "schema_version": "1.0",
            "index_type": "lightyear-oracle-native-run-pack-index",
            "release": RELEASE,
            "manifest_sha256": manifest["content_sha256"],
            "batch_count": len(batches),
            "required_native_case_execution_count": manifest[
                "required_native_case_execution_count"
            ],
            "materialized_harness_count": 0,
            "native_executed_case_count": 0,
            "batches": batches,
            "bootstrap_harness": {
                "path": "data-modernization/oracle-dialect-conformance/native-oracle-fixtures.sql",
                "fixture_completion_marker_count": 8,
                "case_result_marker_count": 0,
                "eligible_as_catalog_native_case_evidence": False,
                "reason": "fixture completion markers are not per-case native observations",
            },
        }
    )


def build_readiness_receipt(
    manifest: Mapping[str, Any],
    contract: Mapping[str, Any],
    index: Mapping[str, Any],
) -> dict[str, Any]:
    return seal(
        {
            "schema_version": "1.0",
            "receipt_type": "lightyear-oracle-native-execution-gate-readiness",
            "release": RELEASE,
            "manifest_sha256": manifest["content_sha256"],
            "execution_contract_sha256": contract["content_sha256"],
            "run_pack_index_sha256": index["content_sha256"],
            "catalog_behavior_count": 500,
            "catalog_case_count": 2000,
            "required_native_case_execution_count": 4000,
            "materialized_harness_count": 0,
            "native_executed_case_count": 0,
            "native_verified_behavior_count": 0,
            "target_equivalent_behavior_count": 0,
            "gate_status": "ready-to-admit-evidence-not-ready-to-claim-conformance",
            "gates": [
                {"id": "bounded-catalog-dependency", "status": "passed"},
                {"id": "case-to-version-manifest", "status": "passed"},
                {"id": "database-and-session-identity-contract", "status": "passed"},
                {"id": "credential-isolation-policy", "status": "passed"},
                {"id": "signed-receipt-verifier", "status": "passed"},
                {"id": "native-sql-harness-materialization", "status": "blocked"},
                {"id": "authorized-oracle-19c-execution", "status": "blocked"},
                {"id": "authorized-oracle-26ai-execution", "status": "blocked"},
            ],
            "claim_statement": (
                "All 2,000 bounded catalog cases are mapped to 4,000 required 19c/26ai native "
                "executions under a signed evidence contract; no catalog-native execution has "
                "occurred and native Oracle and target-equivalent counts remain zero."
            ),
            "native_oracle_execution_observed": False,
            "native_oracle_conformance": False,
            "target_equivalence_observed": False,
            "idempiere_application_equivalence": False,
            "cloudbank_mapping_complete": False,
            "migration_complete": False,
            "production_ready": False,
        }
    )


def native_gate_matrix_markdown(
    manifest: Mapping[str, Any], index: Mapping[str, Any]
) -> str:
    counts = Counter(item["domain_id"] for item in manifest["cases"])
    rows = "\n".join(
        f"| {domain} | {count} | {count * 2} | 0 |"
        for domain, count in sorted(counts.items())
    )
    return f"""# Oracle native execution admission matrix

MS #51 converts the completed bounded catalog into a governed two-version native execution
contract. It does not claim that the required SQL harnesses or database runs already exist.

| Domain | Catalog cases | Required 19c + 26ai runs | Native runs admitted |
|---|---:|---:|---:|
{rows}
| **Total** | **{manifest['case_count']}** | **{manifest['required_native_case_execution_count']}** | **0** |

The index defines {index['batch_count']} version/domain batches. Every admitted native result must
bind the exact case expectation, SQL harness hash, database identity, session settings, diagnostics,
timestamps, runner identity, and an environment-key signature. The earlier eight-fixture SQL file
has completion markers but no per-case native observations, so it remains ineligible as catalog
native evidence.

Native SQL harness materialization, authorized 19c and 26ai execution, target equivalence,
iDempiere application equivalence, CloudBank mapping, migration completion, and production
readiness remain blocked.
"""


def build_oracle_native_gate_artifacts(project_root: Path) -> dict[str, Any]:
    manifest = build_native_case_manifest(project_root)
    contract = build_execution_contract(manifest)
    index = build_run_pack_index(manifest)
    receipt = build_readiness_receipt(manifest, contract, index)
    return {
        "native-case-manifest.json": manifest,
        "execution-contract.json": contract,
        "run-pack-index.json": index,
        "readiness.receipt.json": receipt,
        "execution-matrix.md": native_gate_matrix_markdown(manifest, index),
    }


def _prior_errors(project_root: Path) -> list[str]:
    validators = (
        validate_oracle_core_sql_artifacts,
        validate_oracle_plsql_artifacts,
        validate_oracle_transaction_cdc_artifacts,
        validate_oracle_schema_structured_artifacts,
    )
    return sorted(
        {
            f"oracle-native-gate-dependency:{error}"
            for validator in validators
            for error in validator(project_root)
        }
    )


def validate_oracle_native_gate_artifacts(project_root: Path) -> list[str]:
    errors = _prior_errors(project_root)
    expected = build_oracle_native_gate_artifacts(project_root)
    output_root = project_root / OUTPUT_ROOT
    actual_receipt: Mapping[str, Any] | None = None
    for name, payload in expected.items():
        path = output_root / name
        if not path.is_file():
            errors.append(f"oracle-native-gate-artifact-missing:{name}")
            continue
        actual: Any = path.read_text(encoding="utf-8")
        if name.endswith(".json"):
            actual = json.loads(actual)
        if name == "readiness.receipt.json" and isinstance(actual, Mapping):
            actual_receipt = actual
        if actual != payload:
            errors.append(f"oracle-native-gate-artifact-drift:{name}")
    manifest = expected["native-case-manifest.json"]
    ids = [item["case_id"] for item in manifest["cases"]]
    behavior_ids = {item["behavior_id"] for item in manifest["cases"]}
    if len(ids) != 2000 or len(ids) != len(set(ids)):
        errors.append("oracle-native-gate-case-set-invalid")
    if len(behavior_ids) != 500:
        errors.append("oracle-native-gate-behavior-set-invalid")
    if manifest["required_native_case_execution_count"] != 4000:
        errors.append("oracle-native-gate-execution-target-invalid")
    if any(
        lane["harness_status"] != "required-not-materialized"
        or lane["execution_status"] != "not-executed"
        for item in manifest["cases"]
        for lane in item["native_lanes"]
    ):
        errors.append("oracle-native-gate-premature-native-state")
    receipt = actual_receipt or expected["readiness.receipt.json"]
    for name in (
        "native_oracle_execution_observed",
        "native_oracle_conformance",
        "target_equivalence_observed",
        "idempiere_application_equivalence",
        "cloudbank_mapping_complete",
        "migration_complete",
        "production_ready",
    ):
        if receipt.get(name) is not False:
            errors.append(f"oracle-native-gate-overclaim:{name}")
    if receipt.get("content_sha256") != content_hash(dict(receipt)):
        errors.append("oracle-native-gate-receipt-integrity-invalid")
    return sorted(set(errors))


def validate_native_execution_receipt(
    project_root: Path,
    receipt: Mapping[str, Any],
    verification_key: str,
) -> list[str]:
    errors: list[str] = []
    manifest = build_native_case_manifest(project_root)
    manifest_cases = {item["case_id"]: item for item in manifest["cases"]}
    if receipt.get("receipt_type") != RECEIPT_TYPE:
        errors.append("oracle-native-receipt-type-invalid")
    if receipt.get("release") != RELEASE:
        errors.append("oracle-native-receipt-release-invalid")
    if receipt.get("manifest_sha256") != manifest["content_sha256"]:
        errors.append("oracle-native-receipt-manifest-binding-invalid")
    if receipt.get("content_sha256") != content_hash(dict(receipt)):
        errors.append("oracle-native-receipt-integrity-invalid")
    if not verification_key or not verify_signature(dict(receipt), verification_key):
        errors.append("oracle-native-receipt-signature-invalid")

    for name in ("run_id", "runner_identity"):
        value = receipt.get(name)
        if not isinstance(value, str) or not SAFE_IDENTITY.fullmatch(value):
            errors.append(f"oracle-native-receipt-provenance-invalid:{name}")
    for name in ("raw_stdout_sha256", "raw_stderr_sha256"):
        if not HEX_64.fullmatch(str(receipt.get(name, ""))):
            errors.append(f"oracle-native-receipt-raw-stream-hash-invalid:{name}")

    database = receipt.get("database_identity")
    if not isinstance(database, Mapping):
        errors.append("oracle-native-receipt-database-identity-missing")
        database = {}
    for name in REQUIRED_DATABASE_IDENTITY_FIELDS:
        value = database.get(name)
        if not isinstance(value, str) or not value or not SAFE_IDENTITY.fullmatch(value):
            errors.append(f"oracle-native-receipt-database-identity-invalid:{name}")
    lane = database.get("database_lane")
    if lane not in VERSION_LANES:
        errors.append("oracle-native-receipt-lane-invalid")
    version_full = str(database.get("version_full", ""))
    if lane == "19c" and not version_full.startswith("19"):
        errors.append("oracle-native-receipt-version-lane-mismatch")
    if lane == "26ai" and not version_full.startswith("26"):
        errors.append("oracle-native-receipt-version-lane-mismatch")
    for name in (
        "version_banner_sha256",
        "dbid_sha256",
        "option_set_sha256",
    ):
        if not HEX_64.fullmatch(str(database.get(name, ""))):
            errors.append(f"oracle-native-receipt-database-hash-invalid:{name}")

    session = receipt.get("session_settings")
    if not isinstance(session, Mapping):
        errors.append("oracle-native-receipt-session-settings-missing")
        session = {}
    for name in REQUIRED_SESSION_FIELDS:
        value = session.get(name)
        if not isinstance(value, str) or not value or len(value) > 256:
            errors.append(f"oracle-native-receipt-session-setting-invalid:{name}")

    security = receipt.get("security")
    if not isinstance(security, Mapping):
        errors.append("oracle-native-receipt-security-missing")
        security = {}
    required_security = {
        "external_wallet_authentication": True,
        "credentials_in_arguments": False,
        "credentials_persisted": False,
        "raw_stdout_persisted": False,
        "raw_stderr_persisted": False,
    }
    for name, value in required_security.items():
        if security.get(name) is not value:
            errors.append(f"oracle-native-receipt-security-invalid:{name}")

    results = receipt.get("results")
    if not isinstance(results, list) or not results:
        errors.append("oracle-native-receipt-results-missing")
        results = []
    seen: set[str] = set()
    passed_behaviors: set[str] = set()
    for result in results:
        if not isinstance(result, Mapping):
            errors.append("oracle-native-receipt-result-invalid")
            continue
        for name in REQUIRED_RESULT_FIELDS:
            if name not in result:
                errors.append(f"oracle-native-receipt-result-field-missing:{name}")
        case_id = str(result.get("case_id", ""))
        case = manifest_cases.get(case_id)
        if case is None:
            errors.append(f"oracle-native-receipt-case-unknown:{case_id}")
            continue
        if case_id in seen:
            errors.append(f"oracle-native-receipt-case-duplicate:{case_id}")
        seen.add(case_id)
        if result.get("behavior_id") != case["behavior_id"]:
            errors.append(f"oracle-native-receipt-behavior-binding-invalid:{case_id}")
        if result.get("bounded_expectation_sha256") != case["bounded_expectation_sha256"]:
            errors.append(f"oracle-native-receipt-expectation-binding-invalid:{case_id}")
        if result.get("status") not in {
            "passed-native",
            "failed-native",
            "blocked-native",
        }:
            errors.append(f"oracle-native-receipt-status-invalid:{case_id}")
        if result.get("status") == "passed-native":
            passed_behaviors.add(case["behavior_id"])
        for name in ("harness_sql_sha256", "observed_result_sha256"):
            if not HEX_64.fullmatch(str(result.get(name, ""))):
                errors.append(f"oracle-native-receipt-result-hash-invalid:{case_id}:{name}")
        diagnostics = result.get("diagnostic_codes")
        if not isinstance(diagnostics, list) or any(
            not isinstance(value, str) or len(value) > 64 for value in diagnostics
        ):
            errors.append(f"oracle-native-receipt-diagnostics-invalid:{case_id}")

    if receipt.get("native_executed_case_count") != len(results):
        errors.append("oracle-native-receipt-executed-count-invalid")
    if receipt.get("native_passed_case_count") != sum(
        result.get("status") == "passed-native"
        for result in results
        if isinstance(result, Mapping)
    ):
        errors.append("oracle-native-receipt-passed-count-invalid")
    if receipt.get("native_verified_behavior_count") != len(passed_behaviors):
        errors.append("oracle-native-receipt-behavior-count-invalid")

    complete_lane = len(results) == 2000 and len(seen) == 2000 and all(
        isinstance(result, Mapping) and result.get("status") == "passed-native"
        for result in results
    )
    if receipt.get("native_oracle_conformance") is not complete_lane:
        errors.append("oracle-native-receipt-conformance-claim-invalid")
    for name in (
        "target_equivalence_observed",
        "idempiere_application_equivalence",
        "cloudbank_mapping_complete",
        "migration_complete",
        "production_ready",
    ):
        if receipt.get(name) is not False:
            errors.append(f"oracle-native-receipt-overclaim:{name}")
    return sorted(set(errors))
