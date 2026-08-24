from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .builder import build_canonical_audit
from .contracts import EventDraft
from .dossier import build_dossier, write_dossier
from .ledger import (
    AppendOnlyAuditLog,
    load_snapshot,
    validate_snapshot,
    write_snapshot,
)
from .store import AuditStore


DEFAULT_SNAPSHOT = Path("audit/audit.snapshot.json.gz")
DEFAULT_GRAPH_RECEIPT = Path("knowledge/graph.receipt.json")
DEFAULT_EVIDENCE_RECEIPT = Path("knowledge/evidence/source.receipt.json")
DEFAULT_RUNTIME = Path("knowledge/runtime/runtime.snapshot.json.gz")
DEFAULT_ZOSMF_RUNTIME = Path("knowledge/runtime/zosmf/intcalc.runtime.snapshot.json.gz")
DEFAULT_WORK_ORDER = Path("factory/work-orders/intcalc-repair.example.json")
DEFAULT_POLICY = Path("audit/policies/promotion.json")
DEFAULT_EXECUTION_RECEIPT = Path("factory/execution/conformance.receipt.json")
DEFAULT_MEMORY_SNAPSHOT = Path("factory/memory/store/memory.snapshot.json.gz")
DEFAULT_PORTFOLIO_PLAN = Path("factory/portfolio/carddemo-plan.snapshot.json")
DEFAULT_DURABLE_POLICY = Path("factory/durable/policy.json")
DEFAULT_DURABLE_CONFORMANCE = Path("factory/durable/conformance.receipt.json")
DEFAULT_CONTROL_TOWER_POLICY = Path("control-tower/policy.json")
DEFAULT_CICS_VSAM_READINESS = Path("readiness/cics-vsam/readiness-receipt.json")
DEFAULT_DATA_EQUIVALENCE = Path("data-modernization/receipts/authfrds.offline.receipt.json")
DEFAULT_DOSSIER_JSON = Path("audit/dossiers/carddemo-intcalc-v0.19-demo.json")
DEFAULT_DOSSIER_MD = Path("audit/dossiers/carddemo-intcalc-v0.19-demo.md")
DEFAULT_RELEASE = "release:carddemo-intcalc:v0.19-demo"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LIGHTYEAR audit ledger and evidence control plane")
    commands = parser.add_subparsers(dest="command", required=True)

    build = commands.add_parser("build", help="Build canonical audit ledger and release dossier")
    build.add_argument("--graph-receipt", type=Path, default=DEFAULT_GRAPH_RECEIPT)
    build.add_argument("--evidence-receipt", type=Path, default=DEFAULT_EVIDENCE_RECEIPT)
    build.add_argument("--runtime", type=Path, action="append", dest="runtime_paths")
    build.add_argument("--work-order", type=Path, default=DEFAULT_WORK_ORDER)
    build.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    build.add_argument("--execution-receipt", type=Path, default=DEFAULT_EXECUTION_RECEIPT)
    build.add_argument("--memory-snapshot", type=Path, default=DEFAULT_MEMORY_SNAPSHOT)
    build.add_argument("--portfolio-plan", type=Path, default=DEFAULT_PORTFOLIO_PLAN)
    build.add_argument("--durable-policy", type=Path, default=DEFAULT_DURABLE_POLICY)
    build.add_argument("--durable-conformance", type=Path, default=DEFAULT_DURABLE_CONFORMANCE)
    build.add_argument("--control-tower-policy", type=Path, default=DEFAULT_CONTROL_TOWER_POLICY)
    build.add_argument("--cics-vsam-readiness", type=Path, default=DEFAULT_CICS_VSAM_READINESS)
    build.add_argument("--data-equivalence", type=Path, default=DEFAULT_DATA_EQUIVALENCE)
    build.add_argument("--output", type=Path, default=DEFAULT_SNAPSHOT)
    build.add_argument("--dossier-json", type=Path, default=DEFAULT_DOSSIER_JSON)
    build.add_argument("--dossier-markdown", type=Path, default=DEFAULT_DOSSIER_MD)
    build.add_argument("--release", default=DEFAULT_RELEASE)

    validate = commands.add_parser("validate", help="Validate chain, hashes, graph binding, and signature")
    validate.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    validate.add_argument("--graph-receipt", type=Path, default=DEFAULT_GRAPH_RECEIPT)

    compare = commands.add_parser("compare", help="Compare canonical audit snapshot identities")
    compare.add_argument("--expected", type=Path, required=True)
    compare.add_argument("--actual", type=Path, required=True)

    inspect = commands.add_parser("inspect", help="Inspect trust posture, events, or a policy decision")
    inspect.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    inspect.add_argument("--events", action="store_true")
    inspect.add_argument("--decision")
    inspect.add_argument("--audience", choices=["implementer", "verifier", "auditor"], default="implementer")
    inspect.add_argument("--limit", type=int, default=50)

    dossier = commands.add_parser("dossier", help="Generate a release evidence dossier")
    dossier.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    dossier.add_argument("--release", default=DEFAULT_RELEASE)
    dossier.add_argument("--json", type=Path, default=DEFAULT_DOSSIER_JSON)
    dossier.add_argument("--markdown", type=Path, default=DEFAULT_DOSSIER_MD)

    append = commands.add_parser("append", help="Append one validated event to a local JSONL audit log")
    append.add_argument("--log", type=Path, required=True)
    append.add_argument("--event", type=Path, required=True)
    append.add_argument("--expected-head")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    signing_key = _signing_key()
    if args.command == "build":
        runtime_paths = args.runtime_paths or [DEFAULT_RUNTIME, DEFAULT_ZOSMF_RUNTIME]
        payload = build_canonical_audit(
            args.graph_receipt,
            args.evidence_receipt,
            runtime_paths,
            args.work_order,
            args.policy,
            signing_key,
            args.execution_receipt,
            args.memory_snapshot,
            args.release,
            args.portfolio_plan,
            args.durable_policy,
            args.durable_conformance,
            args.control_tower_policy,
            args.cics_vsam_readiness,
            args.data_equivalence,
        )
        write_snapshot(payload, args.output)
        dossier = build_dossier(payload, args.release)
        write_dossier(dossier, args.dossier_json, args.dossier_markdown)
        print(json.dumps({
            "status": "passed",
            "output": str(args.output),
            "dossier": str(args.dossier_json),
            "content_sha256": payload["content_sha256"],
            "ledger_head_sha256": payload["checkpoint"]["ledger_head_sha256"],
            "checkpoint_signed": bool(payload["checkpoint"]["signature"]),
            **payload["statistics"],
            "promotion_status": dossier["status"],
        }, indent=2, sort_keys=True))
        return 0
    if args.command == "validate":
        graph = json.loads(args.graph_receipt.read_text(encoding="utf-8"))
        errors, warnings = validate_snapshot(
            load_snapshot(args.snapshot), graph["content_sha256"], signing_key
        )
        print(json.dumps({
            "status": "passed" if not errors else "failed",
            "errors": errors,
            "warnings": warnings,
        }, indent=2, sort_keys=True))
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
        store = AuditStore(load_snapshot(args.snapshot))
        if args.decision:
            result = store.decision(args.decision)
        elif args.events:
            result = store.events(args.audience, args.limit)
        else:
            result = store.summary()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.command == "dossier":
        dossier = build_dossier(load_snapshot(args.snapshot), args.release)
        write_dossier(dossier, args.json, args.markdown)
        print(json.dumps({
            "status": "passed",
            "release_status": dossier["status"],
            "content_sha256": dossier["content_sha256"],
            "json": str(args.json),
            "markdown": str(args.markdown),
        }, indent=2, sort_keys=True))
        return 0
    if args.command == "append":
        draft = EventDraft.from_dict(json.loads(args.event.read_text(encoding="utf-8")))
        event = AppendOnlyAuditLog(args.log).append(draft, args.expected_head)
        print(json.dumps({
            "status": "passed",
            "sequence": event["sequence"],
            "event_id": event["event_id"],
            "ledger_head_sha256": event["event_sha256"],
        }, indent=2, sort_keys=True))
        return 0
    return 2


def _signing_key() -> bytes | None:
    value = os.environ.get("LIGHTYEAR_AUDIT_SIGNING_KEY")
    return value.encode("utf-8") if value else None


if __name__ == "__main__":
    raise SystemExit(main())
