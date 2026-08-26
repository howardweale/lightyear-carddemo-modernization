from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from lightyear_common.io import write_json
from lightyear_knowledge_graph.model import load_graph

from .adapters import FixtureAdapter, RecordedReplayAdapter, default_registry
from .contracts import ExtensionContractError, canonical_hash, validate_envelope
from .pli import build_pli_fragment, fragment_receipt, validate_pli_fragment


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
                    "version": "1.0",
                    "language": "PL/I",
                    "status": "reference-proof",
                }],
            }
            payload["content_sha256"] = canonical_hash(payload)
            if args.output:
                write_json(args.output, payload)
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0

        graph = load_graph(args.graph)
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


if __name__ == "__main__":
    raise SystemExit(main())
