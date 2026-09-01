from __future__ import annotations

import argparse
import json
from pathlib import Path

from .builder import build_graph, write_receipt
from .capability import analyze_capabilities, validate_capability_analysis, write_capability_analysis
from .cloudbank_reference import (
    build_cloudbank_reference_fragment,
    validate_cloudbank_reference_fragment,
    write_cloudbank_reference_fragment,
    write_cloudbank_reference_receipt,
)
from .composite import (
    build_composite_estate,
    load_json as load_composite_input,
    validate_composite_estate,
    write_composite_estate,
    write_composite_receipt,
)
from .developer import demo as developer_demo, doctor as developer_doctor
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
from .oracle_reference import (
    build_oracle_reference_fragment,
    validate_oracle_reference_fragment,
    write_oracle_reference_fragment,
    write_oracle_reference_receipt,
)
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

    composite = subparsers.add_parser(
        "build-composite", help="Build a read-only base-plus-extension estate projection"
    )
    composite.add_argument(
        "--base-graph", type=Path, default=Path("knowledge/graph.snapshot.json.gz")
    )

    oracle_reference = subparsers.add_parser(
        "build-oracle-reference",
        help="Build the pinned Oracle Customer (Large) static reference projection",
    )
    oracle_reference.add_argument(
        "--base-graph", type=Path, default=Path("knowledge/graph.snapshot.json.gz")
    )
    oracle_reference.add_argument(
        "--slices", type=Path, default=Path("reference-estates/idempiere/business-slices.json")
    )
    oracle_reference.add_argument(
        "--inventory", type=Path, default=Path("reference-estates/idempiere/inventory.json")
    )
    oracle_reference.add_argument(
        "--source-pin", type=Path, default=Path("reference-estates/idempiere/source-pin.json")
    )
    oracle_reference.add_argument(
        "--output", type=Path,
        default=Path("reference-estates/idempiere/oracle-customer-large.fragment.json"),
    )
    oracle_reference.add_argument(
        "--receipt", type=Path,
        default=Path("reference-estates/idempiere/oracle-customer-large.receipt.json"),
    )

    validate_oracle_reference = subparsers.add_parser(
        "validate-oracle-reference",
        help="Validate the Oracle Customer (Large) static reference projection",
    )
    validate_oracle_reference.add_argument(
        "--base-graph", type=Path, default=Path("knowledge/graph.snapshot.json.gz")
    )
    validate_oracle_reference.add_argument(
        "--slices", type=Path, default=Path("reference-estates/idempiere/business-slices.json")
    )
    validate_oracle_reference.add_argument(
        "--inventory", type=Path, default=Path("reference-estates/idempiere/inventory.json")
    )
    validate_oracle_reference.add_argument(
        "--source-pin", type=Path, default=Path("reference-estates/idempiere/source-pin.json")
    )
    validate_oracle_reference.add_argument(
        "--fragment", type=Path,
        default=Path("reference-estates/idempiere/oracle-customer-large.fragment.json"),
    )

    cloudbank_reference = subparsers.add_parser(
        "build-cloudbank-reference",
        help="Build the pinned CloudBank modern-Oracle static reference projection",
    )
    cloudbank_reference.add_argument(
        "--base-graph", type=Path, default=Path("knowledge/graph.snapshot.json.gz")
    )
    cloudbank_reference.add_argument(
        "--workloads", type=Path,
        default=Path("reference-estates/cloudbank/workloads.json"),
    )
    cloudbank_reference.add_argument(
        "--inventory", type=Path,
        default=Path("reference-estates/cloudbank/inventory.json"),
    )
    cloudbank_reference.add_argument(
        "--source-pin", type=Path,
        default=Path("reference-estates/cloudbank/source-pin.json"),
    )
    cloudbank_reference.add_argument(
        "--output", type=Path,
        default=Path("reference-estates/cloudbank/cloudbank-reference.fragment.json"),
    )
    cloudbank_reference.add_argument(
        "--receipt", type=Path,
        default=Path("reference-estates/cloudbank/cloudbank-reference.receipt.json"),
    )

    validate_cloudbank_reference = subparsers.add_parser(
        "validate-cloudbank-reference",
        help="Validate the CloudBank modern-Oracle static reference projection",
    )
    validate_cloudbank_reference.add_argument(
        "--base-graph", type=Path, default=Path("knowledge/graph.snapshot.json.gz")
    )
    validate_cloudbank_reference.add_argument(
        "--workloads", type=Path,
        default=Path("reference-estates/cloudbank/workloads.json"),
    )
    validate_cloudbank_reference.add_argument(
        "--inventory", type=Path,
        default=Path("reference-estates/cloudbank/inventory.json"),
    )
    validate_cloudbank_reference.add_argument(
        "--source-pin", type=Path,
        default=Path("reference-estates/cloudbank/source-pin.json"),
    )
    validate_cloudbank_reference.add_argument(
        "--fragment", type=Path,
        default=Path("reference-estates/cloudbank/cloudbank-reference.fragment.json"),
    )
    composite.add_argument(
        "--fragment", type=Path, action="append", required=True,
        help="Validated extension fragment; repeat to compose multiple fragments",
    )
    composite.add_argument(
        "--capabilities",
        type=Path,
        default=Path("knowledge/capabilities/mainframe-readiness.json"),
    )
    composite.add_argument(
        "--output", type=Path, default=Path("knowledge/composite/estate.snapshot.json.gz")
    )
    composite.add_argument(
        "--receipt", type=Path, default=Path("knowledge/composite/estate.receipt.json")
    )
    composite.add_argument(
        "--legacy-root", type=Path, help="Legacy source root for the composite evidence pack"
    )
    composite.add_argument("--modern-root", type=Path, default=Path("."))
    composite.add_argument(
        "--evidence-pack",
        type=Path,
        default=Path("knowledge/composite/source.pack.json.gz"),
    )
    composite.add_argument(
        "--evidence-receipt",
        type=Path,
        default=Path("knowledge/composite/source.receipt.json"),
    )

    validate_composite = subparsers.add_parser(
        "validate-composite", help="Validate a composite estate against its bound evidence"
    )
    validate_composite.add_argument(
        "--graph", type=Path, default=Path("knowledge/composite/estate.snapshot.json.gz")
    )

    doctor = subparsers.add_parser(
        "doctor", help="Diagnose required and optional developer prerequisites"
    )
    doctor.add_argument("--project-root", type=Path, default=Path("."))

    demo = subparsers.add_parser(
        "demo", help="Verify and summarize the bounded mixed-language composite lineage"
    )
    demo.add_argument("--project-root", type=Path, default=Path("."))
    validate_composite.add_argument(
        "--base-graph", type=Path, default=Path("knowledge/graph.snapshot.json.gz")
    )
    validate_composite.add_argument("--fragment", type=Path, action="append", required=True)
    validate_composite.add_argument(
        "--capabilities",
        type=Path,
        default=Path("knowledge/capabilities/mainframe-readiness.json"),
    )
    validate_composite.add_argument(
        "--evidence-pack", type=Path, default=Path("knowledge/composite/source.pack.json.gz")
    )
    build.add_argument(
        "--semantic-inputs",
        type=Path,
        help="Versioned manifest declaring files allowed to influence semantic graph identity",
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
        "capabilities", help="Project runtime, language, and data readiness against gates 1-8"
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
    capabilities.add_argument(
        "--pli-fragment", type=Path, default=Path("extensions/pli/pli.fragment.json")
    )
    capabilities.add_argument(
        "--extension-catalog", type=Path, default=Path("extensions/catalog.json")
    )
    capabilities.add_argument(
        "--pli-coverage-receipt",
        type=Path,
        default=Path("extensions/pli/conformance/coverage.receipt.json"),
    )
    capabilities.add_argument(
        "--pli-development-receipt",
        type=Path,
        default=Path("extensions/pli/modernization/development.receipt.json"),
    )
    capabilities.add_argument(
        "--pli-build-receipt",
        type=Path,
        default=Path("extensions/pli/attestation/build.receipt.json"),
    )
    capabilities.add_argument(
        "--pli-build-attestation",
        type=Path,
        default=Path("extensions/pli/attestation/build.attestation.json"),
    )
    capabilities.add_argument(
        "--postgres-data-receipt",
        type=Path,
        default=Path("data-modernization/receipts/authfrds.offline.receipt.json"),
    )
    capabilities.add_argument(
        "--oracle-data-receipt",
        type=Path,
        default=Path("data-modernization/receipts/authfrds.oracle-offline.receipt.json"),
    )
    capabilities.add_argument(
        "--data-rehearsal-receipt",
        type=Path,
        default=Path("data-modernization/rehearsal/receipt.json"),
    )
    capabilities.add_argument(
        "--campaign-receipt",
        type=Path,
        default=Path("extensions/adapters/campaign/campaign.receipt.json"),
    )
    capabilities.add_argument(
        "--enterprise-appliance-receipt",
        type=Path,
        default=Path("extensions/adapters/appliance/appliance.receipt.json"),
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
    explorer.add_argument(
        "--graph", type=Path, default=Path("knowledge/composite/estate.snapshot.json.gz")
    )
    explorer.add_argument("--viewer-root", type=Path, default=Path("knowledge/viewer"))
    explorer.add_argument("--ontology", type=Path, default=DEFAULT_ONTOLOGY_PATH)
    explorer.add_argument(
        "--evidence-pack", type=Path, default=Path("knowledge/composite/source.pack.json.gz")
    )
    explorer.add_argument("--host", default="127.0.0.1")
    explorer.add_argument(
        "--i-understand-this-is-unauthenticated",
        action="store_true",
        help="Explicitly allow a non-loopback bind; customer deployments still require SSO/OIDC",
    )
    explorer.add_argument(
        "--verifier-token",
        help="Use an operator-supplied verifier bearer token instead of generating one",
    )
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
            args.semantic_inputs,
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

    if args.command == "build-composite":
        base_graph = load_graph(args.base_graph)
        fragments = [load_composite_input(path) for path in args.fragment]
        capabilities = load_composite_input(args.capabilities)
        payload = build_composite_estate(base_graph, fragments, capabilities)
        write_composite_estate(payload, args.output)
        write_composite_receipt(payload, args.receipt)
        evidence_payload = None
        if args.legacy_root is not None:
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
                    "base_graph_content_sha256": payload["base_graph"]["content_sha256"],
                    "content_sha256": payload["content_sha256"],
                    "evidence_pack_content_sha256": (
                        evidence_payload["content_sha256"] if evidence_payload else None
                    ),
                    "fragments": payload["fragments"],
                    "output": str(args.output),
                    **payload["statistics"],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    if args.command in {"build-oracle-reference", "validate-oracle-reference"}:
        base_graph = load_graph(args.base_graph)
        slices = json.loads(args.slices.read_text(encoding="utf-8"))
        inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
        source_pin = json.loads(args.source_pin.read_text(encoding="utf-8"))
        if args.command == "build-oracle-reference":
            payload = build_oracle_reference_fragment(
                base_graph, slices, inventory, source_pin
            )
            write_oracle_reference_fragment(payload, args.output)
            write_oracle_reference_receipt(payload, args.receipt)
            errors = validate_oracle_reference_fragment(
                payload, base_graph, slices, inventory, source_pin
            )
            print(json.dumps({
                "content_sha256": payload["content_sha256"],
                "errors": errors,
                "output": str(args.output),
                "status": "passed" if not errors else "failed",
                **payload["statistics"],
            }, indent=2, sort_keys=True))
            return 0 if not errors else 1
        fragment = json.loads(args.fragment.read_text(encoding="utf-8"))
        errors = validate_oracle_reference_fragment(
            fragment, base_graph, slices, inventory, source_pin
        )
        print(json.dumps(
            {"errors": errors, "status": "passed" if not errors else "failed"},
            indent=2,
            sort_keys=True,
        ))
        return 0 if not errors else 1

    if args.command in {"build-cloudbank-reference", "validate-cloudbank-reference"}:
        base_graph = load_graph(args.base_graph)
        workloads = json.loads(args.workloads.read_text(encoding="utf-8"))
        inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
        source_pin = json.loads(args.source_pin.read_text(encoding="utf-8"))
        if args.command == "build-cloudbank-reference":
            payload = build_cloudbank_reference_fragment(
                base_graph, workloads, inventory, source_pin
            )
            write_cloudbank_reference_fragment(payload, args.output)
            write_cloudbank_reference_receipt(payload, args.receipt)
            errors = validate_cloudbank_reference_fragment(
                payload, base_graph, workloads, inventory, source_pin
            )
            print(json.dumps({
                "content_sha256": payload["content_sha256"],
                "errors": errors,
                "output": str(args.output),
                "status": "passed" if not errors else "failed",
                **payload["statistics"],
            }, indent=2, sort_keys=True))
            return 0 if not errors else 1
        fragment = json.loads(args.fragment.read_text(encoding="utf-8"))
        errors = validate_cloudbank_reference_fragment(
            fragment, base_graph, workloads, inventory, source_pin
        )
        print(json.dumps(
            {"errors": errors, "status": "passed" if not errors else "failed"},
            indent=2,
            sort_keys=True,
        ))
        return 0 if not errors else 1

    if args.command == "validate-composite":
        payload = load_graph(args.graph)
        base_graph = load_graph(args.base_graph)
        fragments = [load_composite_input(path) for path in args.fragment]
        capabilities = load_composite_input(args.capabilities)
        errors = validate_composite_estate(payload, base_graph, fragments, capabilities)
        if args.evidence_pack.is_file():
            errors.extend(validate_evidence_pack(payload, load_evidence_pack(args.evidence_pack)))
        errors = sorted(set(errors))
        print(
            json.dumps(
                {"errors": errors, "status": "passed" if not errors else "failed"},
                indent=2,
                sort_keys=True,
            )
        )
        return 0 if not errors else 1

    if args.command == "doctor":
        result = developer_doctor(args.project_root)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["status"] == "passed" else 1

    if args.command == "demo":
        try:
            result = developer_demo(args.project_root)
        except (OSError, ValueError, KeyError) as exc:
            print(json.dumps({"status": "failed", "error": str(exc)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(result, indent=2, sort_keys=True))
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
        try:
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
                args.i_understand_this_is_unauthenticated,
                args.verifier_token,
            )
            return 0
        except ValueError as exc:
            print(f"Control Tower refused to start: {exc}")
            return 2

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
        def load_optional(path: Path) -> dict | None:
            return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

        receipt = load_optional(args.cics_vsam_receipt)
        asm_receipt = load_optional(args.asm_receipt)
        ims_receipt = load_optional(args.ims_receipt)
        pli_fragment = load_optional(args.pli_fragment)
        extension_catalog = load_optional(args.extension_catalog)
        pli_coverage_receipt = load_optional(args.pli_coverage_receipt)
        pli_development_receipt = load_optional(args.pli_development_receipt)
        pli_build_receipt = load_optional(args.pli_build_receipt)
        pli_build_attestation = load_optional(args.pli_build_attestation)
        postgres_data_receipt = load_optional(args.postgres_data_receipt)
        oracle_data_receipt = load_optional(args.oracle_data_receipt)
        data_rehearsal_receipt = load_optional(args.data_rehearsal_receipt)
        campaign_receipt = load_optional(args.campaign_receipt)
        enterprise_appliance_receipt = load_optional(args.enterprise_appliance_receipt)
        expected = analyze_capabilities(
            payload,
            cics_vsam_receipt=receipt,
            asm_receipt=asm_receipt,
            ims_receipt=ims_receipt,
            pli_fragment=pli_fragment,
            extension_catalog=extension_catalog,
            pli_coverage_receipt=pli_coverage_receipt,
            pli_development_receipt=pli_development_receipt,
            pli_build_receipt=pli_build_receipt,
            pli_build_attestation=pli_build_attestation,
            postgres_data_receipt=postgres_data_receipt,
            oracle_data_receipt=oracle_data_receipt,
            data_rehearsal_receipt=data_rehearsal_receipt,
            campaign_receipt=campaign_receipt,
            enterprise_appliance_receipt=enterprise_appliance_receipt,
        )
        if args.validate_only:
            analysis = json.loads(args.output.read_text(encoding="utf-8"))
        else:
            analysis = expected
            write_capability_analysis(analysis, args.output)
        errors = validate_capability_analysis(analysis, payload, expected)
        print(
            json.dumps(
                {
                    "capabilities": analysis.get("capabilities", []),
                    "collection_mechanisms": analysis.get("collection_mechanisms", []),
                    "content_sha256": analysis.get("content_sha256"),
                    "evidence_bindings": analysis.get("evidence_bindings", {}),
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
