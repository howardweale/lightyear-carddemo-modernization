from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from lightyear_common.io import write_json
from lightyear_knowledge_graph.model import load_graph

from .adapters import FixtureAdapter, RecordedReplayAdapter, default_registry
from .campaign import (
    BoundedHttpTransport,
    CampaignError,
    FixtureTransport,
    REQUIRED_ADAPTERS,
    collect_campaign,
    load_profile,
    validate_campaign_receipt,
)
from .contracts import ExtensionContractError, canonical_hash, validate_envelope
from .pli import PACK_VERSION, build_pli_fragment, fragment_receipt, validate_pli_fragment
from .pli_conformance import build_conformance_lab, validate_conformance_receipt
from .pli_proof import build_proof, validate_development_receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LIGHTYEAR trusted extension foundation")
    commands = parser.add_subparsers(dest="command", required=True)

    catalog = commands.add_parser("catalog", help="List registered adapter and language contracts")
    catalog.add_argument("--output", type=Path)

    build_capture = commands.add_parser("build-fixture-capture", help="Finalize a bounded fixture capture")
    build_capture.add_argument("--spec", type=Path, required=True)
    build_capture.add_argument("--graph", type=Path, required=True)
    build_capture.add_argument("--output", type=Path, required=True)

    validate_capture = commands.add_parser("validate-capture", help="Validate an adapter evidence envelope")
    validate_capture.add_argument("--capture", type=Path, required=True)
    validate_capture.add_argument("--graph", type=Path, required=True)
    validate_capture.add_argument("--trusted-key-id")
    validate_capture.add_argument("--trusted-key-env", default="LIGHTYEAR_EXTENSION_EVIDENCE_KEY")

    replay = commands.add_parser("replay", help="Replay a capture without upgrading its evidence class")
    replay.add_argument("--capture", type=Path, required=True)
    replay.add_argument("--graph", type=Path, required=True)
    replay.add_argument("--output", type=Path, required=True)
    replay.add_argument("--trusted-key-id")
    replay.add_argument("--trusted-key-env", default="LIGHTYEAR_EXTENSION_EVIDENCE_KEY")

    build_pli = commands.add_parser("build-pli", help="Build a base-graph-bound PL/I extension fragment")
    build_pli.add_argument("--graph", type=Path, required=True)
    build_pli.add_argument("--source-root", type=Path, required=True)
    build_pli.add_argument("--repository-root", type=Path, default=Path("."))
    build_pli.add_argument("--output", type=Path, required=True)
    build_pli.add_argument("--receipt", type=Path, required=True)

    validate_pli = commands.add_parser("validate-pli", help="Validate a PL/I extension fragment")
    validate_pli.add_argument("--graph", type=Path, required=True)
    validate_pli.add_argument("--fragment", type=Path, required=True)

    build_pli_conformance = commands.add_parser(
        "build-pli-conformance", help="Build synthetic PL/I supported-subset conformance evidence"
    )
    build_pli_conformance.add_argument("--graph", type=Path, required=True)
    build_pli_conformance.add_argument("--corpus-root", type=Path, required=True)
    build_pli_conformance.add_argument("--manifest", type=Path, required=True)
    build_pli_conformance.add_argument("--support-matrix", type=Path, required=True)
    build_pli_conformance.add_argument("--repository-root", type=Path, default=Path("."))
    build_pli_conformance.add_argument("--golden-output", type=Path, required=True)
    build_pli_conformance.add_argument("--receipt", type=Path, required=True)

    validate_pli_conformance = commands.add_parser(
        "validate-pli-conformance", help="Validate PL/I supported-subset conformance evidence"
    )
    validate_pli_conformance.add_argument("--graph", type=Path, required=True)
    validate_pli_conformance.add_argument("--golden", type=Path, required=True)
    validate_pli_conformance.add_argument("--receipt", type=Path, required=True)

    build_pli_proof = commands.add_parser(
        "build-pli-proof", help="Build the bounded mixed PL/I development proof"
    )
    build_pli_proof.add_argument("--project-root", type=Path, required=True)
    build_pli_proof.add_argument("--graph", type=Path, required=True)
    build_pli_proof.add_argument("--fragment", type=Path, required=True)
    build_pli_proof.add_argument("--output-root", type=Path, required=True)

    validate_pli_proof = commands.add_parser(
        "validate-pli-proof", help="Validate a mixed PL/I development receipt"
    )
    validate_pli_proof.add_argument("--project-root", type=Path, required=True)
    validate_pli_proof.add_argument("--graph", type=Path, required=True)
    validate_pli_proof.add_argument("--fragment", type=Path, required=True)
    validate_pli_proof.add_argument("--receipt", type=Path, required=True)

    fixture_campaign = commands.add_parser(
        "campaign-fixture", help="Run the mainframe access campaign against deterministic responses"
    )
    fixture_campaign.add_argument("--profile", type=Path, required=True)
    fixture_campaign.add_argument("--responses", type=Path, required=True)
    fixture_campaign.add_argument("--graph", type=Path, required=True)
    fixture_campaign.add_argument("--output-root", type=Path, required=True)

    live_campaign = commands.add_parser(
        "campaign-live", help="Run credential-safe read-only mainframe collectors"
    )
    live_campaign.add_argument("--profile", type=Path, required=True)
    live_campaign.add_argument("--graph", type=Path, required=True)
    live_campaign.add_argument("--base-url", required=True)
    live_campaign.add_argument("--output-root", type=Path, required=True)
    live_campaign.add_argument("--credential-env", default="LIGHTYEAR_MAINFRAME_BEARER")
    live_campaign.add_argument("--signing-key-env", default="LIGHTYEAR_EXTENSION_EVIDENCE_KEY")
    live_campaign.add_argument("--key-id", required=True)
    live_campaign.add_argument("--ca-file", type=Path)

    validate_campaign = commands.add_parser(
        "campaign-validate", help="Validate a complete mainframe access campaign"
    )
    validate_campaign.add_argument("--profile", type=Path, required=True)
    validate_campaign.add_argument("--graph", type=Path, required=True)
    validate_campaign.add_argument("--capture-root", type=Path, required=True)
    validate_campaign.add_argument("--trusted-key-id")
    validate_campaign.add_argument("--trusted-key-env", default="LIGHTYEAR_EXTENSION_EVIDENCE_KEY")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "catalog":
            payload = {
                "schema_version": "1.0",
                "adapters": default_registry().catalog(),
                "language_packs": [{
                    "id": "lightyear.pli",
                    "version": PACK_VERSION,
                    "language": "PL/I",
                    "status": "development-proof",
                }],
            }
            payload["content_sha256"] = canonical_hash(payload)
            if args.output:
                write_json(args.output, payload)
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0

        graph = load_graph(args.graph)
        if args.command == "build-pli-conformance":
            golden, receipt = build_conformance_lab(
                graph, args.corpus_root, args.manifest, args.support_matrix, args.repository_root
            )
            write_json(args.golden_output, golden)
            write_json(args.receipt, receipt)
            return _result(
                receipt["status"], output=str(args.receipt),
                content_sha256=receipt["content_sha256"], corpus=receipt["corpus"],
                checks=receipt["checks"],
            )
        if args.command == "validate-pli-conformance":
            golden = json.loads(args.golden.read_text(encoding="utf-8"))
            receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
            errors = validate_conformance_receipt(receipt, golden, graph)
            return _result("passed" if not errors else "failed", errors=errors)
        if args.command in {"build-pli-proof", "validate-pli-proof"}:
            fragment = json.loads(args.fragment.read_text(encoding="utf-8"))
            if args.command == "build-pli-proof":
                receipt = build_proof(args.project_root, graph, fragment, args.output_root)
                return _result(
                    "passed" if receipt["status"] == "passed" else "failed",
                    output=str(args.output_root),
                    content_sha256=receipt["content_sha256"],
                    checks=receipt["checks"],
                )
            receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
            errors = validate_development_receipt(receipt, args.project_root, graph, fragment)
            return _result("passed" if not errors else "failed", errors=errors)
        if args.command in {"campaign-fixture", "campaign-live", "campaign-validate"}:
            profile = load_profile(args.profile)
            if args.command == "campaign-fixture":
                responses = json.loads(args.responses.read_text(encoding="utf-8"))
                timestamp = responses.get("collected_at")
                captures, receipt = collect_campaign(
                    profile,
                    graph,
                    FixtureTransport(responses, profile["bounds"]["max_response_bytes"]),
                    evidence_class="simulated",
                    collected_at=timestamp,
                )
                _write_campaign(args.output_root, captures, receipt)
                return _result(
                    "passed", output=str(args.output_root),
                    content_sha256=receipt["content_sha256"], checks=receipt["checks"],
                )
            if args.command == "campaign-live":
                credential = os.environ.get(args.credential_env)
                signing_value = os.environ.get(args.signing_key_env)
                if credential is None:
                    raise CampaignError(f"Set {args.credential_env} for read-only mainframe access")
                if signing_value is None:
                    raise CampaignError(f"Set {args.signing_key_env} to sign live campaign evidence")
                transport = BoundedHttpTransport(
                    args.base_url,
                    credential,
                    timeout_seconds=profile["bounds"]["timeout_seconds"],
                    max_response_bytes=profile["bounds"]["max_response_bytes"],
                    ca_file=args.ca_file,
                )
                captures, receipt = collect_campaign(
                    profile, graph, transport, evidence_class="live",
                    signing_key=signing_value.encode(), key_id=args.key_id,
                )
                _write_campaign(args.output_root, captures, receipt)
                return _result(
                    "passed", output=str(args.output_root),
                    content_sha256=receipt["content_sha256"], checks=receipt["checks"],
                )
            captures, receipt = _read_campaign(args.capture_root)
            errors = validate_campaign_receipt(
                receipt, profile, graph, captures, trusted_keys=_trusted_keys(args)
            )
            return _result("passed" if not errors else "failed", errors=errors)
        if args.command == "build-fixture-capture":
            envelope = FixtureAdapter(args.spec, graph).capture()
            write_json(args.output, envelope)
            return _result("passed", output=str(args.output), content_sha256=envelope["content_sha256"])
        if args.command == "validate-capture":
            envelope = json.loads(args.capture.read_text(encoding="utf-8"))
            errors = validate_envelope(envelope, graph=graph, trusted_keys=_trusted_keys(args))
            return _result("passed" if not errors else "failed", errors=errors)
        if args.command == "replay":
            capture = json.loads(args.capture.read_text(encoding="utf-8"))
            envelope = RecordedReplayAdapter(capture, graph, _trusted_keys(args)).capture()
            write_json(args.output, envelope)
            return _result(
                "passed",
                output=str(args.output),
                content_sha256=envelope["content_sha256"],
                evidence_class=envelope["evidence_class"],
            )
        if args.command == "build-pli":
            fragment = build_pli_fragment(graph, args.source_root, args.repository_root)
            errors = validate_pli_fragment(fragment, graph)
            if errors:
                return _result("failed", errors=errors)
            write_json(args.output, fragment)
            write_json(args.receipt, fragment_receipt(fragment))
            return _result(
                "passed",
                output=str(args.output),
                content_sha256=fragment["content_sha256"],
                statistics=fragment["statistics"],
            )
        if args.command == "validate-pli":
            fragment = json.loads(args.fragment.read_text(encoding="utf-8"))
            errors = validate_pli_fragment(fragment, graph)
            return _result("passed" if not errors else "failed", errors=errors)
    except (ExtensionContractError, OSError, json.JSONDecodeError) as exc:
        return _result("failed", errors=[str(exc)])
    return 2


