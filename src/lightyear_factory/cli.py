from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .agents import LocalAgentSet, OpenAIAgentSet
from .benchmark import run_mutation_benchmark
from .contracts import ContractError, WorkOrder, canonical_hash
from .context import GraphContextAssembler
from .evals import (
    EvaluationPolicy,
    load_evaluation_catalog,
    run_model_evaluation,
    validate_evaluation_catalog,
)
from .quality import (
    QualityPolicy,
    compare_evaluations,
    sign_sealed_catalog,
    verify_sealed_catalog,
    write_signed_catalog,
)
from .orchestrator import FactoryOrchestrator
from .memory import SemanticMemoryStore
from .portfolio import (
    PortfolioManifest,
    PortfolioRunner,
    plan_portfolio,
    sign_portfolio_approval,
    verify_portfolio_approval,
)
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
    run.add_argument("--memory-root", type=Path, default=Path("work/semantic-memory"))
    run.add_argument(
        "--memory-policy", type=Path, default=Path("factory/memory/policy.json")
    )
    run.add_argument("--disable-memory", action="store_true")

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
    evaluate.add_argument("--sealed-envelope", type=Path)
    evaluate.add_argument(
        "--quality-policy", type=Path, default=Path("factory/evals/quality-policy.json")
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

    sign_eval = subparsers.add_parser(
        "sign-eval-catalog", help="Sign an externally controlled sealed holdout catalog"
    )
    sign_eval.add_argument("--catalog", type=Path, required=True)
    sign_eval.add_argument("--output", type=Path, required=True)
    sign_eval.add_argument("--issuer", required=True)
    sign_eval.add_argument("--key-id", default="evaluation-controller")
    sign_eval.add_argument("--ttl-seconds", type=int, default=86_400)

    validate_sealed = subparsers.add_parser(
        "validate-sealed-eval", help="Verify a sealed catalog without printing its contents"
    )
    validate_sealed.add_argument("--envelope", type=Path, required=True)

    compare_eval = subparsers.add_parser(
        "compare-evals", help="Compare two or more evaluation receipts safety-first"
    )
    compare_eval.add_argument("--receipt", type=Path, action="append", required=True)

    inspect = subparsers.add_parser("inspect", help="Inspect a factory run receipt and ledger")
    inspect.add_argument("--runs-root", type=Path, default=Path("work/factory-runs"))
    inspect.add_argument("--run-id", required=True)
    inspect.add_argument("--verifier", action="store_true")
    transcript = subparsers.add_parser(
        "transcript", help="Render the controller-mediated exchange for a factory run"
    )
    transcript.add_argument("--runs-root", type=Path, default=Path("work/factory-runs"))
    transcript.add_argument("--run-id", required=True)
    transcript.add_argument("--verifier", action="store_true")

    memory_ingest = subparsers.add_parser(
        "memory-ingest", help="Promote one existing verified run into semantic memory"
    )
    memory_ingest.add_argument("--run-dir", type=Path, required=True)
    memory_ingest.add_argument("--memory-root", type=Path, default=Path("work/semantic-memory"))
    memory_ingest.add_argument(
        "--memory-policy", type=Path, default=Path("factory/memory/policy.json")
    )

    memory_query = subparsers.add_parser(
        "memory-query", help="Retrieve graph-addressed experiences for a work order"
    )
    memory_query.add_argument("--work-order", type=Path, required=True)
    memory_query.add_argument("--source-root", type=Path, default=Path("."))
    memory_query.add_argument("--graph", type=Path, default=Path("knowledge/graph.snapshot.json.gz"))
    memory_query.add_argument(
        "--evidence-pack", type=Path, default=Path("knowledge/evidence/source.pack.json.gz")
    )
    memory_query.add_argument("--memory-root", type=Path, default=Path("work/semantic-memory"))
    memory_query.add_argument(
        "--memory-policy", type=Path, default=Path("factory/memory/policy.json")
    )

    memory_summary = subparsers.add_parser(
        "memory-summary", help="Show the privacy-safe semantic-memory inventory"
    )
    memory_summary.add_argument("--memory-root", type=Path, default=Path("work/semantic-memory"))
    memory_summary.add_argument(
        "--memory-policy", type=Path, default=Path("factory/memory/policy.json")
    )

    memory_validate = subparsers.add_parser(
        "memory-validate", help="Validate memory hashes, privacy, and deterministic projection"
    )
    memory_validate.add_argument("--memory-root", type=Path, default=Path("work/semantic-memory"))
    memory_validate.add_argument(
        "--memory-policy", type=Path, default=Path("factory/memory/policy.json")
    )

    portfolio_plan = subparsers.add_parser(
        "portfolio-plan", help="Build a deterministic conflict-aware portfolio plan"
    )
    portfolio_plan.add_argument("--manifest", type=Path, required=True)
    portfolio_plan.add_argument("--project-root", type=Path, default=Path("."))
    portfolio_plan.add_argument(
        "--graph", type=Path, default=Path("knowledge/graph.snapshot.json.gz")
    )
    portfolio_plan.add_argument("--output", type=Path, required=True)

    portfolio_sign = subparsers.add_parser(
        "portfolio-sign", help="Bind a human approval to one exact portfolio plan"
    )
    portfolio_sign.add_argument("--plan", type=Path, required=True)
    portfolio_sign.add_argument("--output", type=Path, required=True)
    portfolio_sign.add_argument("--approver", required=True)
    portfolio_sign.add_argument("--key-id", default="portfolio-approver")
    portfolio_sign.add_argument("--ttl-seconds", type=int, default=900)

    portfolio_validate = subparsers.add_parser(
        "portfolio-validate", help="Validate a plan and optional signed human approval"
    )
    portfolio_validate.add_argument("--plan", type=Path, required=True)
    portfolio_validate.add_argument("--approval", type=Path)

    portfolio_run = subparsers.add_parser(
        "portfolio-run", help="Dispatch approved work cells using wave barriers"
    )
    portfolio_run.add_argument("--manifest", type=Path, required=True)
    portfolio_run.add_argument("--plan", type=Path, required=True)
    portfolio_run.add_argument("--approval", type=Path)
    portfolio_run.add_argument("--project-root", type=Path, default=Path("."))
    portfolio_run.add_argument(
        "--graph", type=Path, default=Path("knowledge/graph.snapshot.json.gz")
    )
    portfolio_run.add_argument(
        "--evidence-pack", type=Path, default=Path("knowledge/evidence/source.pack.json.gz")
    )
    portfolio_run.add_argument("--output-root", type=Path, required=True)
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
    if args.command == "sign-eval-catalog":
        key = os.environ.get("LIGHTYEAR_EVALUATION_SIGNING_KEY", "").encode()
        catalog = load_evaluation_catalog(args.catalog)
        envelope = sign_sealed_catalog(
            catalog,
            key,
            issuer=args.issuer,
            key_id=args.key_id,
            ttl_seconds=args.ttl_seconds,
        )
        write_signed_catalog(envelope, args.output)
        result = {
            "status": "passed",
            "output": str(args.output.resolve()),
            "catalog_sha256": envelope["catalog_sha256"],
            "envelope_sha256": envelope["content_sha256"],
            "expires_at": envelope["expires_at"],
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.command == "validate-sealed-eval":
        envelope = json.loads(args.envelope.read_text(encoding="utf-8"))
        key_id = str(envelope.get("key_id", ""))
        key = os.environ.get("LIGHTYEAR_EVALUATION_SIGNING_KEY", "").encode()
        _, binding = verify_sealed_catalog(envelope, {key_id: key})
        print(json.dumps({"status": "passed", **binding}, indent=2, sort_keys=True))
        return 0
    if args.command == "compare-evals":
        result = compare_evaluations([
            json.loads(path.read_text(encoding="utf-8")) for path in args.receipt
        ])
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.command == "portfolio-plan":
        manifest = PortfolioManifest.load(args.manifest)
        graph_path = args.graph if args.graph.is_absolute() else args.project_root / args.graph
        result, _ = plan_portfolio(manifest, args.project_root, graph_path)
        from .contracts import write_json

        write_json(result, args.output)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.command == "portfolio-sign":
        plan = json.loads(args.plan.read_text(encoding="utf-8"))
        key = os.environ.get("LIGHTYEAR_PORTFOLIO_APPROVAL_KEY", "").encode()
        result = sign_portfolio_approval(
            plan,
            key,
            approver_id=args.approver,
            key_id=args.key_id,
            ttl_seconds=args.ttl_seconds,
        )
        from .contracts import write_json

        write_json(result, args.output)
        print(json.dumps({
            "status": "passed",
            "output": str(args.output.resolve()),
            "plan_sha256": result["plan_sha256"],
            "expires_at": result["expires_at"],
        }, indent=2, sort_keys=True))
        return 0
    if args.command == "portfolio-validate":
        plan = json.loads(args.plan.read_text(encoding="utf-8"))
        if plan.get("content_sha256") != canonical_hash(plan, {"content_sha256"}):
            raise ContractError("Portfolio plan content hash is invalid")
        result: dict[str, object] = {
            "status": "passed",
            "plan_sha256": plan["content_sha256"],
            "approval_required": bool(plan.get("approval", {}).get("required")),
        }
        if args.approval:
            envelope = json.loads(args.approval.read_text(encoding="utf-8"))
            key_id = str(envelope.get("key_id", ""))
            key = os.environ.get("LIGHTYEAR_PORTFOLIO_APPROVAL_KEY", "").encode()
            result["admission"] = verify_portfolio_approval(plan, envelope, {key_id: key})
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.command == "portfolio-run":
        manifest = PortfolioManifest.load(args.manifest)
        graph_path = args.graph if args.graph.is_absolute() else args.project_root / args.graph
        expected_plan, orders = plan_portfolio(manifest, args.project_root, graph_path)
        supplied_plan = json.loads(args.plan.read_text(encoding="utf-8"))
        if supplied_plan.get("content_sha256") != expected_plan["content_sha256"]:
            raise ContractError("Supplied portfolio plan is stale or targets different inputs")
        admission = None
        if args.approval:
            envelope = json.loads(args.approval.read_text(encoding="utf-8"))
            key_id = str(envelope.get("key_id", ""))
            key = os.environ.get("LIGHTYEAR_PORTFOLIO_APPROVAL_KEY", "").encode()
            admission = verify_portfolio_approval(
                expected_plan, envelope, {key_id: key}
            )
        cells_root = args.output_root / "cells"
        evidence = (
            args.evidence_pack
            if args.evidence_pack.is_absolute()
            else args.project_root / args.evidence_pack
        )

        def execute_cell(order: WorkOrder, run_id: str) -> dict[str, object]:
            return FactoryOrchestrator(
                args.project_root,
                cells_root,
                LocalAgentSet(),
                graph_path=graph_path,
                evidence_path=evidence,
                memory_store=None,
            ).run(order, run_id)

        result = PortfolioRunner(execute_cell).run(
            expected_plan, orders, args.output_root, admission
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["status"] == "passed" else 1
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
        catalog_override = None
        sealed_binding = None
        if args.sealed_envelope:
            envelope = json.loads(args.sealed_envelope.read_text(encoding="utf-8"))
            key_id = str(envelope.get("key_id", ""))
            key = os.environ.get("LIGHTYEAR_EVALUATION_SIGNING_KEY", "").encode()
            catalog_override, sealed_binding = verify_sealed_catalog(
                envelope, {key_id: key}
            )
        result = run_model_evaluation(
            args.project_root,
            output_root,
            args.catalog,
            lambda _: OpenAIAgentSet.from_environment(),
            policy=policy,
            catalog_override=catalog_override,
            sealed_binding=sealed_binding,
            quality_policy=QualityPolicy.load(args.quality_policy),
            resume=args.resume,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["status"] == "passed" else 1
    if args.command == "inspect":
        result = FactoryRunStore(args.runs_root).run(args.run_id, args.verifier)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.command == "transcript":
        result = FactoryRunStore(args.runs_root).transcript(args.run_id, args.verifier)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.command.startswith("memory-"):
        memory = SemanticMemoryStore.from_policy_path(
            args.memory_root, args.memory_policy
        )
        if args.command == "memory-ingest":
            result = memory.ingest_run_dir(args.run_dir)
        elif args.command == "memory-query":
            order = WorkOrder.load(args.work_order)
            context = GraphContextAssembler(
                args.graph.resolve(), args.evidence_pack.resolve(), max_nodes=160
            ).assemble(order, args.source_root.resolve())
            result = memory.retrieve(
                order,
                context.get("graph_content_sha256"),
                context.get("evidence_pack_sha256"),
            )
        elif args.command == "memory-summary":
            result = memory.summary()
        else:
            result = memory.validate()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("status", "passed") == "passed" else 1
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
    memory_policy_path = args.memory_policy
    if not memory_policy_path.is_absolute():
        memory_policy_path = args.source_root / memory_policy_path
    memory_store = (
        None
        if args.disable_memory
        else SemanticMemoryStore.from_policy_path(args.memory_root, memory_policy_path)
    )
    receipt = FactoryOrchestrator(
        args.source_root,
        args.runs_root,
        agents,
        graph_path=args.graph,
        evidence_path=args.evidence_pack,
        execution_context=execution_context,
        memory_store=memory_store,
    ).run(order, args.run_id)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
