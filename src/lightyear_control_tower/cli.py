from __future__ import annotations

import argparse
import json
from pathlib import Path

from .operational import OperationalEventStore
from .decisions import DecisionService, initialize_authority, verify_envelope, ZERO


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LIGHTYEAR live Control Tower utilities")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate", help="Validate the operational event chain")
    validate.add_argument("--database", type=Path, default=Path("work/control-tower/events.sqlite3"))
    events = subparsers.add_parser("events", help="Print recent operational events")
    events.add_argument("--database", type=Path, default=Path("work/control-tower/events.sqlite3"))
    events.add_argument("--after", type=int, default=0)
    events.add_argument("--limit", type=int, default=100)
    provision = subparsers.add_parser("init-operator", help="Provision an individual local operator credential; grants no approvals")
    provision.add_argument("--authority", type=Path, default=Path("work/control-tower/authority.json"))
    provision.add_argument("--operator-id", required=True)
    provision.add_argument("--operator-name", required=True)
    qualify = subparsers.add_parser("qualify", help="Require current signed normalizations and a passing UI-dispatched proof")
    qualify.add_argument("--authority", type=Path, default=Path("work/control-tower/authority.json"))
    qualify.add_argument("--root", type=Path, default=Path("."))
    qualify.add_argument("--graph", type=Path, default=Path("knowledge/composite/estate.snapshot.json.gz"))
    qualify.add_argument("--run-id", required=True)
    qualify.add_argument("--output", type=Path, required=True)
    verify = subparsers.add_parser("verify-session", help="Verify an exported session against a separately trusted public key")
    verify.add_argument("--record", type=Path, required=True)
    verify.add_argument("--trusted-public-key", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "init-operator":
        credential = initialize_authority(args.authority, args.operator_id, args.operator_name)
        print(json.dumps({"status": "provisioned", "credential_file": str(credential),
                          "next": "Start the Control Tower and use the individual credential to sign in. No decisions have been made."}, indent=2))
        return 0
    if args.command == "qualify":
        from lightyear_knowledge_graph.model import load_graph
        graph = load_graph(args.graph)
        service = DecisionService(args.root, args.authority, graph_identity=lambda: graph["content_sha256"], recover_runs=False)
        result = service.gate(args.run_id)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print(json.dumps({"status": result["status"], "reason_codes": result["reason_codes"], "receipt": str(args.output)}, indent=2))
        return 0 if result["status"] == "passed" else 1
    if args.command == "verify-session":
        record = json.loads(args.record.read_text())
        key = args.trusted_public_key.read_bytes()
        passed = verify_envelope(record, key) and record.get("record_type") == "control-tower-session-export"
        previous = ZERO
        for index, event in enumerate(record.get("events", []), 1):
            passed = passed and event.get("sequence") == index and event.get("previous_sha256") == previous and verify_envelope(event, key)
            previous = event.get("content_sha256")
        passed = passed and record.get("journal_head_sha256") == previous
        print(json.dumps({"status": "passed" if passed else "failed", "scope": "signature and chain integrity; current approval validity requires the live qualification gate"}))
        return 0 if passed else 1
    store = OperationalEventStore(args.database)
    if args.command == "validate":
        result = store.validate()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["status"] == "passed" else 1
    print(json.dumps({"events": store.events(args.after, args.limit)}, indent=2, sort_keys=True))
    return 0
