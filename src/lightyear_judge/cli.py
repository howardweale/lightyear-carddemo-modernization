"""Operator CLI. Launch outside the agent account; stdout contains safe startup state only."""

import argparse
import json
from pathlib import Path
from .service import Judge, initialize, replay
from .http import create_server


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    from .graph_cli import parsers
    parsers(commands)
    init = commands.add_parser("init")
    init.add_argument("--data-root", type=Path, required=True)
    init.add_argument("--config", type=Path, required=True)
    serve = commands.add_parser("serve")
    serve.add_argument("--data-root", type=Path, required=True)
    serve.add_argument("--task", required=True)
    serve.add_argument("--port", type=int, default=8770)
    audit = commands.add_parser("replay")
    audit.add_argument("--data-root", type=Path, required=True)
    audit.add_argument("--public-key", type=Path, required=True)
    audit.add_argument("--journal-head", required=True)
    decision = commands.add_parser("import-decision")
    decision.add_argument("--data-root", type=Path, required=True)
    decision.add_argument("--attempt", required=True)
    decision.add_argument("--proof", type=Path, required=True)
    decision.add_argument("--trusted-head", required=True)
    budget = commands.add_parser("inventory-budget")
    budget.add_argument("--data-root", type=Path, required=True)
    budget.add_argument("--new-limit", type=int, required=True)
    budget.add_argument("--proof", type=Path)
    budget.add_argument("--trusted-head")
    args = parser.parse_args(argv)
    if args.command in {"graph-project", "graph-leak-check"}:
        from .graph_cli import execute
        result = execute(args)
        print(json.dumps({"status": "written", "sha256": result["content_sha256"], "model_calls": 0}))
    elif args.command == "init":
        initialize(args.data_root, json.loads(args.config.read_text()))
        print(json.dumps({"status": "initialized", "model_calls": 0}))
    elif args.command == "serve":
        judge = Judge(args.data_root, task=args.task)
        server = create_server(judge, args.port)
        print(
            json.dumps(
                {"status": "ready", "port": server.server_port, "task": args.task}
            ),
            flush=True,
        )
        try:
            server.serve_forever()
        finally:
            server.server_close()
            judge.close()
    elif args.command == "inventory-budget":
        from .review import inventory_budget
        from lightyear_mainframe.zos_evidence import read_json

        print(
            json.dumps(
                inventory_budget(
                    args.data_root,
                    args.new_limit,
                    proof=read_json(args.proof) if args.proof else None,
                    expected_head=args.trusted_head,
                )
            )
        )
    elif args.command == "import-decision":
        from .review import queue_decision
        from lightyear_mainframe.zos_evidence import read_json

        queue_decision(
            args.data_root, args.attempt, read_json(args.proof), args.trusted_head
        )
        print(json.dumps({"status": "decision-imported", "model_calls": 0}))
    else:
        print(
            json.dumps(
                replay(args.data_root, args.public_key.read_bytes(), args.journal_head)
            )
        )


if __name__ == "__main__":
    main()