def _result(status: str, **values: object) -> int:
    print(json.dumps({"status": status, **values}, indent=2, sort_keys=True))
    return 0 if status == "passed" else 1


def _trusted_keys(args: argparse.Namespace) -> dict[str, bytes] | None:
    key_id = getattr(args, "trusted_key_id", None)
    if not key_id:
        return None
    variable = getattr(args, "trusted_key_env", "LIGHTYEAR_EXTENSION_EVIDENCE_KEY")
    value = os.environ.get(variable)
    if value is None:
        raise ExtensionContractError(f"Set {variable} to validate signed adapter evidence")
    return {key_id: value.encode("utf-8")}


def _write_campaign(
    output_root: Path,
    captures: list[dict[str, object]],
    receipt: dict[str, object],
) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    for capture in captures:
        adapter_id = str(capture["adapter"]["id"])  # type: ignore[index]
        if adapter_id not in REQUIRED_ADAPTERS:
            raise CampaignError(f"Refusing to write an unknown campaign adapter: {adapter_id}")
        write_json(output_root / f"{adapter_id}.capture.json", capture)
    write_json(output_root / "campaign.receipt.json", receipt)


def _read_campaign(output_root: Path) -> tuple[list[dict[str, object]], dict[str, object]]:
    receipt = json.loads((output_root / "campaign.receipt.json").read_text(encoding="utf-8"))
    captures = [
        json.loads((output_root / f"{adapter_id}.capture.json").read_text(encoding="utf-8"))
        for adapter_id in REQUIRED_ADAPTERS
    ]
    return captures, receipt


if __name__ == "__main__":
    raise SystemExit(main())
