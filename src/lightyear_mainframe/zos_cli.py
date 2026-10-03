"""Folder-delivery commands. Console output is deliberately value-free."""

import argparse
import json
from pathlib import Path

from .zos_evidence import Signer, initialize_key, read_json

COMMANDS = {
    "init-intake-key",
    "intake",
    "decode-run",
    "observe-run",
    "compare-runs",
    "delta",
    "prepare-intcalc-inputs",
    "run-intcalc",
    "verdict-intcalc",
    "replay-intcalc",
    "rehearse-intake",
    "bridge-self-test",
}


def main(argv):
    parser = argparse.ArgumentParser(
        description="Offline z/OS folder intake; no model or Docker access"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name in sorted(COMMANDS):
        p = sub.add_parser(name)
        if name == "init-intake-key":
            p.add_argument("key", type=Path)
            continue
        if name == "intake":
            p.add_argument("folder", type=Path)
            p.add_argument("--source-description", default="Maintec operator delivery")
        elif name == "compare-runs":
            p.add_argument("run1", type=Path)
            p.add_argument("run2", type=Path)
        elif name not in ("rehearse-intake", "bridge-self-test"):
            p.add_argument("run", type=Path)
        if name in (
            "intake",
            "prepare-intcalc-inputs",
            "run-intcalc",
            "verdict-intcalc",
            "rehearse-intake",
        ):
            p.add_argument("--key", required=True, type=Path)
        if name not in ("intake", "rehearse-intake", "bridge-self-test"):
            p.add_argument("--public-key", required=True, type=Path)
        if name in ("run-intcalc", "rehearse-intake"):
            p.add_argument("--jar", required=True, type=Path)
        if name in ("verdict-intcalc", "replay-intcalc"):
            p.add_argument("--tower-public-key", type=Path)
        if name == "verdict-intcalc":
            p.add_argument("--normalizations", type=Path)
            p.add_argument("--tower-head")
    args = parser.parse_args(argv)
    try:
        key = args.public_key.read_bytes() if hasattr(args, "public_key") else None
        signer = (
            Signer(args.key)
            if hasattr(args, "key") and args.command != "init-intake-key"
            else None
        )
        if args.command == "init-intake-key":
            initialize_key(args.key)
            result = dict(
                status="created",
                message="Keep the private key outside delivery folders; trust the public key out of band.",
            )
        elif args.command == "intake":
            from .zos_intake import intake

            arrival, result = intake(args.folder, args.source_description, signer)
            result = {**result, "arrival_id": arrival.name}
        elif args.command in ("decode-run", "observe-run"):
            from .zos_intake import decode_run

            run, decoded = decode_run(args.run, key)
            result = dict(
                status="decoded",
                datasets=len(decoded["datasets"]),
                findings=len(run["findings"]),
                code_pages=sorted(
                    {
                        v["descriptor"]["code_page_observation"]
                        for v in decoded["datasets"].values()
                    }
                ),
            )
        elif args.command == "compare-runs":
            from .zos_compare import compare_runs

            r = compare_runs(args.run1, args.run2, key)
            result = dict(
                schema=r["schema"],
                datasets=len(r["datasets"]),
                findings=len(r["findings"]),
                proposals=len(r["proposals"]),
            )
        elif args.command == "delta":
            from .zos_compare import delta

            r = delta(args.run, key)
            result = dict(
                schema=r["schema"],
                datasets=len(r["datasets"]),
                findings=len(r["findings"]),
            )
        elif args.command == "prepare-intcalc-inputs":
            from .zos_bridge import prepare

            r = prepare(args.run, key, signer)
            result = dict(
                status="prepared", sha256=r["content_sha256"], inputs=len(r["files"])
            )
        elif args.command == "run-intcalc":
            from .zos_bridge import run_candidate

            r = run_candidate(args.run, args.jar, key, signer)
            result = dict(
                status=r["status"],
                return_code=r["return_code"],
                sha256=r["content_sha256"],
            )
        elif args.command == "verdict-intcalc":
            from .zos_bridge import verdict

            r = verdict(
                args.run,
                key,
                signer,
                normalizations=(
                    read_json(args.normalizations) if args.normalizations else None
                ),
                tower_key=(
                    args.tower_public_key.read_bytes()
                    if args.tower_public_key
                    else None
                ),
                tower_head=args.tower_head,
            )
            result = dict(verdict=r["verdict"], sha256=r["content_sha256"])
        elif args.command == "replay-intcalc":
            from .zos_bridge import replay

            result = replay(
                args.run,
                key,
                tower_key=(
                    args.tower_public_key.read_bytes()
                    if args.tower_public_key
                    else None
                ),
            )
        else:
            from .zos_rehearsal import bridge_self_test, rehearse

            result = (
                bridge_self_test()
                if args.command == "bridge-self-test"
                else rehearse(signer, args.jar)
            )
        print(json.dumps(result, sort_keys=True))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        # Never echo exceptions containing hidden record bytes, source text or paths.
        print(
            json.dumps(
                dict(
                    status="refused",
                    error_type=type(exc).__name__,
                    message="Evidence or configuration validation failed. Review the local gaps/evidence and runbook; no values were printed.",
                )
            )
        )
        return 2
