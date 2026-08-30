from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from lightyear_common.io import write_json

from .builder import build_assets, load_assets
from .contracts import seal, sign
from .db2 import Db2SourceAdapter, build_db2_source_ledger, db2_source_conformance_receipt
from .equivalence import offline_equivalence
from .live import DockerOracleRunner, DockerPostgresExactRunner, aggregate_receipts
from .oracle import OracleAdapter
from .oracle_postgres_proof import (
    build_oracle_postgresql_proof,
    validate_oracle_postgresql_proof,
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
    else:
        key = os.environ.get("FACTORYDARK_DATA_EQUIVALENCE_KEY", "")
        payload = json.loads(args.receipt.read_text(encoding="utf-8"))
        result = sign(payload, key, args.signer)
        write_json(args.output, result)
        result = {"status": "passed", "output": str(args.output), "content_sha256": result["content_sha256"]}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("status") == "passed" else 1
