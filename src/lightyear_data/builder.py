from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lightyear_common.io import write_json, write_text

from .equivalence import signed_development_receipt
from .fixtures import fixture_catalog
from .parser import parse_db2_ddl, parse_dcl, parse_embedded_sql
from .postgres import PostgreSQLAdapter
from .oracle import OracleAdapter
from .contracts import seal


RELATIVE_ROOT = Path("app/app-authorization-ims-db2-mq")


def build_assets(legacy_root: Path, output_root: Path) -> dict[str, Any]:
    source_root = legacy_root / RELATIVE_ROOT
    ddl_path = source_root / "ddl/AUTHFRDS.ddl"
    index_path = source_root / "ddl/XAUTHFRD.ddl"
    dcl_path = source_root / "dcl/AUTHFRDS.dcl"
    program_path = source_root / "cbl/COPAUS2C.cbl"
    missing = [path for path in (ddl_path, index_path, dcl_path, program_path) if not path.is_file()]
    if missing:
        raise ValueError("Missing AUTHFRDS source assets: " + ", ".join(str(path) for path in missing))
    source_paths = {
        "ddl": ddl_path.relative_to(legacy_root).as_posix(),
        "index": index_path.relative_to(legacy_root).as_posix(),
        "dcl": dcl_path.relative_to(legacy_root).as_posix(),
        "program": program_path.relative_to(legacy_root).as_posix(),
    }
    model = parse_db2_ddl(
        ddl_path.read_text(encoding="utf-8", errors="replace") + "\n" +
        index_path.read_text(encoding="utf-8", errors="replace"),
        source_paths["ddl"],
    )
    model["source"]["index_path"] = source_paths["index"]
    # The source-path enrichment is semantic, so reseal after it is applied.
    from .contracts import seal
    model = seal(model)
    dcl = parse_dcl(dcl_path.read_text(encoding="utf-8", errors="replace"), source_paths["dcl"])
    sql = parse_embedded_sql(program_path.read_text(encoding="utf-8", errors="replace"), source_paths["program"])
    fixtures = fixture_catalog()
    postgres = PostgreSQLAdapter()
    oracle = OracleAdapter()
    postgres_mapping = postgres.mapping(model)
    oracle_mapping = oracle.mapping(model)
    postgres_receipt = signed_development_receipt(model, postgres_mapping, fixtures)
    oracle_receipt = signed_development_receipt(model, oracle_mapping, fixtures)
    target_plan = seal({
        "schema_version": "1.0", "plan_type": "factorydark-multi-target-data-equivalence-plan",
        "workload": "carddemo-authorization-authfrds", "source": "db2-zos",
        "targets": [
            {"dialect": postgres.dialect, "adapter": postgres_mapping["adapter"], "mapping_sha256": postgres_mapping["content_sha256"], "image": postgres.default_image},
            {"dialect": oracle.dialect, "adapter": oracle_mapping["adapter"], "mapping_sha256": oracle_mapping["content_sha256"], "image": oracle.default_image},
        ],
        "production_ready": False,
        "required_live_checks": ["exact_schema", "exact_primary_key", "exact_indexes", "row_count", "normalized_row_checksums", "query_results", "transaction_commit", "transaction_rollback"],
    })
    root = output_root / "data-modernization"
    write_json(root / "canonical/authfrds.model.json", model)
    write_json(root / "source/authfrds.dcl-contract.json", dcl)
    write_json(root / "source/authfrds.embedded-sql.json", sql)
    write_json(root / "mappings/authfrds-postgresql.json", postgres_mapping)
    write_json(root / "mappings/authfrds-oracle.json", oracle_mapping)
    write_json(root / "fixtures/authfrds.fixtures.json", fixtures)
    write_text(root / "postgres/authfrds.sql", postgres.schema_sql(model))
    write_text(root / "oracle/authfrds.sql", oracle.schema_sql(model))
    write_json(root / "receipts/authfrds.offline.receipt.json", postgres_receipt)
    write_json(root / "receipts/authfrds.oracle-offline.receipt.json", oracle_receipt)
    write_json(root / "receipts/authfrds.target-plan.json", target_plan)
    return {
        "status": "passed" if postgres_receipt["status"] == oracle_receipt["status"] == "passed" else "failed", "output": str(root),
        "model_sha256": model["content_sha256"],
        "mapping_sha256": postgres_mapping["content_sha256"], "oracle_mapping_sha256": oracle_mapping["content_sha256"],
        "receipt_sha256": postgres_receipt["content_sha256"], "target_plan_sha256": target_plan["content_sha256"], "columns": len(model["columns"]),
        "sql_statements": len(sql["statements"]), "fixture_rows": len(fixtures["rows"]),
    }


def load_assets(root: Path, target: str = "postgresql") -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    base = root / "data-modernization"
    return tuple(
        json.loads((base / path).read_text(encoding="utf-8"))
        for path in (
            "canonical/authfrds.model.json", f"mappings/authfrds-{target}.json",
            "fixtures/authfrds.fixtures.json",
        )
    )  # type: ignore[return-value]
