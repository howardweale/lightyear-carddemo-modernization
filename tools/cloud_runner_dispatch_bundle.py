"""Materialize public dispatch metadata without shell interpolation or private data."""
import argparse
import json
import os
from pathlib import Path

from lightyear_cloud_runner.signing import canonical, require, sha256


def materialize(bundle_text: str, policy_text: str, policy_sha256: str, output: Path) -> None:
    require(len(bundle_text.encode()) <= 60000, "Dispatch metadata exceeds limit")
    require(len(policy_text.encode()) <= 60000, "Policy exceeds limit")
    require(sha256(policy_text.encode()) == policy_sha256, "Reviewed environment policy hash differs")

    def strict(text):
        def pairs(items):
            result = {}
            for key, value in items:
                require(key not in result, "Duplicate JSON key")
                result[key] = value
            return result
        return json.loads(text, object_pairs_hook=pairs,
                          parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))

    bundle = strict(bundle_text)
    strict(policy_text)
    require(set(bundle) == {"request", "go", "witness"}, "Only public admission metadata is accepted")
    output.mkdir(parents=True, exist_ok=False)
    (output / "policy.json").write_bytes(policy_text.encode())
    for name, value in bundle.items():
        (output / (name + ".json")).write_bytes(canonical(value))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    materialize(os.environ["CLOUD_RUNNER_BUNDLE"], os.environ["CLOUD_RUNNER_POLICY"],
                os.environ["CLOUD_RUNNER_POLICY_SHA256"], args.output)
