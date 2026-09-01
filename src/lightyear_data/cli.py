from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from lightyear_common.io import write_json, write_text

from .builder import build_assets, load_assets
from .ase import build_ase_artifacts, validate_ase_qualification
from .contracts import seal, sign
from .db2 import Db2SourceAdapter, build_db2_source_ledger, db2_source_conformance_receipt
from .equivalence import offline_equivalence
from .live import DockerOracleRunner, DockerPostgresExactRunner, aggregate_receipts
from .oracle import OracleAdapter
from .oracle_dialect import (
    OUTPUT_ROOT as ORACLE_DIALECT_OUTPUT_ROOT,
    build_oracle_dialect_artifacts,
    validate_oracle_dialect_artifacts,
)
from .oracle_postgres_proof import (
    build_oracle_postgresql_proof,
    validate_oracle_postgresql_proof,
)
from .oracle_procedures import validate_procedure_artifacts
from .oracle_source import (
    build_oracle_source_artifacts,
    validate_oracle_postgresql_source_qualification,
)
from .postgres import PostgreSQLAdapter, fixture_sql
from .rehearsal import build_rehearsal_evidence, validate_rehearsal_evidence
from .validation import validate_assets
from .semantic_core import validate_compatibility_ledger
from .semantic_core import build_profile_contract
from .stored_logic import (
    build_stored_logic_qualification,
    validate_stored_logic_qualification,
)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="FactoryDark Db2-to-PostgreSQL and Oracle data modernization proof cell")
    commands = root.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build")
    build.add_argument("--legacy-root", type=Path, required=True)
    build.add_argument("--output-root", type=Path, default=Path("."))
    validate = commands.add_parser("validate")
    validate.add_argument("--project-root", type=Path, default=Path("."))
    offline = commands.add_parser("verify-offline")
    offline.add_argument("--project-root", type=Path, default=Path("."))
    live = commands.add_parser("verify-docker")
    live.add_argument("--project-root", type=Path, default=Path("."))
    live.add_argument("--target", choices=("postgresql", "oracle", "all"), default="postgresql")
    live.add_argument("--image")
    live.add_argument("--postgres-image", default=PostgreSQLAdapter.default_image)
    live.add_argument("--oracle-image", default=OracleAdapter.default_image)
    live.add_argument("--output", type=Path)
    sign_command = commands.add_parser("sign")
    sign_command.add_argument("--receipt", type=Path, required=True)
    sign_command.add_argument("--output", type=Path, required=True)
    sign_command.add_argument("--signer", default="customer-data-equivalence-authority")
    rehearsal = commands.add_parser("rehearse-offline")
    rehearsal.add_argument("--project-root", type=Path, default=Path("."))
    rehearsal.add_argument("--output-root", type=Path)
    validate_rehearsal = commands.add_parser("validate-rehearsal")
    validate_rehearsal.add_argument("--project-root", type=Path, default=Path("."))
    semantic = commands.add_parser("verify-semantic-core")
    semantic.add_argument("--project-root", type=Path, default=Path("."))
    proof = commands.add_parser("build-oracle-postgresql-proof")
    proof.add_argument("--project-root", type=Path, default=Path("."))
    proof.add_argument("--output", type=Path)
    verify_proof = commands.add_parser("verify-oracle-postgresql-proof")
    verify_proof.add_argument("--project-root", type=Path, default=Path("."))
    stored = commands.add_parser("build-stored-logic-qualification")
    stored.add_argument("--project-root", type=Path, default=Path("."))
    stored.add_argument("--output", type=Path)
    verify_stored = commands.add_parser("verify-stored-logic-qualification")
    verify_stored.add_argument("--project-root", type=Path, default=Path("."))
    db2 = commands.add_parser("build-db2-semantic-adapter")
    db2.add_argument("--project-root", type=Path, default=Path("."))
    verify_db2 = commands.add_parser("verify-db2-semantic-adapter")
    verify_db2.add_argument("--project-root", type=Path, default=Path("."))
    oracle_source = commands.add_parser("build-oracle-source-qualification")
    oracle_source.add_argument("--project-root", type=Path, default=Path("."))
    oracle_source.add_argument("--output-root", type=Path)
    verify_oracle_source = commands.add_parser("verify-oracle-source-qualification")
    verify_oracle_source.add_argument("--project-root", type=Path, default=Path("."))
    oracle_dialect = commands.add_parser("build-oracle-dialect-corpus")
    oracle_dialect.add_argument("--project-root", type=Path, default=Path("."))
    verify_oracle_dialect = commands.add_parser("verify-oracle-dialect-corpus")
    verify_oracle_dialect.add_argument("--project-root", type=Path, default=Path("."))
    ase_source = commands.add_parser("build-sap-ase-source-adapter")
    ase_source.add_argument("--project-root", type=Path, default=Path("."))
    ase_source.add_argument("--output-root", type=Path)
    verify_ase_source = commands.add_parser("verify-sap-ase-source-adapter")
    verify_ase_source.add_argument("--project-root", type=Path, default=Path("."))
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "build":
        result = build_assets(args.legacy_root.resolve(), args.output_root.resolve())
    elif args.command == "validate":
        result = validate_assets(args.project_root.resolve())
    elif args.command == "verify-offline":
        model, mapping, fixtures = load_assets(args.project_root.resolve())
        result = offline_equivalence(model, mapping, fixtures)
    elif args.command == "verify-docker":
        model, _, fixtures = load_assets(args.project_root.resolve())
        output_root = args.project_root.resolve() / "work/data-modernization"
        if args.target == "postgresql":
            result = DockerPostgresExactRunner().verify(model, fixtures, args.image or args.postgres_image)
            output = args.output or output_root / "live-postgresql.receipt.json"
        elif args.target == "oracle":
            result = DockerOracleRunner().verify(model, fixtures, args.image or args.oracle_image)
            output = args.output or output_root / "live-oracle.receipt.json"
        else:
            postgres = DockerPostgresExactRunner().verify(model, fixtures, args.postgres_image)
            oracle = DockerOracleRunner().verify(model, fixtures, args.oracle_image)
            write_json(output_root / "live-postgresql.receipt.json", postgres)
            write_json(output_root / "live-oracle.receipt.json", oracle)
            result = aggregate_receipts([postgres, oracle])
            output = args.output or output_root / "live-multi-target.receipt.json"
        write_json(output, result)
        result = dict(result)
        result["output"] = str(output)
    elif args.command == "rehearse-offline":
        project_root = args.project_root.resolve()
        result = build_rehearsal_evidence(
            project_root, (args.output_root or project_root).resolve()
        )
    elif args.command == "validate-rehearsal":
        errors = validate_rehearsal_evidence(args.project_root.resolve())
        result = {
            "status": "passed" if not errors else "failed",
            "errors": errors,
        }
    elif args.command == "verify-semantic-core":
        project_root = args.project_root.resolve()
        model, postgres_mapping, _ = load_assets(project_root)
        _, oracle_mapping, _ = load_assets(project_root, "oracle")
        ledger = json.loads(
            (project_root / "data-modernization/semantic-core/authfrds.compatibility-ledger.json").read_text(encoding="utf-8")
        )
        errors = validate_compatibility_ledger(
            ledger, model, (postgres_mapping, oracle_mapping)
        )
        result = {
            "status": "passed" if not errors else "failed",
            "errors": errors,
            "semantic_core_version": "1.0",
            "compatibility_ledger_sha256": ledger.get("content_sha256"),
            "production_ready": False,
        }
    elif args.command == "build-oracle-postgresql-proof":
        project_root = args.project_root.resolve()
        payload = build_oracle_postgresql_proof(project_root)
        output = args.output or project_root / "data-modernization/oracle-postgresql-proof/authfrds.proof.json"
        write_json(output, payload)
        result = {
            "status": "passed",
            "output": str(output),
            "content_sha256": payload["content_sha256"],
            "database_migration_complete": False,
            "production_ready": False,
        }
    elif args.command == "verify-oracle-postgresql-proof":
        project_root = args.project_root.resolve()
        errors = validate_oracle_postgresql_proof(project_root)
        result = {
            "status": "passed" if not errors else "failed",
            "errors": errors,
            "database_migration_complete": False,
            "production_ready": False,
        }
    elif args.command == "build-stored-logic-qualification":
        project_root = args.project_root.resolve()
        payload = build_stored_logic_qualification(project_root)
        output = args.output or project_root / "data-modernization/stored-logic/authfrds.qualification.json"
        write_json(output, payload)
        result = {
            "status": "passed",
            "output": str(output),
            "content_sha256": payload["content_sha256"],
            "stored_logic_complete": False,
            "production_ready": False,
        }
    elif args.command == "verify-stored-logic-qualification":
        project_root = args.project_root.resolve()
        errors = validate_stored_logic_qualification(project_root)
        result = {
            "status": "passed" if not errors else "failed",
            "errors": errors,
            "stored_logic_complete": False,
            "production_ready": False,
        }
    elif args.command in {"build-db2-semantic-adapter", "verify-db2-semantic-adapter"}:
        project_root = args.project_root.resolve()
        model, _, fixtures = load_assets(project_root)
        adapter = Db2SourceAdapter(model, fixtures["rows"])
        profile_contract = build_profile_contract(model)
        ledger = build_db2_source_ledger(model)
        discovery = adapter.discover_schema()
        profile = adapter.profile_data(profile_contract)
        receipt = db2_source_conformance_receipt(adapter, model, profile_contract, ledger)
        output_root = project_root / "data-modernization/db2-semantic-adapter"
        expected = {
            "authfrds.discovery.json": discovery,
            "authfrds.profile.json": profile,
            "authfrds.compatibility-ledger.json": ledger,
            "authfrds.conformance.receipt.json": receipt,
        }
        errors = []
        if args.command == "build-db2-semantic-adapter":
            for name, payload in expected.items():
                write_json(output_root / name, payload)
        else:
            for name, payload in expected.items():
                path = output_root / name
                if not path.is_file() or json.loads(path.read_text(encoding="utf-8")) != payload:
                    errors.append(f"db2-semantic-adapter-drift:{name}")
        result = {
            "status": "passed" if not errors and receipt["status"] == "passed" else "failed",
            "errors": errors,
            "ledger_sha256": ledger["content_sha256"],
            "conformance_sha256": receipt["content_sha256"],
            "catalog_observed": False,
            "cdc_observed": False,
            "mainframe_equivalent": False,
            "production_ready": False,
        }
    elif args.command in {"build-oracle-source-qualification", "verify-oracle-source-qualification"}:
        project_root = args.project_root.resolve()
        expected = build_oracle_source_artifacts(project_root)
        output_root = (
            args.output_root.resolve()
            if args.command == "build-oracle-source-qualification" and args.output_root
            else project_root / "data-modernization/oracle-source-qualification"
        )
        errors = []
        if args.command == "build-oracle-source-qualification":
            for name, payload in expected.items():
                write_json(output_root / name, payload)
        else:
            for name, payload in expected.items():
                path = output_root / name
                if not path.is_file() or json.loads(path.read_text(encoding="utf-8")) != payload:
                    errors.append(f"oracle-source-qualification-drift:{name}")
            errors.extend(validate_procedure_artifacts(project_root, expected["procedure-qualification.json"]))
            errors.extend(validate_oracle_postgresql_source_qualification(project_root, expected["qualification.json"]))
        qualification = expected["qualification.json"]
        result = {
            "status": "passed" if not errors else "failed",
            "errors": sorted(set(errors)),
            "output_root": str(output_root),
            "qualification_sha256": qualification["content_sha256"],
            "development_ready": qualification["development_ready"],
            "supported_procedure_subset_qualified": qualification["supported_procedure_subset_qualified"],
            "database_migration_complete": False,
            "stored_logic_complete": False,
            "production_ready": False,
        }
    elif args.command in {"build-oracle-dialect-corpus", "verify-oracle-dialect-corpus"}:
        project_root = args.project_root.resolve()
        catalog, receipt, sql = build_oracle_dialect_artifacts(project_root)
        output_root = project_root / ORACLE_DIALECT_OUTPUT_ROOT
        errors = []
        if args.command == "build-oracle-dialect-corpus":
            write_json(output_root / "fixture-catalog.json", catalog)
            write_json(output_root / "model-conformance.receipt.json", receipt)
            write_text(output_root / "native-oracle-fixtures.sql", sql)
        else:
            errors.extend(validate_oracle_dialect_artifacts(project_root))
        result = {
            "status": "passed" if not errors else "failed",
            "errors": sorted(set(errors)),
            "output_root": str(output_root),
            "fixture_count": receipt["fixture_count"],
            "case_count": receipt["case_count"],
            "bounded_model_execution_observed": True,
            "native_oracle_execution_observed": False,
            "native_oracle_conformance": False,
            "production_ready": False,
        }
    elif args.command in {"build-sap-ase-source-adapter", "verify-sap-ase-source-adapter"}:
        project_root = args.project_root.resolve()
        expected = build_ase_artifacts()
        output_root = (
            args.output_root.resolve()
            if args.command == "build-sap-ase-source-adapter" and args.output_root
            else project_root / "data-modernization/sap-ase-source-adapter"
        )
        errors = []
        if args.command == "build-sap-ase-source-adapter":
            for name, payload in expected.items():
                write_json(output_root / name, payload)
        else:
            for name, payload in expected.items():
                path = output_root / name
                if not path.is_file() or json.loads(path.read_text(encoding="utf-8")) != payload:
                    errors.append(f"sap-ase-source-adapter-drift:{name}")
            errors.extend(validate_ase_qualification(expected["qualification.json"]))
        qualification = expected["qualification.json"]
        result = {
            "status": "passed" if not errors else "failed",
            "errors": sorted(set(errors)),
            "output_root": str(output_root),
            "qualification_sha256": qualification["content_sha256"],
            "source_adapter_qualified": qualification["source_adapter_qualified"],
            "conformance_cases": expected["conformance-corpus.json"]["case_count"],
            "target_selected": False,
            "target_migration_qualified": False,
            "live_ase_observed": False,
            "stored_logic_complete": False,
            "database_migration_complete": False,
            "production_ready": False,
        }
    else:
        key = os.environ.get("FACTORYDARK_DATA_EQUIVALENCE_KEY", "")
        payload = json.loads(args.receipt.read_text(encoding="utf-8"))
        result = sign(payload, key, args.signer)
        write_json(args.output, result)
        result = {"status": "passed", "output": str(args.output), "content_sha256": result["content_sha256"]}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("status") == "passed" else 1
