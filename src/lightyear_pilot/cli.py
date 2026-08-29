from __future__ import annotations

import argparse
import json
import platform
import sys
import tempfile
from pathlib import Path

from lightyear_common.io import write_json, write_text
from lightyear_knowledge_graph.model import load_graph

from .analysis import (
    build_source_analysis,
    validate_source_analysis,
    write_analysis_graph,
)

from .pilot import (
    PilotError,
    build_dossier,
    build_intake_manifest,
    build_preflight,
    load_json,
    render_dossier_markdown,
    validate_compatibility_policy,
    validate_dossier,
    validate_intake_manifest,
    validate_preflight,
)


def _paths(project_root: Path) -> dict[str, Path]:
    pilot = project_root / "pilot"
    return {
        "profile": pilot / "pilot.profile.json",
        "compatibility": pilot / "compatibility.policy.json",
        "runtime": pilot / "runtime-manifest.json",
        "source": pilot / "reference-intake",
        "canonical": pilot / "reference-output",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LIGHTYEAR governed source-only pilot release")
    parser.add_argument("--project-root", type=Path, default=Path("."))
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("doctor", help="Check pilot runtime and committed evidence prerequisites")

    intake = subparsers.add_parser("intake", help="Inventory an approved source-only intake")
    intake.add_argument("--source-root", type=Path, required=True)
    intake.add_argument("--approval-id", required=True)
    intake.add_argument("--source-label", required=True)
    intake.add_argument("--output", type=Path, required=True)

    preflight = subparsers.add_parser("preflight", help="Generate the gates 6-8 onboarding checklist")
    preflight.add_argument("--intake", type=Path, required=True)
    preflight.add_argument("--output", type=Path, required=True)

    analyze = subparsers.add_parser("analyze", help="Build a customer-specific typed source estate")
    analyze.add_argument("--source-root", type=Path, required=True)
    analyze.add_argument("--intake", type=Path, required=True)
    analyze.add_argument("--output-graph", type=Path, required=True)
    analyze.add_argument("--output-receipt", type=Path, required=True)

    dossier = subparsers.add_parser("dossier", help="Build the evidence-bound offline pilot dossier")
    dossier.add_argument("--intake", type=Path, required=True)
    dossier.add_argument("--preflight", type=Path, required=True)
    dossier.add_argument("--analysis", type=Path, required=True)
    dossier.add_argument("--analysis-graph", type=Path, required=True)
    dossier.add_argument("--output-json", type=Path, required=True)
    dossier.add_argument("--output-md", type=Path, required=True)

    rehearse = subparsers.add_parser("rehearse", help="Run the complete reference intake-to-dossier flow")
    rehearse.add_argument("--source-root", type=Path)
    rehearse.add_argument("--output-root", type=Path, required=True)
    rehearse.add_argument("--approval-id", default="repository-reference-fixture")
    rehearse.add_argument("--source-label", default="CardDemo bounded reference intake")

    subparsers.add_parser("verify", help="Rebuild, validate, and byte-compare the committed pilot evidence")
    subparsers.add_parser("compatibility", help="Validate the pilot-line schema compatibility policy")
    return parser


def _load_contracts(project_root: Path) -> tuple[dict, dict]:
    paths = _paths(project_root)
    return load_json(paths["profile"]), load_json(paths["compatibility"])


def _rehearse(project_root: Path, source_root: Path, output_root: Path, approval_id: str, source_label: str) -> dict:
    profile, compatibility = _load_contracts(project_root)
    intake = build_intake_manifest(source_root, profile, approval_id=approval_id, source_label=source_label)
    errors = validate_intake_manifest(intake, profile, source_root)
    if errors:
        raise PilotError(errors[0])
    analysis_graph, analysis = build_source_analysis(
        source_root,
        intake,
        profile,
        project_root / "pilot/analysis-relationships.json",
    )
    errors = validate_source_analysis(
        analysis_graph,
        analysis,
        intake,
        profile,
        project_root / "pilot/analysis-relationships.json",
    )
    if errors:
        raise PilotError(errors[0])
    preflight = build_preflight(project_root, intake, profile)
    errors = validate_preflight(preflight, intake)
    if errors:
        raise PilotError(errors[0])
    dossier = build_dossier(
        project_root,
        intake,
        preflight,
        analysis,
        analysis_graph,
        profile,
        compatibility,
    )
    errors = validate_dossier(
        dossier,
        intake,
        preflight,
        analysis,
        analysis_graph,
        project_root,
        profile,
    )
    if errors:
        raise PilotError(errors[0])
    output_root.mkdir(parents=True, exist_ok=True)
    write_json(output_root / "intake.manifest.json", intake)
    write_analysis_graph(analysis_graph, output_root / "source-estate.snapshot.json.gz")
    write_json(output_root / "source-analysis.receipt.json", analysis)
    write_json(output_root / "mainframe.preflight.json", preflight)
    write_json(output_root / "pilot.dossier.json", dossier)
    write_text(output_root / "pilot.dossier.md", render_dossier_markdown(dossier))
    return dossier


def _doctor(project_root: Path) -> int:
    paths = _paths(project_root)
    required = [
        paths["profile"], paths["compatibility"], paths["runtime"], project_root / "knowledge/composite/estate.receipt.json",
        project_root / "knowledge/capabilities/mainframe-readiness.json",
        project_root / "extensions/adapters/appliance/appliance.receipt.json",
    ]
    checks = {
        "python_3_11_or_newer": sys.version_info >= (3, 11),
        "supported_platform": platform.system() in {"Linux", "Darwin", "Windows"},
        "pilot_profile_present": paths["profile"].is_file(),
        "compatibility_policy_present": paths["compatibility"].is_file(),
        "runtime_manifest_present": paths["runtime"].is_file(),
        "reference_intake_present": paths["source"].is_dir(),
        "bound_evidence_present": all(path.exists() for path in required),
    }
    print(json.dumps({"status": "passed" if all(checks.values()) else "failed", "checks": checks}, indent=2, sort_keys=True))
    return 0 if all(checks.values()) else 1


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    project_root = args.project_root.resolve()
    paths = _paths(project_root)
    try:
        if args.command == "doctor":
            return _doctor(project_root)
        profile, compatibility = _load_contracts(project_root)
        if args.command == "intake":
            payload = build_intake_manifest(args.source_root.resolve(), profile, approval_id=args.approval_id, source_label=args.source_label)
            errors = validate_intake_manifest(payload, profile, args.source_root.resolve())
            if errors:
                raise PilotError(errors[0])
            write_json(args.output, payload)
            print(payload["content_sha256"])
        elif args.command == "preflight":
            intake = load_json(args.intake)
            errors = validate_intake_manifest(intake, profile)
            if errors:
                raise PilotError(errors[0])
            payload = build_preflight(project_root, intake, profile)
            write_json(args.output, payload)
            print(payload["content_sha256"])
        elif args.command == "analyze":
            intake = load_json(args.intake)
            errors = validate_intake_manifest(intake, profile, args.source_root.resolve())
            if errors:
                raise PilotError(errors[0])
            graph, payload = build_source_analysis(
                args.source_root.resolve(),
                intake,
                profile,
                project_root / "pilot/analysis-relationships.json",
            )
            errors = validate_source_analysis(
                graph,
                payload,
                intake,
                profile,
                project_root / "pilot/analysis-relationships.json",
            )
            if errors:
                raise PilotError(errors[0])
            write_analysis_graph(graph, args.output_graph)
            write_json(args.output_receipt, payload)
            print(payload["content_sha256"])
        elif args.command == "dossier":
            intake = load_json(args.intake)
            preflight = load_json(args.preflight)
            analysis = load_json(args.analysis)
            analysis_graph = load_graph(args.analysis_graph)
            payload = build_dossier(
                project_root,
                intake,
                preflight,
                analysis,
                analysis_graph,
                profile,
                compatibility,
            )
            errors = validate_dossier(
                payload,
                intake,
                preflight,
                analysis,
                analysis_graph,
                project_root,
                profile,
            )
            if errors:
                raise PilotError(errors[0])
            write_json(args.output_json, payload)
            write_text(args.output_md, render_dossier_markdown(payload))
            print(payload["content_sha256"])
        elif args.command == "rehearse":
            source = args.source_root.resolve() if args.source_root else paths["source"]
            payload = _rehearse(project_root, source, args.output_root, args.approval_id, args.source_label)
            print(json.dumps({"pilot_ready": payload["pilot_ready"], "dossier_sha256": payload["content_sha256"]}, sort_keys=True))
        elif args.command == "verify":
            with tempfile.TemporaryDirectory() as directory:
                output = Path(directory)
                payload = _rehearse(project_root, paths["source"], output, "repository-reference-fixture", "CardDemo bounded reference intake")
                for name in (
                    "intake.manifest.json",
                    "source-estate.snapshot.json.gz",
                    "source-analysis.receipt.json",
                    "mainframe.preflight.json",
                    "pilot.dossier.json",
                    "pilot.dossier.md",
                ):
                    if (output / name).read_bytes() != (paths["canonical"] / name).read_bytes():
                        raise PilotError(f"committed-pilot-evidence-drift:{name}")
            print(json.dumps({"status": "passed", "pilot_ready": payload["pilot_ready"], "mainframe_equivalent": False, "production_ready": False}, sort_keys=True))
        elif args.command == "compatibility":
            errors = validate_compatibility_policy(compatibility)
            if errors:
                raise PilotError(errors[0])
            print(json.dumps({"status": "passed", "pilot_line": compatibility["pilot_line"]}, sort_keys=True))
        return 0
    except (OSError, ValueError, PilotError) as error:
        print(f"pilot-error:{error}", file=sys.stderr)
        return 1
