from __future__ import annotations

import argparse
import json
from pathlib import Path

from lightyear_knowledge_graph.model import load_graph

from .adapters import FixtureAdapter, LocalOracleAdapter
from .engine import RuntimeEvidenceEngine, load_snapshot, validate_snapshot, write_snapshot


DEFAULT_GRAPH = Path("knowledge/graph.snapshot.json.gz")
DEFAULT_FIXTURE = Path("knowledge/runtime/fixtures/intcalc-zos-replay.json")
DEFAULT_SNAPSHOT = Path("knowledge/runtime/runtime.snapshot.json.gz")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LIGHTYEAR runtime evidence plane")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="Capture local evidence and replay recorded fixtures")
    build.add_argument("--graph", type=Path, default=DEFAULT_GRAPH)
    build.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    build.add_argument("--work-dir", type=Path, default=Path("work/runtime-capture"))
    build.add_argument("--output", type=Path, default=DEFAULT_SNAPSHOT)

    replay = subparsers.add_parser("replay", help="Build a snapshot from one adapter fixture")
    replay.add_argument("--graph", type=Path, default=DEFAULT_GRAPH)
    replay.add_argument("--fixture", type=Path, required=True)
    replay.add_argument("--output", type=Path, required=True)

    validate = subparsers.add_parser("validate", help="Validate hashes, ledger chains, and graph identity")
    validate.add_argument("--graph", type=Path, default=DEFAULT_GRAPH)
    validate.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)

    compare = subparsers.add_parser("compare", help="Compare canonical runtime snapshot identities")
    compare.add_argument("--expected", type=Path, required=True)
    compare.add_argument("--actual", type=Path, required=True)

    inspect = subparsers.add_parser("inspect", help="Inspect runtime status or one graph entity")
    inspect.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    inspect.add_argument("--node")
    inspect.add_argument("--edge")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command in {"build", "replay"}:
        graph = load_graph(args.graph)
        adapters = [FixtureAdapter(args.fixture)]
        if args.command == "build":
            adapters.insert(0, LocalOracleAdapter(args.work_dir))
        payload = RuntimeEvidenceEngine(graph).build(adapter.capture() for adapter in adapters)
        write_snapshot(payload, args.output)
        print(json.dumps({"output": str(args.output), **payload["statistics"], "content_sha256": payload["content_sha256"]}, indent=2, sort_keys=True))
        return 0
    if args.command == "validate":
        errors = validate_snapshot(load_snapshot(args.snapshot), load_graph(args.graph))
        print(json.dumps({"errors": errors, "status": "passed" if not errors else "failed"}, indent=2, sort_keys=True))
        return 0 if not errors else 1
    if args.command == "compare":
        expected = load_snapshot(args.expected)
        actual = load_snapshot(args.actual)
        matches = expected.get("content_sha256") == actual.get("content_sha256")
        print(json.dumps({
            "status": "passed" if matches else "failed",
            "expected_content_sha256": expected.get("content_sha256"),
            "actual_content_sha256": actual.get("content_sha256"),
        }, indent=2, sort_keys=True))
        return 0 if matches else 1
    if args.command == "inspect":
        payload = load_snapshot(args.snapshot)
        if args.node and args.edge:
            raise SystemExit("Choose either --node or --edge")
        if args.node:
            result = payload["projections"]["nodes"].get(args.node, {"state": "static_only"})
        elif args.edge:
            result = payload["projections"]["edges"].get(args.edge, {"state": "static_only"})
        else:
            result = {"statistics": payload["statistics"], "runs": [
                {key: run[key] for key in ("run_id", "adapter_id", "source_system", "policies", "content_sha256")}
                for run in payload["runs"]
            ]}
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
