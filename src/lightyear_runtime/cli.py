from __future__ import annotations

import argparse
import json
from pathlib import Path

from lightyear_knowledge_graph.model import load_graph

from .adapters import FixtureAdapter, LocalOracleAdapter
from .engine import RuntimeEvidenceEngine, load_snapshot, validate_snapshot, write_snapshot
from .mock_zosmf import RunningMockZosmf, load_mock_fixture
from .zosmf import (
    HttpClientTransport,
    ZosmfClient,
    ZosmfConfig,
    ZosmfCredentials,
    ZosmfJobsAdapter,
)


DEFAULT_GRAPH = Path("knowledge/graph.snapshot.json.gz")
DEFAULT_FIXTURE = Path("knowledge/runtime/fixtures/intcalc-zos-replay.json")
DEFAULT_SNAPSHOT = Path("knowledge/runtime/runtime.snapshot.json.gz")
DEFAULT_ZOSMF_MAPPING = Path("knowledge/runtime/zosmf/intcalc-mapping.json")
DEFAULT_ZOSMF_FIXTURE = Path("knowledge/runtime/zosmf/mock-intcalc.json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LIGHTYEAR runtime evidence plane")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="Capture local evidence and replay recorded fixtures")
    build.add_argument("--graph", type=Path, default=DEFAULT_GRAPH)
    build.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    build.add_argument("--work-dir", type=Path, default=Path("work/runtime-capture"))
    build.add_argument("--output", type=Path, default=DEFAULT_SNAPSHOT)

    replay = subparsers.add_parser("replay", help="Build a snapshot from one adapter fixture")
    replay.add_argument("--graph", type=Path, default=DEFAULT_GRAPH)
    replay.add_argument("--fixture", type=Path, required=True)
    replay.add_argument("--output", type=Path, required=True)

    validate = subparsers.add_parser("validate", help="Validate hashes, ledger chains, and graph identity")
    validate.add_argument("--graph", type=Path, default=DEFAULT_GRAPH)
    validate.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)

    compare = subparsers.add_parser("compare", help="Compare canonical runtime snapshot identities")
    compare.add_argument("--expected", type=Path, required=True)
    compare.add_argument("--actual", type=Path, required=True)

    inspect = subparsers.add_parser("inspect", help="Inspect runtime status or one graph entity")
    inspect.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    inspect.add_argument("--node")
    inspect.add_argument("--edge")

    diagnose = subparsers.add_parser(
        "zosmf-diagnose", help="Test a read-only z/OSMF Jobs connection without retaining secrets"
    )
    diagnose.add_argument("--base-url")
    diagnose.add_argument("--owner", required=True)
    diagnose.add_argument("--prefix", default="*")
    diagnose.add_argument("--max-jobs", type=int, default=10)

    capture = subparsers.add_parser(
        "capture-zosmf", help="Capture one completed JES job as graph-addressed runtime evidence"
    )
    capture.add_argument("--base-url")
    capture.add_argument("--graph", type=Path, default=DEFAULT_GRAPH)
    capture.add_argument("--mapping", type=Path, default=DEFAULT_ZOSMF_MAPPING)
    capture.add_argument("--job-name", required=True)
    capture.add_argument("--job-id", required=True)
    capture.add_argument("--output", type=Path, required=True)
    capture.add_argument(
        "--attest-real-zos",
        action="store_true",
        help="Assert this non-loopback HTTPS endpoint is an authorized real z/OS system",
    )

    simulate = subparsers.add_parser(
        "simulate-zosmf", help="Run the IBM-shaped local z/OSMF simulator and capture its evidence"
    )
    simulate.add_argument("--graph", type=Path, default=DEFAULT_GRAPH)
    simulate.add_argument("--mapping", type=Path, default=DEFAULT_ZOSMF_MAPPING)
    simulate.add_argument("--fixture", type=Path, default=DEFAULT_ZOSMF_FIXTURE)
    simulate.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command in {"build", "replay"}:
        graph = load_graph(args.graph)
        adapters = [FixtureAdapter(args.fixture)]
        if args.command == "build":
            adapters.insert(0, LocalOracleAdapter(args.work_dir))
        payload = RuntimeEvidenceEngine(graph).build(adapter.capture() for adapter in adapters)
        write_snapshot(payload, args.output)
        print(json.dumps({"output": str(args.output), **payload["statistics"], "content_sha256": payload["content_sha256"]}, indent=2, sort_keys=True))
        return 0
    if args.command == "validate":
        errors = validate_snapshot(load_snapshot(args.snapshot), load_graph(args.graph))
        print(json.dumps({"errors": errors, "status": "passed" if not errors else "failed"}, indent=2, sort_keys=True))
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
        payload = load_snapshot(args.snapshot)
        if args.node and args.edge:
            raise SystemExit("Choose either --node or --edge")
        if args.node:
            result = payload["projections"]["nodes"].get(args.node, {"state": "static_only"})
        elif args.edge:
            result = payload["projections"]["edges"].get(args.edge, {"state": "static_only"})
        else:
            result = {"statistics": payload["statistics"], "runs": [
                {key: run[key] for key in ("run_id", "adapter_id", "source_system", "policies", "content_sha256")}
                for run in payload["runs"]
            ]}
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.command == "zosmf-diagnose":
        config = ZosmfConfig.from_env(args.base_url)
        client = ZosmfClient(HttpClientTransport(config), ZosmfCredentials.from_env())
        jobs = client.list_jobs(args.owner, args.prefix, args.max_jobs)
        safe_jobs = [{
            key: job.get(key)
            for key in ("jobname", "jobid", "owner", "status", "retcode", "exec-system")
        } for job in jobs]
        print(json.dumps({
            "status": "passed",
            "source_alias": config.source_alias,
            "job_count": len(safe_jobs),
            "jobs": safe_jobs,
            "credentials_retained": False,
        }, indent=2, sort_keys=True))
        return 0
    if args.command == "capture-zosmf":
        config = ZosmfConfig.from_env(args.base_url)
        adapter = ZosmfJobsAdapter(
            ZosmfClient(HttpClientTransport(config), ZosmfCredentials.from_env()),
            config,
            args.mapping,
            args.job_name,
            args.job_id,
            attest_real_zos=args.attest_real_zos,
        )
        payload = RuntimeEvidenceEngine(load_graph(args.graph)).build([adapter.capture()])
        write_snapshot(payload, args.output)
        print(json.dumps({
            "status": "passed",
            "output": str(args.output),
            "content_sha256": payload["content_sha256"],
            "evidence_classes": payload["statistics"]["evidence_classes"],
            "mainframe_equivalence": payload["runs"][0]["policies"]["mainframe_equivalence"],
        }, indent=2, sort_keys=True))
        return 0
    if args.command == "simulate-zosmf":
        fixture = load_mock_fixture(args.fixture)
        with RunningMockZosmf(fixture) as mock:
            config = ZosmfConfig(
                mock.base_url,
                "local-zosmf-simulator",
                allow_loopback_http=True,
            )
            adapter = ZosmfJobsAdapter(
                ZosmfClient(HttpClientTransport(config), ZosmfCredentials()),
                config,
                args.mapping,
                fixture["job"]["jobname"],
                fixture["job"]["jobid"],
            )
            bundle = adapter.capture()
        payload = RuntimeEvidenceEngine(load_graph(args.graph)).build([bundle])
        write_snapshot(payload, args.output)
        print(json.dumps({
            "status": "passed",
            "output": str(args.output),
            "request_count": len(mock.server.requests),
            "content_sha256": payload["content_sha256"],
            "evidence_classes": payload["statistics"]["evidence_classes"],
            "mainframe_equivalence": payload["runs"][0]["policies"]["mainframe_equivalence"],
        }, indent=2, sort_keys=True))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
