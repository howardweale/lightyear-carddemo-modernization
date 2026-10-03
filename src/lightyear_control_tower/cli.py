from __future__ import annotations

import argparse
import json
from pathlib import Path

from .operational import OperationalEventStore
from .decisions import DecisionService, initialize_authority, verify_envelope, ZERO


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="LIGHTYEAR live Control Tower utilities"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    zos = subparsers.add_parser(
        "init-carddemo-workspace",
        help="Create a no-values intake workspace; no identities or approvals",
    )
    zos.add_argument("--root", type=Path, required=True)
    validate = subparsers.add_parser(
        "validate", help="Validate the operational event chain"
    )
    validate.add_argument(
        "--database", type=Path, default=Path("work/control-tower/events.sqlite3")
    )
    events = subparsers.add_parser("events", help="Print recent operational events")
    events.add_argument(
        "--database", type=Path, default=Path("work/control-tower/events.sqlite3")
    )
    events.add_argument("--after", type=int, default=0)
    events.add_argument("--limit", type=int, default=100)
    provision = subparsers.add_parser(
        "init-operator",
        help="Provision an individual local operator credential; grants no approvals",
    )
    provision.add_argument(
        "--authority", type=Path, default=Path("work/control-tower/authority.json")
    )
    provision.add_argument(
        "--workload",
        choices=("workload:carddemo-intcalc", "cloudbank:retained-value-conservation"),
        default="workload:carddemo-intcalc",
    )
    provision.add_argument("--operator-id", required=True)
    provision.add_argument("--operator-name", required=True)
    qualify = subparsers.add_parser(
        "qualify",
        help="Headless qualification of current signed normalizations and a recorded proof",
    )
    qualify.add_argument(
        "--authority", type=Path, default=Path("work/control-tower/authority.json")
    )
    qualify.add_argument("--root", type=Path, default=Path("."))
    qualify.add_argument(
        "--graph",
        type=Path,
        default=Path("knowledge/composite/estate.snapshot.json.gz"),
    )
    qualify.add_argument("--run-id", required=True)
    qualify.add_argument("--output", type=Path, required=True)
    verify = subparsers.add_parser(
        "verify-session",
        help="Verify an exported session against a separately trusted public key",
    )
    verify.add_argument("--record", type=Path, required=True)
    verify.add_argument("--trusted-public-key", type=Path, required=True)
    provision = subparsers.add_parser(
        "provision", help="Create a scoped Console identity with NO roles"
    )
    provision.add_argument("--authority", type=Path, required=True)
    provision.add_argument("--scope", required=True)
    provision.add_argument("--operator-id", required=True)
    provision.add_argument("--operator-name", required=True)
    provision.add_argument(
        "--identity-kind", choices=("human", "customer", "agent"), default="human"
    )
    grant = subparsers.add_parser(
        "grant-roles",
        help="Local authority administration; journal an explicit scope role assignment",
    )
    grant.add_argument("--root", type=Path, required=True)
    grant.add_argument("--authority", type=Path, required=True)
    grant.add_argument("--operator-id", required=True)
    grant.add_argument("--roles", nargs="*", default=[])
    grant.add_argument("--reason", required=True)
    grant.add_argument("--workloads", nargs="*", default=[])
    serve = subparsers.add_parser(
        "serve", help="Serve the decision-only loopback console"
    )
    serve.add_argument("--root", type=Path, required=True)
    serve.add_argument("--authority", type=Path, required=True)
    serve.add_argument("--port", type=int, default=8766)
    add = subparsers.add_parser(
        "add-identity",
        help="Provision another individual in a scoped authority, with no roles",
    )
    add.add_argument("--root", type=Path, required=True)
    add.add_argument("--authority", type=Path, required=True)
    add.add_argument("--operator-id", required=True)
    add.add_argument("--operator-name", required=True)
    add.add_argument(
        "--identity-kind", choices=("human", "customer", "agent"), default="human"
    )
    add.add_argument("--credential-output", type=Path, required=True)
    exp = subparsers.add_parser(
        "verify-export", help="Offline scoped archive and dual-release verification"
    )
    exp.add_argument("--archive", type=Path, required=True)
    exp.add_argument("--trusted-public-key", type=Path, required=True)
    cat = subparsers.add_parser(
        "catalogue-check", help="Check signed catalogue and both public projections"
    )
    cat.add_argument("--root", type=Path, default=Path("."))
    cat.add_argument("--trusted-public-key", type=Path, required=True)
    cat.add_argument("--qualification-trust", type=Path, required=True)
    cat.add_argument(
        "--public", type=Path, default=Path("docs/catalogue/lanes.public.json")
    )
    cat.add_argument("--website", type=Path, required=True)
    verify_dec = subparsers.add_parser(
        "verify-decision", help="Verify a decision proof at a trusted journal head"
    )
    verify_dec.add_argument("--record", type=Path, required=True)
    verify_dec.add_argument("--trusted-public-key", type=Path, required=True)
    verify_dec.add_argument("--kind", required=True)
    verify_dec.add_argument("--scope", required=True)
    verify_dec.add_argument("--bound", type=Path, required=True)
    verify_dec.add_argument("--journal-head", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    from .features import feature

    if args.command == "init-carddemo-workspace":
        from .carddemo_policy import initialize_workspace

        print(json.dumps(initialize_workspace(args.root)))
        return 0

    required = {
        "serve": "server",
        "verify-export": "workspace",
        "catalogue-check": "catalogue",
    }.get(args.command)
    if required and feature(required) is None:
        parser.error("The " + required + " delivery unit is not installed")
    if args.command in {"serve", "add-identity"}:
        if (
            args.command == "add-identity"
            and args.credential_output.resolve().is_relative_to(args.root.resolve())
        ):
            parser.error(
                "Credential output must be outside the engine-writable data root"
            )
        from .console import ConsoleService

        service = ConsoleService(args.root, args.authority)
        try:
            if args.command == "serve":
                from .server import create_server

                server = create_server(service, port=args.port)
                print(
                    "Decision console: http://127.0.0.1:" + str(server.server_port),
                    flush=True,
                )
                try:
                    server.serve_forever()
                finally:
                    server.server_close()
            else:
                import os

                # Reserve a private, new output before creating the identity.
                fd = os.open(
                    args.credential_output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
                )
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(
                        service.add_identity(
                            args.operator_id,
                            args.operator_name,
                            identity_kind=args.identity_kind,
                        )
                    )
                print(
                    json.dumps(
                        {
                            "status": "provisioned",
                            "roles": [],
                            "credential_file": str(args.credential_output),
                        }
                    )
                )
        finally:
            service.close()
        return 0
    if args.command in {"verify-export", "catalogue-check"}:
        try:
            if args.command == "verify-export":
                from .workspaces import verify_export
                from .requests import read_json

                result = verify_export(
                    read_json(args.archive), args.trusted_public_key.read_bytes()
                )
            else:
                from .catalogue import consistency
                from .trust import qualification_key

                result = consistency(
                    args.root,
                    args.trusted_public_key.read_bytes(),
                    args.public,
                    args.website,
                    qualification_key=qualification_key(
                        args.root, args.qualification_trust
                    ),
                )
            print(json.dumps(result))
            return 0
        except (ValueError, KeyError, OSError) as exc:
            print(
                json.dumps(
                    {
                        "status": "refused",
                        "reason_code": getattr(exc, "code", "invalid-evidence"),
                    }
                )
            )
            return 1
    if args.command == "provision":
        from .console import provision

        credential = provision(
            args.authority,
            args.scope,
            args.operator_id,
            args.operator_name,
            identity_kind=args.identity_kind,
        )
        print(
            json.dumps(
                {
                    "status": "provisioned",
                    "credential_file": str(credential),
                    "roles": [],
                }
            )
        )
        return 0
    if args.command == "grant-roles":
        from .console import ConsoleService

        service = ConsoleService(args.root, args.authority)
        try:
            result = service.grant_roles(
                args.operator_id,
                args.roles,
                reason=args.reason,
                workloads=args.workloads,
            )
        finally:
            service.close()
        print(
            json.dumps(
                {"status": "recorded", "decision_sha256": result["content_sha256"]}
            )
        )
        return 0
    if args.command == "verify-decision":
        from .verification import verify_decision, DecisionVerificationError

        try:
            verify_decision(
                json.loads(args.record.read_bytes()),
                args.trusted_public_key.read_bytes(),
                args.kind,
                json.loads(args.bound.read_bytes()),
                scope=args.scope,
                expected_head=args.journal_head,
            )
            print(json.dumps({"status": "verified"}))
            return 0
        except DecisionVerificationError as exc:
            print(json.dumps({"status": "refused", "reason_code": exc.code}))
            return 1
    if args.command == "init-operator":
        credential = initialize_authority(
            args.authority,
            args.operator_id,
            args.operator_name,
            workload_id=args.workload,
        )
        print(
            json.dumps(
                {
                    "status": "provisioned",
                    "credential_file": str(credential),
                    "next": "Start the Control Tower and use the individual credential to sign in. No decisions have been made.",
                },
                indent=2,
            )
        )
        return 0
    if args.command == "qualify":
        from lightyear_knowledge_graph.model import load_graph

        graph = load_graph(args.graph)
        service = DecisionService(
            args.root,
            args.authority,
            graph_identity=lambda: graph["content_sha256"],
            recover_runs=False,
            decision_only=False,
        )
        result = service.gate(args.run_id)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print(
            json.dumps(
                {
                    "status": result["status"],
                    "reason_codes": result["reason_codes"],
                    "receipt": str(args.output),
                },
                indent=2,
            )
        )
        return 0 if result["status"] == "passed" else 1
    if args.command == "verify-session":
        record = json.loads(args.record.read_text())
        key = args.trusted_public_key.read_bytes()
        passed = (
            verify_envelope(record, key)
            and record.get("record_type") == "control-tower-session-export"
        )
        previous = ZERO
        for index, event in enumerate(record.get("events", []), 1):
            passed = (
                passed
                and event.get("sequence") == index
                and event.get("previous_sha256") == previous
                and verify_envelope(event, key)
            )
            previous = event.get("content_sha256")
        passed = passed and record.get("journal_head_sha256") == previous
        print(
            json.dumps(
                {
                    "status": "passed" if passed else "failed",
                    "scope": "signature and chain integrity; current approval validity requires the live qualification gate",
                }
            )
        )
        return 0 if passed else 1
    store = OperationalEventStore(args.database)
    if args.command == "validate":
        result = store.validate()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["status"] == "passed" else 1
    print(
        json.dumps(
            {"events": store.events(args.after, args.limit)}, indent=2, sort_keys=True
        )
    )
    return 0
