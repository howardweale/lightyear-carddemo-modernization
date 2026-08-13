from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .agents import LocalAgentSet, OpenAIAgentSet
from .benchmark import run_mutation_benchmark
from .contracts import ContractError, WorkOrder
from .evals import (
    EvaluationPolicy,
    load_evaluation_catalog,
    run_model_evaluation,
    validate_evaluation_catalog,
)
from .orchestrator import FactoryOrchestrator
from .store import FactoryRunStore

from lightyear_execution.admission import AdmissionNonceStore, verify_work_order
from lightyear_execution.backend import OCIContainerBackend
from lightyear_execution.contracts import ExecutionContractError, ExecutionPolicy
from lightyear_execution.integration import HardenedExecutionContext


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LIGHTYEAR autonomous modernization factory")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="Execute one approved factory work order")
    run.add_argument("--work-order", type=Path)
    run.add_argument("--signed-work-order", type=Path)
    run.add_argument("--source-root", type=Path, default=Path("."))
    run.add_argument("--runs-root", type=Path, default=Path("work/factory-runs"))
    run.add_argument("--graph", type=Path, default=Path("knowledge/graph.snapshot.json.gz"))
    run.add_argument(
        "--evidence-pack", type=Path, default=Path("knowledge/evidence/source.pack.json.gz")
    )
    run.add_argument("--provider", choices=["local", "openai"], default="local")
    run.add_argument("--run-id")
    run.add_argument("--execution-policy", type=Path, default=Path("factory/execution/policy.json"))
    run.add_argument("--execution-runtime", choices=["docker", "podman"])

    benchmark = subparsers.add_parser(
        "benchmark", help="Run the offline INTCALC mutation gauntlet"
    )
    benchmark.add_argument("--project-root", type=Path, default=Path("."))
    benchmark.add_argument("--output-root", type=Path)
    benchmark.add_argument("--mutation", action="append", dest="mutations")

    evaluate = subparsers.add_parser(
        "evaluate", help="Run a model-backed public or sealed work-cell evaluation"
    )
    evaluate.add_argument("--project-root", type=Path, default=Path("."))
    evaluate.add_argument(
        "--catalog", type=Path, default=Path("factory/evals/carddemo-v0.12-public.json")
    )
    evaluate.add_argument("--output-root", type=Path)
    evaluate.add_argument("--provider", choices=["openai"], default="openai")
    evaluate.add_argument("--resume", action="store_true")
    evaluate.add_argument(
        "--max-evaluation-cost-usd",
        type=float,
        default=float(os.environ.get("LIGHTYEAR_EVALUATION_MAX_COST_USD", "15")),
    )
    evaluate.add_argument(
        "--max-evaluation-tokens",
        type=int,
        default=int(os.environ.get("LIGHTYEAR_EVALUATION_MAX_TOKENS", "8000000")),
    )
    evaluate.add_argument(
        "--max-evaluation-model-calls",
        type=int,
        default=int(os.environ.get("LIGHTYEAR_EVALUATION_MAX_MODEL_CALLS", "180")),
    )
    evaluate.add_argument(
        "--max-case-cost-usd",
        type=float,
        default=float(os.environ.get("LIGHTYEAR_EVALUATION_MAX_CASE_COST_USD", "2")),
    )
    evaluate.add_argument(
        "--max-case-tokens",
        type=int,
        default=int(os.environ.get("LIGHTYEAR_EVALUATION_MAX_CASE_TOKENS", "400000")),
    )
    evaluate.add_argument(
        "--pace-seconds",
        type=float,
        default=float(os.environ.get("LIGHTYEAR_EVALUATION_PACE_SECONDS", "1")),
    )

    validate_eval = subparsers.add_parser(
        "validate-eval", help="Validate an evaluation catalog without calling a model"
    )
    validate_eval.add_argument("--project-root", type=Path, default=Path("."))
    validate_eval.add_argument(
        "--catalog", type=Path, default=Path("factory/evals/carddemo-v0.12-public.json")
    )

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
    if args.command == "validate-eval":
        result = validate_evaluation_catalog(
            args.project_root.resolve(), load_evaluation_catalog(args.catalog)
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.command == "evaluate":
        output_root = args.output_root or Path("work") / (
            "model-evaluation-"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        )
        input_price = float(os.environ.get("LIGHTYEAR_MODEL_INPUT_USD_PER_MILLION", "0"))
        output_price = float(os.environ.get("LIGHTYEAR_MODEL_OUTPUT_USD_PER_MILLION", "0"))
        if input_price <= 0 or output_price <= 0:
            raise ContractError(
                "Live evaluation requires positive model input and output prices for cost enforcement"
            )
        policy = EvaluationPolicy(
            max_cost_usd=args.max_evaluation_cost_usd,
            max_tokens=args.max_evaluation_tokens,
            max_model_calls=args.max_evaluation_model_calls,
            max_case_cost_usd=args.max_case_cost_usd,
            max_case_tokens=args.max_case_tokens,
            pace_seconds=args.pace_seconds,
            require_cost_estimate=True,
        )
        result = run_model_evaluation(
            args.project_root,
            output_root,
            args.catalog,
            lambda _: OpenAIAgentSet.from_environment(),
            policy=policy,
            resume=args.resume,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["status"] == "passed" else 1
    if args.command == "inspect":
        result = FactoryRunStore(args.runs_root).run(args.run_id, args.verifier)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    execution_context = None
    if args.execution_runtime:
        if not args.signed_work_order or args.work_order:
            raise ExecutionContractError(
                "Hardened execution requires --signed-work-order and forbids unsigned --work-order"
            )
        policy = ExecutionPolicy.load(args.execution_policy)
        envelope = json.loads(args.signed_work_order.read_text(encoding="utf-8"))
        key_id = envelope.get("signature", {}).get("key_id", "")
        admission_key = os.environ.get("LIGHTYEAR_WORK_ORDER_SIGNING_KEY", "").encode()
        order, admission = verify_work_order(
            envelope,
            policy,
            {key_id: admission_key},
            datetime.now(timezone.utc).isoformat(),
            AdmissionNonceStore(args.runs_root / "admission-nonces.sha256"),
        )
        identity_key = os.environ.get("LIGHTYEAR_IDENTITY_SIGNING_KEY", "").encode()
        execution_context = HardenedExecutionContext(
            policy,
            OCIContainerBackend(policy, args.execution_runtime, execute=True),
            admission,
            identity_key,
            {"OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY", "")},
        )
        execution_context.bind(order.content_sha256, datetime.now(timezone.utc).isoformat())
    else:
        if not args.work_order or args.signed_work_order:
            raise ExecutionContractError(
                "Host compatibility mode requires exactly one unsigned --work-order"
            )
        order = WorkOrder.load(args.work_order)
    if args.provider == "local":
        agents = LocalAgentSet()
    elif execution_context:
        agents = OpenAIAgentSet(
            execution_context.lease_secret(
                "provider", "OPENAI_API_KEY", datetime.now(timezone.utc).isoformat()
            )
        )
    else:
        agents = OpenAIAgentSet.from_environment()
    receipt = FactoryOrchestrator(
        args.source_root,
        args.runs_root,
        agents,
        graph_path=args.graph,
        evidence_path=args.evidence_pack,
        execution_context=execution_context,
    ).run(order, args.run_id)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
