from __future__ import annotations

import argparse
import json
from pathlib import Path

from .operational import OperationalEventStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LIGHTYEAR live Control Tower utilities")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate", help="Validate the operational event chain")
    validate.add_argument("--database", type=Path, default=Path("work/control-tower/events.sqlite3"))
    events = subparsers.add_parser("events", help="Print recent operational events")
    events.add_argument("--database", type=Path, default=Path("work/control-tower/events.sqlite3"))
    events.add_argument("--after", type=int, default=0)
    events.add_argument("--limit", type=int, default=100)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store = OperationalEventStore(args.database)
    if args.command == "validate":
        result = store.validate()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["status"] == "passed" else 1
    print(json.dumps({"events": store.events(args.after, args.limit)}, indent=2, sort_keys=True))
    return 0
