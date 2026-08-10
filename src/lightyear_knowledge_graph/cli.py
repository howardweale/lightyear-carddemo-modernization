from __future__ import annotations

import argparse
import json
from pathlib import Path

from .builder import build_graph, write_receipt
from .model import load_graph
from .query import neighborhood, shortest_trace
from .validation import rule_gaps, validate_graph


DEFAULT_LEGACY_COMMIT = "59cc6c2fd7ebd7ef7925cad552a01a4b8b6e4d5e"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LIGHTYEAR evidence-aware modernization knowledge graph")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="Build a deterministic graph snapshot")
    build.add_argument("--legacy-root", type=Path, required=True)
    build.add_argument("--modern-root", type=Path, default=Path("."))
    build.add_argument("--manifest", type=Path, default=Path("knowledge/mappings/carddemo-intcalc.json"))
    build.add_argument("--output", type=Path, default=Path("knowledge/graph.snapshot.json.gz"))
    build.add_argument("--receipt", type=Path, default=Path("knowledge/graph.receipt.json"))
    build.add_argument("--legacy-commit", default=DEFAULT_LEGACY_COMMIT)
    build.add_argument("--modern-commit", default="working-tree")

    validate = subparsers.add_parser("validate", help="Validate graph integrity and rule coverage")
    validate.add_argument("--graph", type=Path, default=Path("knowledge/graph.snapshot.json.gz"))

    stats = subparsers.add_parser("stats", help="Print graph statistics")
    stats.add_argument("--graph", type=Path, default=Path("knowledge/graph.snapshot.json.gz"))

    gaps = subparsers.add_parser("gaps", help="List business rules missing evidence, code, or tests")
    gaps.add_argument("--graph", type=Path, default=Path("knowledge/graph.snapshot.json.gz"))

    context = subparsers.add_parser("context", help="Build an audience-filtered context package")
    context.add_argument("--graph", type=Path, default=Path("knowledge/graph.snapshot.json.gz"))
    context.add_argument("--node", required=True)
    context.add_argument("--depth", type=int, default=2)
    context.add_argument("--audience", choices=["shared", "implementer", "verifier"], default="implementer")

    impact = subparsers.add_parser("impact", help="Find the components potentially affected by a node")
    impact.add_argument("--graph", type=Path, default=Path("knowledge/graph.snapshot.json.gz"))
    impact.add_argument("--node", required=True)
    impact.add_argument("--depth", type=int, default=2)

    trace = subparsers.add_parser("trace", help="Find the shortest evidence path between two nodes")
    trace.add_argument("--graph", type=Path, default=Path("knowledge/graph.snapshot.json.gz"))
    trace.add_argument("--from", dest="source", required=True)
    trace.add_argument("--to", dest="target", required=True)

    compare = subparsers.add_parser(
        "compare-snapshots",
        help="Compare canonical graph content while ignoring compression metadata",
    )
    compare.add_argument("--expected", type=Path, required=True)
    compare.add_argument("--actual", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "build":
        graph = build_graph(
            args.legacy_root,
            args.modern_root,
            args.manifest,
            args.legacy_commit,
            args.modern_commit,
        )
        payload = graph.write(args.output)
        write_receipt(payload, args.receipt)
        print(json.dumps({"output": str(args.output), **payload["statistics"], "content_sha256": payload["content_sha256"]}, indent=2, sort_keys=True))
        return 0

    if args.command == "compare-snapshots":
        expected = load_graph(args.expected)
        actual = load_graph(args.actual)
        matches = expected.get("content_sha256") == actual.get("content_sha256")
        print(
            json.dumps(
                {
                    "status": "passed" if matches else "failed",
                    "expected_content_sha256": expected.get("content_sha256"),
                    "actual_content_sha256": actual.get("content_sha256"),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0 if matches else 1

    payload = load_graph(args.graph)
    if args.command == "validate":
        errors = validate_graph(payload)
        print(json.dumps({"status": "passed" if not errors else "failed", "errors": errors}, indent=2, sort_keys=True))
        return 0 if not errors else 1
    if args.command == "stats":
        print(json.dumps(payload["statistics"], indent=2, sort_keys=True))
        return 0
    if args.command == "gaps":
        gaps = rule_gaps(payload)
        print(json.dumps({"status": "passed" if not gaps else "failed", "gaps": gaps}, indent=2, sort_keys=True))
        return 0 if not gaps else 1
    if args.command == "context":
        print(json.dumps(neighborhood(payload, args.node, args.depth, args.audience), indent=2, sort_keys=True))
        return 0
    if args.command == "impact":
        print(json.dumps(neighborhood(payload, args.node, args.depth, "shared"), indent=2, sort_keys=True))
        return 0
    if args.command == "trace":
        result = shortest_trace(payload, args.source, args.target)
        print(json.dumps({"status": "found" if result else "not_found", "trace": result}, indent=2, sort_keys=True))
        return 0 if result else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
