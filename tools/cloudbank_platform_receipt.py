#!/usr/bin/env python3
"""Offline public plan/recipe/observation/receipt preparation and verification."""
import argparse
from datetime import datetime, timezone
from pathlib import Path

from lightyear_data.cloudbank_platform_plan import DRILLS, canonical, compile_plan, decode, digest, require
from lightyear_data.cloudbank_platform_drills import recipes, prepare_observation
from lightyear_data.cloudbank_platform_receipt import evaluate, verify_compound


def load(path):
    require(path is not None, "required-public-input-missing")
    return decode(path.read_bytes())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("expectations", "recipes", "observe", "judge", "verify"))
    for key in ("plan", "rollout", "output"):
        parser.add_argument("--"+key, type=Path, required=True)
    for key in ("iac-commit", "plan-sha256", "rollout-sha256", "policy-sha256"):
        parser.add_argument("--"+key, required=True)
    for key in ("legacy", "readback", "legacy-validation", "trust", "code", "observations", "receipt"):
        parser.add_argument("--"+key, type=Path)
    parser.add_argument("--trust-sha256")
    parser.add_argument("--drill", choices=DRILLS)
    parser.add_argument("--run-id")
    parser.add_argument("--evidence-class", choices=("offline-fixture", "live-nonproduction"))
    parser.add_argument("--started-at")
    parser.add_argument("--finished-at")
    args = parser.parse_args(argv)
    contract = compile_plan(args.plan.read_bytes(), args.rollout.read_bytes(), commit=args.iac_commit,
                            plan_sha256=args.plan_sha256, rollout_sha256=args.rollout_sha256,
                            policy_sha256=args.policy_sha256)
    if args.action == "expectations":
        result = contract
    elif args.action == "recipes":
        result = recipes(contract)
    elif args.action == "observe":
        require(args.drill in DRILLS and args.run_id and args.evidence_class
                and args.started_at and args.finished_at, "observation-scope-required")
        result = prepare_observation(contract, args.drill, load(args.legacy), load(args.readback),
                                     load(args.legacy_validation), run_id=args.run_id,
                                     evidence_class=args.evidence_class, started_at=args.started_at,
                                     finished_at=args.finished_at)
    else:
        require(args.trust is not None and digest(args.trust.read_bytes()) == args.trust_sha256,
                "out-of-band-trust-policy-digest-required")
        policy, code, observations = load(args.trust), load(args.code), load(args.observations)
        now = datetime.now(timezone.utc).isoformat()
        result = (evaluate(contract, code, observations, policy, now=now) if args.action == "judge" else
                  verify_compound(load(args.receipt), contract, code, observations, policy, now=now))
    # Never overwrite a retained observation, signing request or receipt.
    with args.output.open("xb") as stream:
        stream.write(canonical(result) + b"\n")
    return 1 if result.get("verdict") in {"FAIL", "NOT RUN"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
