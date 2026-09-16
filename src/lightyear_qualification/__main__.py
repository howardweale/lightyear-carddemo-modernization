from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from lightyear_common.io import write_json
from lightyear_data.contracts import seal

from .campaign import check_freeze, development_campaign, freeze, metrics, run_case, save_report
from .protocol import keys, normalize, strict_json, validate_command


def main(argv=None):
    parser = argparse.ArgumentParser(description="Bounded local verifier qualification; no partner claims")
    actions = parser.add_subparsers(dest="action", required=True)
    run = actions.add_parser("run", help="Run the public executable challenge campaign")
    run.add_argument("--output", type=Path, required=True)
    gates = actions.add_parser("runtime-gates", help="MS76: challenge existing CloudBank and CardDemo gate paths")
    gates.add_argument("--output", type=Path, required=True)
    frozen = actions.add_parser("freeze", help="Freeze code, contract and public corpus before external challenge review")
    frozen.add_argument("--output", type=Path, required=True)
    evaluate = actions.add_parser("evaluate", help="Evaluate a local adapter against reviewer-provided cases")
    evaluate.add_argument("--adapter", type=Path, required=True)
    evaluate.add_argument("--cases", type=Path, required=True)
    evaluate.add_argument("--freeze", type=Path, required=True)
    evaluate.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.output.exists():
            raise ValueError("output already exists; choose a new evidence path")
        if args.action == "runtime-gates":
            from .runtime_gates import run, save
            report = run()
            save(report, args.output)
            print(json.dumps({"status": report["status"], "report": str(args.output / "report.md")}))
            return 0 if report["status"] == "passed" else 1
        if args.action == "run":
            report = development_campaign()
            save_report(report, args.output)
            print(json.dumps({"status": report["status"], "faults": report["fault_counts"], "report": str(args.output / "report.md")}))
            return 0 if report["status"] == "passed" else 1
        if args.action == "freeze":
            write_json(args.output, freeze())
            return 0
        frozen = strict_json(args.freeze.read_text(encoding="utf-8"))
        check_freeze(frozen)
        adapter = strict_json(args.adapter.read_text(encoding="utf-8"))
        keys(adapter, {"id", "argv", "artifact", "artifact_sha256"})
        if not isinstance(adapter["id"], str) or not adapter["id"]:
            raise ValueError("adapter requires an id")
        if not isinstance(adapter["argv"], list) or not adapter["argv"] or not all(isinstance(a, str) and a for a in adapter["argv"]):
            raise ValueError("adapter argv must be a nonempty string list; no shell")
        artifact = Path(adapter["artifact"]).resolve()
        if hashlib.sha256(artifact.read_bytes()).hexdigest() != adapter["artifact_sha256"]:
            raise ValueError("adapter artifact hash mismatch")
        if str(artifact) not in adapter["argv"]:
            raise ValueError("bound artifact must appear explicitly in argv")
        corpus = strict_json(args.cases.read_text(encoding="utf-8"))
        if not isinstance(corpus, list) or not 1 <= len(corpus) <= 1000:
            raise ValueError("cases must contain between 1 and 1000 scenarios")
        ids = set()
        for case in corpus:
            keys(case, {"id", "behavior", "accounts", "steps"})
            if not isinstance(case["id"], str) or not case["id"] or case["id"] in ids:
                raise ValueError("case identity missing or duplicated")
            ids.add(case["id"])
            if not isinstance(case["behavior"], str) or not case["behavior"]:
                raise ValueError("case requires a named behavior")
            normalize({"encoding": "integer-cents-v1", "accounts": case["accounts"], "operations": [], "outcomes": []})
            if not isinstance(case["steps"], list) or not 1 <= len(case["steps"]) <= 100:
                raise ValueError("each case requires 1 to 100 steps")
            for step in case["steps"]:
                keys(step, {"command", "expected"})
                validate_command(step["command"])
                keys(step["expected"], {"accounts", "operations", "outcomes"})
                canonical = normalize({"encoding": "integer-cents-v1", **step["expected"]})
                if canonical != step["expected"]:
                    raise ValueError("expectations must be canonical and explicit")
        runs = [run_case(adapter, case) for case in corpus]
        check_freeze(frozen)
        if hashlib.sha256(artifact.read_bytes()).hexdigest() != adapter["artifact_sha256"]:
            raise ValueError("adapter artifact changed during evaluation")
        summary = metrics(runs)
        report = seal({"kind": "verifier-external-evaluation-v1", "freeze": frozen, "adapter": adapter,
                       "cases_sha256": hashlib.sha256(args.cases.read_bytes()).hexdigest(),
                       "metrics": summary, "runs": runs,
                       "independent_review": "not-attested", "partner_qualified": False})
        write_json(args.output, report)
        print(json.dumps(summary))
        return 1 if summary["failed"] else 2 if summary["indeterminate"] else 0
    except (ValueError, OSError, TypeError, KeyError) as exc:
        print(json.dumps({"status": "indeterminate", "reason": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
