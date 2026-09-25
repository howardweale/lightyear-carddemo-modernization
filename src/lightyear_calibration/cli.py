"""Product entry point for read-only corpus calibration."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .adapters import ADAPTERS, discover, import_idempiere, scan
from .contracts import CalibrationError, read_json, require
from .instrument import assess, build_report, compare_reports, validate_report
from .reporting import publish


def parser():
    p = argparse.ArgumentParser(description="Measure comparator decidability without invoking customer systems or applying normalization rules")
    commands = p.add_subparsers(dest="command", required=True)
    d = commands.add_parser("discover", help="Inventory and pair every eligible file by relative path, retaining unpaired files")
    d.add_argument("--source", required=True, type=Path)
    d.add_argument("--target", required=True, type=Path)
    d.add_argument("--adapter", choices=ADAPTERS, required=True)
    d.add_argument("--corpus-id", required=True)
    d.add_argument("--output", required=True, type=Path)
    s = commands.add_parser("scan", help="Run the selected gate over every case in a complete corpus manifest")
    s.add_argument("--manifest", required=True, type=Path)
    s.add_argument("--output", required=True, type=Path)
    s.add_argument("--minimum-decidability", type=float)
    s.add_argument("--context", type=Path, help="Input-bound schema/session baseline")
    b = commands.add_parser("baseline", help="Inventory required schema/session facts without inventing a catalog")
    b.add_argument("--manifest", required=True, type=Path)
    b.add_argument("--output", required=True, type=Path)
    r = commands.add_parser("replay-idempiere", help="Replay the pinned paired source and publish actual before/after counts")
    r.add_argument("--source", required=True, type=Path)
    r.add_argument("--report", required=True, type=Path)
    r.add_argument("--pairing-manifest", required=True, type=Path)
    r.add_argument("--output", required=True, type=Path)
    r.add_argument("--context", type=Path, help="Optional reviewed baseline from a prior pinned replay")
    i = commands.add_parser("import-idempiere", help="Calibrate a retained comparison report without claiming a fresh source replay")
    i.add_argument("--report", required=True, type=Path)
    i.add_argument("--pairing-manifest", required=True, type=Path)
    i.add_argument("--output", required=True, type=Path)
    i.add_argument("--minimum-decidability", type=float)
    a = commands.add_parser("assess", help="Recompute a narrowed draft proposal's blast radius")
    a.add_argument("--report", required=True, type=Path)
    a.add_argument("--proposal", required=True, type=Path)
    a.add_argument("--output", required=True, type=Path)
    c = commands.add_parser("compare", help="Measure before/after results on identical corpus contents")
    c.add_argument("--before", required=True, type=Path)
    c.add_argument("--after", required=True, type=Path)
    c.add_argument("--output", required=True, type=Path)
    v = commands.add_parser("validate", help="Verify report integrity, accounting and proposal scopes")
    v.add_argument("report", type=Path)
    return p


def write_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(value, sort_keys=True, indent=2) + "\n")


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "discover":
            result = discover(args.source, args.target, args.adapter, args.corpus_id)
            for root in (args.source, args.target):
                require(not args.output.resolve().is_relative_to(root.resolve()), "Keep manifests outside corpus roots")
            write_new(args.output, result)
        elif args.command == 'baseline':
            from .sql_context import baseline
            manifest=read_json(args.manifest)
            require(manifest['adapter']=='oracle-postgresql-sql','Baseline requires SQL corpus')
            for root in manifest['roots'].values():
                require(not args.output.resolve().is_relative_to((args.manifest.parent/root).resolve()),'Keep baselines outside corpus roots')
            snapshot,texts=scan(manifest,args.manifest.parent,include_texts=True)
            write_new(args.output,baseline(snapshot,texts))
        elif args.command == 'replay-idempiere':
            from .replay import replay_idempiere
            result=replay_idempiere(args.source,read_json(args.report),read_json(args.pairing_manifest),args.output,context=read_json(args.context) if args.context else None)
            print(json.dumps(result['counts']))
            return 0
        elif args.command in {"scan", "import-idempiere"}:
            require(not args.output.exists(), "Output already exists; choose a new evidence directory")
            if args.command == "scan":
                manifest = read_json(args.manifest)
                for root in manifest["roots"].values():
                    require(not args.output.resolve().is_relative_to((args.manifest.parent / root).resolve()), "Keep reports outside corpus roots")
                snapshot = scan(manifest, args.manifest.parent, context=read_json(args.context) if args.context else None)
            else:
                snapshot = import_idempiere(read_json(args.report), read_json(args.pairing_manifest))
            result = build_report(snapshot, args.minimum_decidability)
            publish(result, args.output)
            print(json.dumps({"status": "reported", "output": str(args.output), "summary": result["summary"], "threshold": result["threshold"]}))
            return 3 if result["threshold"]["status"] in {"below-minimum", "no-comparable-units"} else 0
        elif args.command == "assess":
            report = validate_report(read_json(args.report))
            result = assess(report, read_json(args.proposal))
            write_new(args.output, result)
        elif args.command == "compare":
            result = compare_reports(read_json(args.before), read_json(args.after))
            write_new(args.output, result)
            print(json.dumps({"status": "review-required" if result["review_required"] else "compared", "output": str(args.output)}))
            return 3 if result["review_required"] else 0
        else:
            result = validate_report(read_json(args.report))
        print(json.dumps({"status": "valid" if args.command == "validate" else "written", "output": str(getattr(args, "output", args.report if hasattr(args, "report") else ""))}))
        return 0
    except (CalibrationError, OSError, ValueError, KeyError, TypeError, RecursionError) as exc:
        print(json.dumps({"status": "invalid", "reason": str(exc)}))
        return 2
