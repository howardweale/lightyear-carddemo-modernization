from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .agents import LocalAgentSet, OpenAIAgentSet
from .benchmark import run_mutation_benchmark
from .contracts import WorkOrder
from .orchestrator import FactoryOrchestrator
from .store import FactoryRunStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LIGHTYEAR autonomous modernization factory")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="Execute one approved factory work order")
    run.add_argument("--work-order", type=Path, required=True)
    run.add_argument("--source-root", type=Path, default=Path("."))
    run.add_argument("--runs-root", type=Path, default=Path("work/factory-runs"))
    run.add_argument("--graph", type=Path, default=Path("knowledge/graph.snapshot.json.gz"))
    run.add_argument("--provider", choices=["local", "openai"], default="local")
    run.add_argument("--run-id")

    benchmark = subparsers.add_parser(
        "benchmark", help="Run the offline INTCALC mutation gauntlet"
    )
    benchmark.add_argument("--project-root", type=Path, default=Path("."))
    benchmark.add_argument("--output-root", type=Path)
    benchmark.add_argument("--mutation", action="append", dest="mutations")

    inspect = subparsers.add_parser("inspect", help="Inspect a factory run receipt and ledger")
    inspect.add_argument("--runs-root", type=Path, default=Path("work/factory-runs"))
    inspect.add_argument("--run-id", required=True)
    inspect.add_argument("--verifier", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "benchmark":
        output_root = args.output_root or Path("work") / (
            "factory-benchmark-"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        )
        result = run_mutation_benchmark(
            args.project_root, output_root, args.mutations
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["status"] == "passed" else 1
    if args.command == "inspect":
        result = FactoryRunStore(args.runs_root).run(args.run_id, args.verifier)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    order = WorkOrder.load(args.work_order)
    agents = LocalAgentSet() if args.provider == "local" else OpenAIAgentSet.from_environment()
    receipt = FactoryOrchestrator(
        args.source_root,
        args.runs_root,
        agents,
        graph_path=args.graph,
    ).run(order, args.run_id)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
