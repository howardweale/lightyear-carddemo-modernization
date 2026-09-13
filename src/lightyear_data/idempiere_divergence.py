from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

from lightyear_common.io import normalize_logical_source, source_hashes

from .contracts import content_hash, seal


SCHEMA_VERSION = "1.0"
MILESTONE = 68
PROJECT_ID = "idempiere-release13-oracle-postgresql-divergence-audit"
MANIFEST_TYPE = "lightyear-idempiere-dialect-pairing-manifest"
RECEIPT_TYPE = "lightyear-idempiere-divergence-audit-stage1-receipt"
PINNED_COMMIT = "731515dcdd5278b843db33b9d3109d155b881951"

SOURCE_PIN_PATH = Path("reference-estates/idempiere/source-pin.json")
INVENTORY_PATH = Path("reference-estates/idempiere/inventory.json")
BUSINESS_SLICES_PATH = Path("reference-estates/idempiere/business-slices.json")
SEMANTIC_CORE_PATH = Path("data-modernization/semantic-core/database-semantic-core.json")
PAIRING_SCHEMA_PATH = Path(
    "data-modernization/schema/idempiere-dialect-pairing-manifest.schema.json"
)
RECEIPT_SCHEMA_PATH = Path(
    "data-modernization/schema/idempiere-divergence-stage1-receipt.schema.json"
)
OUTPUT_ROOT = Path("factory/idempiere-divergence-audit")
MANIFEST_PATH = OUTPUT_ROOT / "pairing-manifest.json"
RECEIPT_PATH = OUTPUT_ROOT / "stage1.receipt.json"

CURRENT_MIGRATION_RE = re.compile(
    r"^migration/([^/]+)/(oracle|postgresql)/(.+\.sql)$", re.IGNORECASE
)
TICKET_RE = re.compile(r"(?<![A-Za-z0-9])IDEMPIERE-(\d+)(?![A-Za-z0-9])", re.IGNORECASE)

# These are the deliberately bounded Java exceptions to the SQL-only audit.
# They can transform Oracle-shaped SQL before PostgreSQL execution or select a
# database-specific provider, so excluding them would leave the maintenance
# provenance premise untested.
CONVERSION_BOUNDARY_PATHS = (
    "org.adempiere.base/src/org/compiere/db/AdempiereDatabase.java",
    "org.adempiere.base/src/org/compiere/db/Database.java",
    "org.adempiere.base/src/org/compiere/dbPort/Convert.java",
    "org.adempiere.base/src/org/compiere/dbPort/Convert_SQL92.java",
    "org.compiere.db.oracle.provider/src/org/compiere/db/DB_Oracle.java",
    "org.compiere.db.oracle.provider/src/org/compiere/dbPort/Convert_Oracle.java",
    "org.compiere.db.postgresql.provider/src/org/compiere/db/DB_PostgreSQL.java",
    "org.compiere.db.postgresql.provider/src/org/compiere/dbPort/ConvertMap_PostgreSQL.java",
    "org.compiere.db.postgresql.provider/src/org/compiere/dbPort/Convert_PostgreSQL.java",
)

CONVERSION_BOUNDARY_ROLES = {
    "org.adempiere.base/src/org/compiere/db/AdempiereDatabase.java": "database-conversion-interface",
    "org.adempiere.base/src/org/compiere/db/Database.java": "database-provider-selection",
    "org.adempiere.base/src/org/compiere/dbPort/Convert.java": "dual-dialect-migration-log-writer",
    "org.adempiere.base/src/org/compiere/dbPort/Convert_SQL92.java": "shared-sql92-conversion-base",
    "org.compiere.db.oracle.provider/src/org/compiere/db/DB_Oracle.java": "oracle-conversion-entrypoint",
    "org.compiere.db.oracle.provider/src/org/compiere/dbPort/Convert_Oracle.java": "oracle-converter",
    "org.compiere.db.postgresql.provider/src/org/compiere/db/DB_PostgreSQL.java": "postgresql-conversion-entrypoint",
    "org.compiere.db.postgresql.provider/src/org/compiere/dbPort/ConvertMap_PostgreSQL.java": "postgresql-conversion-map",
    "org.compiere.db.postgresql.provider/src/org/compiere/dbPort/Convert_PostgreSQL.java": "postgresql-converter",
}

