from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path

from .compare import (
    compare_directories,
    validate_normalization_ledger,
    write_comparison,
)
from .demo import create_demo_inputs
from .oracle import run_directory


DEFAULT_PROCESSING_DATE = "2022071800"
DEFAULT_TIMESTAMP = "2022-07-18-00.00.00.000000"


def _add_run_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--processing-date", default=DEFAULT_PROCESSING_DATE)
    parser.add_argument("--timestamp", default=DEFAULT_TIMESTAMP)
    parser.add_argument(
        "--final-account-policy",
        choices=["source-faithful", "intended"],
        default="source-faithful",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local CardDemo INTCALC oracle")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run the source-faithful oracle")
    _add_run_arguments(run_parser)

    demo_parser = subparsers.add_parser("demo", help="Create and execute a deterministic demo")
    demo_parser.add_argument("--work-dir", type=Path, default=Path("work/demo"))
    demo_parser.add_argument(
        "--final-account-policy",
        choices=["source-faithful", "intended"],
        default="source-faithful",
    )

    compare_parser = subparsers.add_parser("compare", help="Compare candidate output to oracle output")
    compare_parser.add_argument("--expected", type=Path, required=True)
    compare_parser.add_argument("--actual", type=Path, required=True)
    compare_parser.add_argument("--report", type=Path, required=True)

    normalization_parser = subparsers.add_parser(
        "validate-normalizations",
        help="Validate governed comparator normalizations and review dates",
    )
    normalization_parser.add_argument(
        "--ledger",
        type=Path,
        default=Path("spec/comparison-normalizations.json"),
    )
    normalization_parser.add_argument(
        "--as-of",
        type=date.fromisoformat,
        help="ISO date used for deterministic review-expiry checks",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "run":
        receipt = run_directory(
            args.input,
            args.output,
            args.processing_date,
            args.timestamp,
            args.final_account_policy,
        )
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 0
    if args.command == "demo":
        input_dir = args.work_dir / "input"
        output_dir = args.work_dir / "oracle-output"
        create_demo_inputs(input_dir)
        receipt = run_directory(
            input_dir,
            output_dir,
            DEFAULT_PROCESSING_DATE,
            DEFAULT_TIMESTAMP,
            args.final_account_policy,
        )
        print(f"Demo input:  {input_dir.resolve()}")
        print(f"Demo output: {output_dir.resolve()}")
        print(json.dumps(receipt["observations"], indent=2, sort_keys=True))
        return 0
    if args.command == "compare":
        report = compare_directories(args.expected, args.actual)
        write_comparison(report, args.report)
        print(json.dumps(report, indent=2, sort_keys=True))
        if report["status"] == "passed":
            return 0
        if report["status"] == "failed":
            return 1
        return 2
    if args.command == "validate-normalizations":
        report = validate_normalization_ledger(args.ledger, as_of=args.as_of)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["status"] == "passed" else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
