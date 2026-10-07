"""Read-only actual MCP/HTTP check; no submissions, models, signing or key reads."""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from lightyear_control_tower.status_export import atomic_new

BASE = {"describe_copybook", "decode_records", "read_job_log", "lane_status",
        "get_task", "submit_candidate", "get_verdict", "get_budget", "get_receipt", "propose_normalization"}
GRAPH = {"graph_search", "graph_node", "graph_neighbors", "graph_references", "explain_divergence", "graph_guidance"}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate(names, task, before, after, expected, projection=None, search=None):
    if names != BASE | (GRAPH if expected == "approved" else set()):
        raise ValueError("activation-tool-set")
    if not task.get("ok") or not before.get("ok") or before != after:
        raise ValueError("activation-task-or-budget")
    if expected == "approved":
        if task.get("context_projection_sha256") != projection:
            raise ValueError("activation-judge-context")
        if (not isinstance(search, dict) or search.get("error") or
                search.get("projection_sha256") != projection or not search.get("items")):
            raise ValueError("activation-graph-query")


async def probe(args):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    argv = ["-m", "lightyear_toolkit.mcp", "--workspace", str(args.workspace),
            "--public-manifest", str(args.public_manifest), "--judge-url", args.judge_url]
    if args.graph_projection:
        argv += ["--graph-projection", str(args.graph_projection), "--graph-decision", str(args.graph_decision)]
    params = StdioServerParameters(command=sys.executable, args=argv, env=dict(os.environ))
    async with stdio_client(params) as (reader, writer), ClientSession(reader, writer) as client:
        await client.initialize()
        names = {t.name for t in (await client.list_tools()).tools}
        async def call(name, arguments=None):
            result = await client.call_tool(name, arguments or {})
            if result.is_error:
                raise ValueError("activation-tool-error")
            return result.structured_content
        before = await call("get_budget")
        task = await call("get_task")
        search = await call("graph_search", {"query":"ACCT", "limit":1}) if args.expect == "approved" else None
        after = await call("get_budget")
        projection = sha(args.graph_projection / "projection.json.gz") if args.graph_projection else None
        validate(names, task, before, after, args.expect, projection, search)
        return dict(schema="verify-graph-activation-check/1", status="passed",
                    at_utc=datetime.now(timezone.utc).isoformat(), expected=args.expect,
                    tool_names=sorted(names), tool_count=len(names), budget_unchanged=True,
                    public_manifest_sha256=sha(args.public_manifest), projection_sha256=projection,
                    decision_proof_sha256=sha(args.graph_decision) if args.graph_decision else None,
                    probe_sha256=sha(__file__), model_calls=0, submissions=0,
                    claim="Operator-run protocol check; not Linux isolation or independent attestation")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("workspace", "public-manifest", "out"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--judge-url", required=True)
    p.add_argument("--graph-projection", type=Path)
    p.add_argument("--graph-decision", type=Path)
    p.add_argument("--expect", choices=("baseline", "approved"), required=True)
    args = p.parse_args()
    if args.out.exists():
        p.error("Output exists; preserve the earlier result")
    if bool(args.graph_projection) != bool(args.graph_decision) or (args.expect == "approved" and not args.graph_projection):
        p.error("Supply both projection and decision for graph admission")
    if not os.environ.get("LIGHTYEAR_VERIFY_TOKEN"):
        p.error("Use the agent's existing token environment, never token arguments")
    try:
        result = asyncio.run(asyncio.wait_for(probe(args), timeout=90))
    except Exception:
        atomic_new(args.out, dict(schema="verify-graph-activation-check/1", status="failed",
                                 at_utc=datetime.now(timezone.utc).isoformat(),
                                 error="activation-check-failed", model_calls=0, submissions=0))
        print("Activation check failed; preserve report and inspect locally.", file=sys.stderr)
        return 1
    atomic_new(args.out, result)
    print(json.dumps({"status":"passed", "tool_count":result["tool_count"], "model_calls":0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
