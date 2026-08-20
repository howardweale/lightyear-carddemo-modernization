from __future__ import annotations

import argparse
import json
from pathlib import Path

from .builder import build_graph, write_receipt
from .capability import analyze_capabilities, validate_capability_analysis, write_capability_analysis
from .evidence_pack import (
    build_evidence_pack,
    load_evidence_pack,
    validate_evidence_pack,
    write_evidence_pack,
    write_evidence_receipt,
)
from .explorer import serve
from .model import load_graph
from .neo4j_export import export_neo4j
from .ontology import DEFAULT_ONTOLOGY_PATH
from .query import neighborhood, shortest_trace
from .validation import rule_gaps, validate_graph


DEFAULT_LEGACY_COMMIT = "59cc6c2fd7ebd7ef7925cad552a01a4b8b6e4d5e"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LIGHTYEAR evidence-aware modernization knowledge graph")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="Build a deterministic graph snapshot")
    build.add_argument("--legacy-root", type=Path, required=True)
    build.add_argument("--modern-root", type=Path, default=Path("."))
    build.add_argument(
        "--manifest",
        type=Path,
        action="append",
        help="Curated workload manifest; repeat to compose multiple vertical slices",
    )
    build.add_argument("--output", type=Path, default=Path("knowledge/graph.snapshot.json.gz"))
    build.add_argument("--receipt", type=Path, default=Path("knowledge/graph.receipt.json"))
    build.add_argument("--legacy-commit", default=DEFAULT_LEGACY_COMMIT)
    build.add_argument("--modern-commit", default="working-tree")
    build.add_argument("--ontology", type=Path, default=DEFAULT_ONTOLOGY_PATH)
    build.add_argument(
        "--evidence-pack", type=Path, default=Path("knowledge/evidence/source.pack.json.gz")
    )
    build.add_argument(
        "--evidence-receipt", type=Path, default=Path("knowledge/evidence/source.receipt.json")
    )

    validate = subparsers.add_parser("validate", help="Validate graph integrity and rule coverage")
    validate.add_argument("--graph", type=Path, default=Path("knowledge/graph.snapshot.json.gz"))

    validate_evidence = subparsers.add_parser(
        "validate-evidence", help="Validate source evidence capsules against the canonical graph"
    )
    validate_evidence.add_argument(
        "--graph", type=Path, default=Path("knowledge/graph.snapshot.json.gz")
    )
    validate_evidence.add_argument(
        "--evidence-pack", type=Path, default=Path("knowledge/evidence/source.pack.json.gz")
    )

    stats = subparsers.add_parser("stats", help="Print graph statistics")
    stats.add_argument("--graph", type=Path, default=Path("knowledge/graph.snapshot.json.gz"))

    gaps = subparsers.add_parser("gaps", help="List business rules missing evidence, code, or tests")
    gaps.add_argument("--graph", type=Path, default=Path("knowledge/graph.snapshot.json.gz"))

    capabilities = subparsers.add_parser(
        "capabilities", help="Evaluate CICS, VSAM, IMS, and HLASM against readiness gates 1-8"
    )
    capabilities.add_argument("--graph", type=Path, default=Path("knowledge/graph.snapshot.json.gz"))
    capabilities.add_argument(
        "--cics-vsam-receipt",
        type=Path,
        default=Path("readiness/cics-vsam/readiness-receipt.json"),
    )
    capabilities.add_argument(
        "--output", type=Path, default=Path("knowledge/capabilities/mainframe-readiness.json")
    )
    capabilities.add_argument(
        "--asm-receipt", type=Path, default=Path("readiness/asm-date/readiness-receipt.json")
    )
    capabilities.add_argument(
        "--ims-receipt", type=Path, default=Path("readiness/ims-expiry/readiness-receipt.json")
    )
    capabilities.add_argument("--validate-only", action="store_true")

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

    compare_evidence = subparsers.add_parser(
        "compare-evidence-packs", help="Compare canonical source evidence pack identities"
    )
    compare_evidence.add_argument("--expected", type=Path, required=True)
    compare_evidence.add_argument("--actual", type=Path, required=True)

    explorer = subparsers.add_parser("serve", help="Run the local LIGHTYEAR Graph Explorer")
    explorer.add_argument("--graph", type=Path, default=Path("knowledge/graph.snapshot.json.gz"))
    explorer.add_argument("--viewer-root", type=Path, default=Path("knowledge/viewer"))
    explorer.add_argument("--ontology", type=Path, default=DEFAULT_ONTOLOGY_PATH)
    explorer.add_argument(
        "--evidence-pack", type=Path, default=Path("knowledge/evidence/source.pack.json.gz")
    )
    explorer.add_argument("--host", default="127.0.0.1")
    explorer.add_argument("--port", type=int, default=8765)
    explorer.add_argument("--no-browser", action="store_true")
    explorer.add_argument("--factory-runs", type=Path, default=Path("work"))
    explorer.add_argument(
        "--runtime-snapshot",
        type=Path,
        default=Path("knowledge/runtime/runtime.snapshot.json.gz"),
    )
    explorer.add_argument(
        "--audit-snapshot",
        type=Path,
        default=Path("audit/audit.snapshot.json.gz"),
    )

    neo4j = subparsers.add_parser(
        "export-neo4j",
        help="Export a deterministic Neo4j CSV projection",
    )
    neo4j.add_argument("--graph", type=Path, default=Path("knowledge/graph.snapshot.json.gz"))
    neo4j.add_argument("--output-dir", type=Path, default=Path("work/neo4j-export"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "build":
        graph = build_graph(
            args.legacy_root,
            args.modern_root,
            args.manifest or [Path("knowledge/mappings/carddemo-intcalc.json")],
            args.legacy_commit,
            args.modern_commit,
            args.ontology,
        )
        payload = graph.write(args.output)
        write_receipt(payload, args.receipt)
        evidence_payload = build_evidence_pack(
            payload,
            {
                "source:aws-carddemo": args.legacy_root,
                "source:lightyear-carddemo": args.modern_root,
            },
        )
        write_evidence_pack(evidence_payload, args.evidence_pack)
        write_evidence_receipt(evidence_payload, args.evidence_receipt)
        print(
            json.dumps(
                {
                    "content_sha256": payload["content_sha256"],
                    "evidence_pack": str(args.evidence_pack),
                    "evidence_pack_content_sha256": evidence_payload["content_sha256"],
                    "evidence_statistics": evidence_payload["statistics"],
                    "output": str(args.output),
                    **payload["statistics"],
                },
                indent=2,
                sort_keys=True,
            )
        )
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

    if args.command == "compare-evidence-packs":
        expected = load_evidence_pack(args.expected)
        actual = load_evidence_pack(args.actual)
        matches = expected.get("content_sha256") == actual.get("content_sha256")
        print(
            json.dumps(
                {
                    "actual_content_sha256": actual.get("content_sha256"),
                    "expected_content_sha256": expected.get("content_sha256"),
                    "status": "passed" if matches else "failed",
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0 if matches else 1

    if args.command == "serve":
        serve(
            args.graph,
            args.viewer_root,
            args.host,
            args.port,
            not args.no_browser,
            args.ontology,
            args.evidence_pack,
            args.factory_runs,
            args.runtime_snapshot,
            args.audit_snapshot,
        )
        return 0

    payload = load_graph(args.graph)
    if args.command == "export-neo4j":
        receipt = export_neo4j(payload, args.output_dir)
        print(json.dumps({"output": str(args.output_dir), **receipt}, indent=2, sort_keys=True))
        return 0
    if args.command == "validate":
        errors = validate_graph(payload)
        print(json.dumps({"status": "passed" if not errors else "failed", "errors": errors}, indent=2, sort_keys=True))
        return 0 if not errors else 1
    if args.command == "validate-evidence":
        evidence_payload = load_evidence_pack(args.evidence_pack)
        errors = validate_evidence_pack(payload, evidence_payload)
        print(
            json.dumps(
                {"errors": errors, "status": "passed" if not errors else "failed"},
                indent=2,
                sort_keys=True,
            )
        )
        return 0 if not errors else 1
    if args.command == "stats":
        print(json.dumps(payload["statistics"], indent=2, sort_keys=True))
        return 0
    if args.command == "gaps":
        gaps = rule_gaps(payload)
        print(json.dumps({"status": "passed" if not gaps else "failed", "gaps": gaps}, indent=2, sort_keys=True))
        return 0 if not gaps else 1
    if args.command == "capabilities":
        if args.validate_only:
            analysis = json.loads(args.output.read_text(encoding="utf-8"))
        else:
            receipt = (
                json.loads(args.cics_vsam_receipt.read_text(encoding="utf-8"))
                if args.cics_vsam_receipt.exists()
                else None
            )
            asm_receipt = (
                json.loads(args.asm_receipt.read_text(encoding="utf-8"))
                if args.asm_receipt.exists()
                else None
            )
            ims_receipt = (
                json.loads(args.ims_receipt.read_text(encoding="utf-8"))
                if args.ims_receipt.exists()
                else None
            )
            analysis = analyze_capabilities(payload, receipt, asm_receipt, ims_receipt)
            write_capability_analysis(analysis, args.output)
        errors = validate_capability_analysis(analysis, payload)
        print(
            json.dumps(
                {
                    "capabilities": analysis.get("capabilities", []),
                    "content_sha256": analysis.get("content_sha256"),
                    "errors": errors,
                    "output": str(args.output),
                    "status": "passed" if not errors else "failed",
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0 if not errors else 1
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