GENERATION_MARKERS = {
    "org.adempiere.base/src/org/compiere/dbPort/Convert.java": (
        "public synchronized static void logMigrationScript",
        'getMigrationScriptFolder("oracle")',
        'getMigrationScriptFolder("postgresql")',
        "writeLogMigrationScript(writerOr, oraStatement)",
        "writeLogMigrationScript(writerPg, pgStatement)",
    ),
    "org.compiere.db.oracle.provider/src/org/compiere/db/DB_Oracle.java": (
        "Convert.logMigrationScript(oraStatement, null)",
    ),
    "org.compiere.db.postgresql.provider/src/org/compiere/db/DB_PostgreSQL.java": (
        "Convert.logMigrationScript(oraStatement, retValue[0])",
    ),
}


def _git(source_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(source_root), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise ValueError(result.stderr.strip() or "git command failed")
    return result.stdout.strip()


def _tracked_paths(source_root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(source_root), "ls-files", "-z"],
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise ValueError(result.stderr.decode("utf-8", errors="replace").strip() or "git ls-files failed")
    return sorted(item.decode("utf-8") for item in result.stdout.split(b"\0") if item)


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {path}")
    return payload


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_identity(source_root: Path, source_pin: Mapping[str, Any]) -> dict[str, str]:
    expected = source_pin.get("source", {})
    commit = _git(source_root, "rev-parse", "HEAD")
    tree = _git(source_root, "rev-parse", "HEAD^{tree}")
    if commit != expected.get("commit") or commit != PINNED_COMMIT:
        raise ValueError(f"expected pinned commit {PINNED_COMMIT}; found {commit}")
    if tree != expected.get("tree"):
        raise ValueError(f"expected pinned tree {expected.get('tree')}; found {tree}")
    if _git(source_root, "status", "--porcelain"):
        raise ValueError("upstream checkout must be clean")
    return {
        "repository": str(expected.get("repository")),
        "branch": str(expected.get("branch")),
        "commit": commit,
        "tree": tree,
    }


def _script_key(path: str) -> tuple[str, str]:
    match = CURRENT_MIGRATION_RE.match(path)
    if not match:
        raise ValueError(f"not a current migration script: {path}")
    version, _, filename = match.groups()
    return version.casefold(), filename.casefold()


def _ticket_key(path: str) -> tuple[str, str] | None:
    match = CURRENT_MIGRATION_RE.match(path)
    if not match:
        return None
    version, _, filename = match.groups()
    ticket = TICKET_RE.search(filename)
    return (version.casefold(), ticket.group(1)) if ticket else None


def _script_record(source_root: Path, relative: str) -> tuple[dict[str, Any], str]:
    path = source_root / relative
    logical_sha256, transport_sha256 = source_hashes(path)
    raw = path.read_bytes()
    logical = normalize_logical_source(raw)
    return (
        {
            "path": relative,
            "logical_sha256": logical_sha256,
            "transport_sha256": transport_sha256,
            "bytes": len(raw),
            "lines": len(logical.splitlines()),
        },
        logical.decode("utf-8", errors="replace"),
    )


def _referenced_tables(texts: Iterable[str], tables: Iterable[str]) -> list[str]:
    combined = "\n".join(texts)
    return sorted(
        table
        for table in tables
        if re.search(rf"(?<![A-Za-z0-9_$#]){re.escape(table)}(?![A-Za-z0-9_$#])", combined, re.IGNORECASE)
    )


def _pair_id(oracle_path: str, postgresql_path: str) -> str:
    digest = hashlib.sha256(f"{oracle_path}\0{postgresql_path}".encode("utf-8")).hexdigest()
    return f"pair:{digest}"


def pair_current_migrations(
    source_root: Path,
    tracked_paths: Iterable[str],
    pilot_tables: Iterable[str],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    by_dialect: dict[str, dict[tuple[str, str], str]] = {"oracle": {}, "postgresql": {}}
    for path in tracked_paths:
        match = CURRENT_MIGRATION_RE.match(path)
        if not match:
            continue
        dialect = match.group(2).casefold()
        key = _script_key(path)
        if key in by_dialect[dialect]:
            raise ValueError(f"duplicate normalized migration path: {path}")
        by_dialect[dialect][key] = path

    matched: list[tuple[str, str, str]] = []
    exact_keys = sorted(set(by_dialect["oracle"]) & set(by_dialect["postgresql"]))
    for key in exact_keys:
        matched.append(
            (
                by_dialect["oracle"].pop(key),
                by_dialect["postgresql"].pop(key),
                "exact-version-and-filename",
            )
        )

    oracle_by_ticket: dict[tuple[str, str], list[str]] = defaultdict(list)
    postgres_by_ticket: dict[tuple[str, str], list[str]] = defaultdict(list)
    for path in by_dialect["oracle"].values():
        key = _ticket_key(path)
        if key:
            oracle_by_ticket[key].append(path)
    for path in by_dialect["postgresql"].values():
        key = _ticket_key(path)
        if key:
            postgres_by_ticket[key].append(path)

    for key in sorted(set(oracle_by_ticket) & set(postgres_by_ticket)):
        oracle_candidates = oracle_by_ticket[key]
        postgres_candidates = postgres_by_ticket[key]
        if len(oracle_candidates) != 1 or len(postgres_candidates) != 1:
            continue
        oracle_path = oracle_candidates[0]
        postgres_path = postgres_candidates[0]
        matched.append((oracle_path, postgres_path, "unique-version-and-ticket-id"))
        by_dialect["oracle"].pop(_script_key(oracle_path))
        by_dialect["postgresql"].pop(_script_key(postgres_path))

    pairs: list[dict[str, Any]] = []
    pilot_tables = tuple(pilot_tables)
    for oracle_path, postgresql_path, method in sorted(matched):
        oracle, oracle_text = _script_record(source_root, oracle_path)
        postgresql, postgresql_text = _script_record(source_root, postgresql_path)
        tables = _referenced_tables((oracle_text, postgresql_text), pilot_tables)
        ticket = TICKET_RE.search(f"{oracle_path} {postgresql_path}")
        pairs.append(
            {
                "pair_id": _pair_id(oracle_path, postgresql_path),
                "release_segment": CURRENT_MIGRATION_RE.match(oracle_path).group(1),  # type: ignore[union-attr]
                "ticket_id": f"IDEMPIERE-{ticket.group(1)}" if ticket else None,
                "pairing_method": method,
                "oracle": oracle,
                "postgresql": postgresql,
                "content_identical": oracle["logical_sha256"] == postgresql["logical_sha256"],
                "pilot_slices": ["order-to-cash"] if tables else [],
                "pilot_tables_referenced": tables,
                "maintenance_provenance": "not-classified",
                "comparison_status": "not-run",
            }
        )

    unpaired = [
        {"dialect": dialect, "path": path, "reason": "no-unique-counterpart"}
        for dialect in ("oracle", "postgresql")
        for path in sorted(by_dialect[dialect].values())
    ]
    return pairs, unpaired


def _conversion_boundary(source_root: Path, tracked_paths: set[str]) -> list[dict[str, Any]]:
    missing = sorted(set(CONVERSION_BOUNDARY_PATHS) - tracked_paths)
    if missing:
        raise ValueError(f"missing conversion-boundary source: {missing}")
    items = []
    for relative in CONVERSION_BOUNDARY_PATHS:
        path = source_root / relative
        text = path.read_text(encoding="utf-8", errors="replace")
        missing_markers = [
            marker for marker in GENERATION_MARKERS.get(relative, ()) if marker not in text
        ]
        if missing_markers:
            raise ValueError(f"conversion-boundary markers missing from {relative}: {missing_markers}")
        logical_sha256, transport_sha256 = source_hashes(path)
        items.append(
            {
                "path": relative,
                "role": CONVERSION_BOUNDARY_ROLES[relative],
                "logical_sha256": logical_sha256,
                "transport_sha256": transport_sha256,
            }
        )
    return items


def _pilot_tables(business_slices: Mapping[str, Any]) -> list[str]:
    slices = business_slices.get("slices")
    if not isinstance(slices, list):
        raise ValueError("business-slices list is unavailable")
    selected = next(
        (item for item in slices if isinstance(item, dict) and item.get("id") == "order-to-cash"),
        None,
    )
    if not selected or not isinstance(selected.get("tables"), list):
        raise ValueError("order-to-cash slice tables are unavailable")
    tables = sorted(str(item) for item in selected["tables"])
    if not tables:
        raise ValueError("order-to-cash slice must contain tables")
    return tables


def build_pairing_manifest(project_root: Path, source_root: Path) -> dict[str, Any]:
    source_pin_path = project_root / SOURCE_PIN_PATH
    inventory_path = project_root / INVENTORY_PATH
    business_slices_path = project_root / BUSINESS_SLICES_PATH
    semantic_core_path = project_root / SEMANTIC_CORE_PATH
    source_pin = _load_json(source_pin_path)
    inventory = _load_json(inventory_path)
    business_slices = _load_json(business_slices_path)
    semantic_core = _load_json(semantic_core_path)
    source = _source_identity(source_root, source_pin)
    tracked = _tracked_paths(source_root)
    pairs, unpaired = pair_current_migrations(
        source_root, tracked, _pilot_tables(business_slices)
    )

    methods: dict[str, int] = defaultdict(int)
    for item in pairs:
        methods[item["pairing_method"]] += 1
    oracle_scripts = len(pairs) + sum(item["dialect"] == "oracle" for item in unpaired)
    postgresql_scripts = len(pairs) + sum(item["dialect"] == "postgresql" for item in unpaired)
    expected_oracle = inventory.get("estate", {}).get("oracle_sql_files_current_migration")
    if oracle_scripts != expected_oracle:
        raise ValueError(
            f"current Oracle migration count does not match MS48 inventory: {oracle_scripts} != {expected_oracle}"
        )
    total_scripts = oracle_scripts + postgresql_scripts
    pilot_pairs = sum("order-to-cash" in item["pilot_slices"] for item in pairs)
    content_identical = sum(bool(item["content_identical"]) for item in pairs)

    return seal(
        {
            "schema_version": SCHEMA_VERSION,
            "manifest_type": MANIFEST_TYPE,
            "milestone": MILESTONE,
            "project_id": PROJECT_ID,
            "source": source,
            "bindings": {
                "source_pin_file_sha256": _file_sha256(source_pin_path),
                "inventory_file_sha256": _file_sha256(inventory_path),
                "business_slices_file_sha256": _file_sha256(business_slices_path),
                "database_semantic_core_sha256": semantic_core.get("content_sha256"),
                "pairing_manifest_schema_sha256": _file_sha256(
                    project_root / PAIRING_SCHEMA_PATH
                ),
                "stage1_receipt_schema_sha256": _file_sha256(
                    project_root / RECEIPT_SCHEMA_PATH
                ),
            },
            "scope": {
                "included": [
                    "current migration Oracle SQL",
                    "current migration PostgreSQL SQL",
                    "order-to-cash script subset",
                    "bounded database-provider and SQL-conversion Java boundary",
                ],
                "excluded": [
                    "migration-historic",
                    "general Java application source",
                    "native database execution",
                    "semantic comparison",
                    "agent triage",
                ],
                "pilot_slice": "order-to-cash",
                "pilot_tables": _pilot_tables(business_slices),
                "pilot_selection_method": "case-insensitive whole-identifier lexical reference in either dialect; comments are not excluded until Stage 2 parsing",
            },
            "pairing_policy": {
                "primary": "case-insensitive release segment and filename identity",
                "fallback": "unique IDEMPIERE ticket id within one release segment",
                "unpaired_is_finding": True,
                "many_to_many_pairing_allowed": False,
            },
            "statistics": {
                "oracle_scripts": oracle_scripts,
                "postgresql_scripts": postgresql_scripts,
                "paired_script_pairs": len(pairs),
                "exact_version_and_filename_pairs": methods["exact-version-and-filename"],
                "unique_version_and_ticket_id_pairs": methods["unique-version-and-ticket-id"],
                "unpaired_oracle_scripts": sum(item["dialect"] == "oracle" for item in unpaired),
                "unpaired_postgresql_scripts": sum(
                    item["dialect"] == "postgresql" for item in unpaired
                ),
                "paired_script_coverage": round((2 * len(pairs)) / total_scripts, 8)
                if total_scripts
                else 0.0,
                "order_to_cash_pilot_pairs": pilot_pairs,
                "content_identical_pairs": content_identical,
            },
            "premise_check": {
                "conversion_layer_present": True,
                "dual_dialect_migration_log_writer_present": True,
                "independent_parallel_maintenance_proven": False,
                "generated_variants_ruled_out": False,
                "status": "history-classification-required",
                "reason": "iDempiere Convert.logMigrationScript writes Oracle and PostgreSQL migration files and DB_PostgreSQL.convertStatement supplies converted output; static pairing cannot establish which files were later edited independently.",
            },
            "conversion_boundary": _conversion_boundary(source_root, set(tracked)),
            "pairs": pairs,
            "unpaired": unpaired,
            "stage1_complete": True,
            "semantic_comparison_complete": False,
            "agent_triage_complete": False,
            "audit_complete": False,
            "application_equivalence": False,
            "production_ready": False,
        }
    )


def build_stage1_receipt(manifest: Mapping[str, Any]) -> dict[str, Any]:
    statistics = dict(manifest["statistics"])
    premise = dict(manifest["premise_check"])
    return seal(
        {
            "schema_version": SCHEMA_VERSION,
            "receipt_type": RECEIPT_TYPE,
            "milestone": MILESTONE,
            "project_id": PROJECT_ID,
            "stage": "inventory-pairing-and-premise-check",
            "status": "passed",
            "bindings": {
                "pairing_manifest_sha256": manifest["content_sha256"],
                "source_commit": manifest["source"]["commit"],
                "source_tree": manifest["source"]["tree"],
                **dict(manifest["bindings"]),
            },
            "checks": {
                "existing_source_pin_reused": True,
                "ms48_inventory_reconciled": True,
                "existing_order_to_cash_slice_reused": True,
                "existing_database_semantic_core_reused": True,
                "current_migrations_only": True,
                "conversion_boundary_bound": bool(manifest["conversion_boundary"]),
                "pairing_coverage_measured": True,
                "maintenance_premise_not_overclaimed": (
                    premise.get("status") == "history-classification-required"
                    and premise.get("dual_dialect_migration_log_writer_present") is True
                    and premise.get("independent_parallel_maintenance_proven") is False
                    and premise.get("generated_variants_ruled_out") is False
                ),
                "model_calls_zero": True,
            },
            "coverage": statistics,
            "station_usage": {
                "planner": "not-used-stage1-deterministic",
                "analyst": "not-used-stage1-deterministic",
                "builder": "not-used-audit-does-not-generate-candidate",
                "verifier": "deterministic-contract-validation",
            },
            "open_gates": [
                "classify generated versus independently edited script provenance",
                "implement parser coverage and semantic comparison",
                "calibrate the first twenty flagged comparisons",
                "run bounded agent triage only after deterministic flagging",
            ],
            "semantic_comparison_complete": False,
            "agent_triage_complete": False,
            "audit_complete": False,
            "application_equivalence": False,
            "production_ready": False,
            "claim_unlocked": "LIGHTYEAR deterministically paired and measured the pinned iDempiere current Oracle/PostgreSQL migration surface, selected the existing order-to-cash pilot, and bound the database conversion layer without claiming semantic equivalence.",
        }
    )


def build_stage1_artifacts(project_root: Path, source_root: Path) -> dict[str, dict[str, Any]]:
    manifest = build_pairing_manifest(project_root.resolve(), source_root.resolve())
    return {
        "pairing-manifest.json": manifest,
        "stage1.receipt.json": build_stage1_receipt(manifest),
    }


def validate_stage1_artifacts(
    project_root: Path,
    *,
    source_root: Path | None = None,
    manifest: Mapping[str, Any] | None = None,
    receipt: Mapping[str, Any] | None = None,
) -> list[str]:
    project_root = project_root.resolve()
    manifest = dict(manifest or _load_json(project_root / MANIFEST_PATH))
    receipt = dict(receipt or _load_json(project_root / RECEIPT_PATH))
    errors: list[str] = []

    if manifest.get("milestone") != MILESTONE or receipt.get("milestone") != MILESTONE:
        errors.append("stage1-milestone-invalid")

    if manifest.get("manifest_type") != MANIFEST_TYPE or manifest.get("project_id") != PROJECT_ID:
        errors.append("pairing-manifest-identity-invalid")
    if manifest.get("content_sha256") != content_hash(manifest):
        errors.append("pairing-manifest-content-hash-invalid")
    if receipt.get("receipt_type") != RECEIPT_TYPE or receipt.get("project_id") != PROJECT_ID:
        errors.append("stage1-receipt-identity-invalid")
    if receipt.get("content_sha256") != content_hash(receipt):
        errors.append("stage1-receipt-content-hash-invalid")

    bindings = manifest.get("bindings", {})
    expected_bindings = {
        "source_pin_file_sha256": _file_sha256(project_root / SOURCE_PIN_PATH),
        "inventory_file_sha256": _file_sha256(project_root / INVENTORY_PATH),
        "business_slices_file_sha256": _file_sha256(project_root / BUSINESS_SLICES_PATH),
        "database_semantic_core_sha256": _load_json(project_root / SEMANTIC_CORE_PATH).get(
            "content_sha256"
        ),
        "pairing_manifest_schema_sha256": _file_sha256(project_root / PAIRING_SCHEMA_PATH),
        "stage1_receipt_schema_sha256": _file_sha256(project_root / RECEIPT_SCHEMA_PATH),
    }
    if bindings != expected_bindings:
        errors.append("pairing-manifest-input-bindings-invalid")
    source_pin = _load_json(project_root / SOURCE_PIN_PATH)
    if manifest.get("source") != {
        key: source_pin["source"][key] for key in ("repository", "branch", "commit", "tree")
    }:
        errors.append("pairing-manifest-source-identity-invalid")

    pairs = manifest.get("pairs")
    unpaired = manifest.get("unpaired")
    statistics = manifest.get("statistics", {})
    if not isinstance(pairs, list) or not isinstance(unpaired, list):
        errors.append("pairing-manifest-items-invalid")
        pairs = []
        unpaired = []
    pair_ids = [item.get("pair_id") for item in pairs if isinstance(item, dict)]
    oracle_paths = [item.get("oracle", {}).get("path") for item in pairs if isinstance(item, dict)]
    postgres_paths = [
        item.get("postgresql", {}).get("path") for item in pairs if isinstance(item, dict)
    ]
    if len(pair_ids) != len(set(pair_ids)) or None in pair_ids:
        errors.append("pairing-manifest-pair-ids-invalid")
    if len(oracle_paths) != len(set(oracle_paths)) or None in oracle_paths:
        errors.append("pairing-manifest-oracle-paths-invalid")
    if len(postgres_paths) != len(set(postgres_paths)) or None in postgres_paths:
        errors.append("pairing-manifest-postgresql-paths-invalid")
    if statistics.get("paired_script_pairs") != len(pairs):
        errors.append("pairing-manifest-pair-count-invalid")
    if statistics.get("order_to_cash_pilot_pairs") != sum(
        "order-to-cash" in item.get("pilot_slices", []) for item in pairs if isinstance(item, dict)
    ):
        errors.append("pairing-manifest-pilot-count-invalid")
    if any(
        item.get("maintenance_provenance") != "not-classified"
        or item.get("comparison_status") != "not-run"
        for item in pairs
        if isinstance(item, dict)
    ):
        errors.append("pairing-manifest-stage-boundary-invalid")
    if [item.get("path") for item in manifest.get("conversion_boundary", [])] != list(
        CONVERSION_BOUNDARY_PATHS
    ):
        errors.append("pairing-manifest-conversion-boundary-invalid")
    premise = manifest.get("premise_check", {})
    if (
        premise.get("conversion_layer_present") is not True
        or premise.get("dual_dialect_migration_log_writer_present") is not True
        or premise.get("independent_parallel_maintenance_proven") is not False
        or premise.get("generated_variants_ruled_out") is not False
        or premise.get("status") != "history-classification-required"
    ):
        errors.append("pairing-manifest-premise-overclaim")
    if any(
        manifest.get(name) is not False
        for name in (
            "semantic_comparison_complete",
            "agent_triage_complete",
            "audit_complete",
            "application_equivalence",
            "production_ready",
        )
    ):
        errors.append("pairing-manifest-completion-overclaim")

    expected_receipt = build_stage1_receipt(manifest)
    if receipt != expected_receipt:
        errors.append("stage1-receipt-drift")
    if any(
        receipt.get(name) is not False
        for name in (
            "semantic_comparison_complete",
            "agent_triage_complete",
            "audit_complete",
            "application_equivalence",
            "production_ready",
        )
    ):
        errors.append("stage1-receipt-completion-overclaim")
    if receipt.get("checks", {}).get("model_calls_zero") is not True:
        errors.append("stage1-receipt-model-boundary-invalid")
    if receipt.get("station_usage", {}).get("builder") != "not-used-audit-does-not-generate-candidate":
        errors.append("stage1-receipt-builder-boundary-invalid")

    if source_root is not None:
        try:
            expected = build_stage1_artifacts(project_root, source_root)
        except ValueError as exc:
            errors.append(f"upstream-source-invalid:{exc}")
        else:
            if manifest != expected["pairing-manifest.json"]:
                errors.append("pairing-manifest-upstream-drift")
            if receipt != expected["stage1.receipt.json"]:
                errors.append("stage1-receipt-upstream-drift")
    return sorted(set(errors))
