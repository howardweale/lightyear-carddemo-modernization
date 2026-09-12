"""Headless planning for CI or services: python -m lightyear_workflow emit."""
import argparse
import json
from pathlib import Path

from .artifacts import LIVE_PATH, emit, read_snapshot


def main(argv=None):
    parser = argparse.ArgumentParser(description="Emit or verify evidence actions; never execute them")
    parser.add_argument("command", choices=("emit", "verify"))
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, default=LIVE_PATH)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    try:
        if args.command == "emit":
            report = (args.report if args.report.is_absolute() else root / args.report) if args.report else None
            snapshot = emit(root, output, report)
            print(json.dumps({"status": "emitted", "output": str(output), "summary": snapshot["plan"]["summary"]}, indent=2))
            return 0
        result = read_snapshot(root, output)
        print(json.dumps({k: v for k, v in result.items() if k != "plan"}, indent=2))
        return 0 if result["status"] in {"snapshot", "stale"} else 1
    except (ValueError, OSError) as exc:
        print(json.dumps({"status": "failed", "reason": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
