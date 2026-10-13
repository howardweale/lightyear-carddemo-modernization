"""Offline plan-only entry point. There is intentionally no apply/run command."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from .contracts import admission
from .signing import canonical, require, sha256


def load(path):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "Duplicate JSON key: " + key)
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("request", "go", "witness", "policy", "policy-sha256", "output"):
        parser.add_argument("--" + flag, required=True)
    args = parser.parse_args()
    require(sha256(Path(args.policy).read_bytes()) == args.policy_sha256, "Policy file is not the reviewed version")
    plan = admission(load(args.request), load(args.go), load(args.witness), load(args.policy),
                     datetime.now(timezone.utc))
    with Path(args.output).open("xb") as stream:
        stream.write(canonical(plan) + b"\n")
    print("Validated plan only; no cloud API calls or run authorization were performed.")


if __name__ == "__main__":
    main()
