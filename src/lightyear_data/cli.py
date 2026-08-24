from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from lightyear_common.io import write_json

from .builder import build_assets, load_assets
from .contracts import seal, sign
from .equivalence import offline_equivalence
from .live import DockerOracleRunner, DockerPostgresExactRunner, aggregate_receipts
from .oracle import OracleAdapter
from .postgres import PostgreSQLAdapter, fixture_sql
from .validation import validate_assets


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
    else:
        key = os.environ.get("FACTORYDARK_DATA_EQUIVALENCE_KEY", "")
        payload = json.loads(args.receipt.read_text(encoding="utf-8"))
        result = sign(payload, key, args.signer)
        write_json(args.output, result)
        result = {"status": "passed", "output": str(args.output), "content_sha256": result["content_sha256"]}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("status") == "passed" else 1
