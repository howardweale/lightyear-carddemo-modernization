"""Operator CLI. Launch outside the agent account; stdout contains safe startup state only."""

import argparse
import json
from pathlib import Path
from .service import Judge, initialize, replay
from .http import create_server


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
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
    args = parser.parse_args(argv)
    if args.command == "init":
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
    else:
        print(
            json.dumps(
                replay(args.data_root, args.public_key.read_bytes(), args.journal_head)
            )
        )


if __name__ == "__main__":
    main()
