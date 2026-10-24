"""CI-only retained historical audit; output contains public paths/hashes only."""
import argparse
import json
import os
from pathlib import Path
import re
import sys
from tools.operational_claims import audit


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if os.environ.get("GITHUB_ACTIONS") != "true" or not re.fullmatch(r"[0-9a-f]{40}", args.revision):
            raise ValueError("ci-revision-required")
        report = audit(Path.cwd(), args.revision)
        report.update(run_id=os.environ.get("GITHUB_RUN_ID"), run_attempt=os.environ.get("GITHUB_RUN_ATTEMPT"))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(report, stream, indent=2)
            stream.write("\n")
        print(json.dumps(dict(unsupported_count=report["unsupported_count"], files=len(report["rows"]), errors=len(report["errors"]))))
        return 1 if report["errors"] else 0
    except Exception:
        print("Operational audit incomplete", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
