"""Local stdio MCP adapter. The configured project is fixed at server startup."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .service import Workflow


def create_server(project: Path):
    from mcp.server import MCPServer
    from mcp.types import ToolAnnotations

    workflow = Workflow(project)
    server = MCPServer("Lightyear local workflow", version="1.0.0", instructions=(
        "Use capabilities, then plan. Start only the reviewed plan with a UUID request_id; reuse that UUID on retries. "
        "Poll status by run_id; client disconnect does not cancel a run. Check ok and status in every response. "
        "verified means replay-valid evidence, not completed work or fresh database execution. "
        "Human decisions happen separately in Control Tower. This server cannot approve them."))
    read = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
    write = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)

    @server.tool(annotations=read)
    def capabilities() -> dict[str, Any]:
        """Discover this project's workflow, scope and supported operations."""
        return workflow.invoke("capabilities")

    @server.tool(annotations=read)
    def plan() -> dict[str, Any]:
        """Review exact input/policy digest, budgets and human-decision requirements. Does not execute."""
        return workflow.invoke("plan")

    @server.tool(annotations=write)
    def start(plan_sha256: str, request_id: str) -> dict[str, Any]:
        """Start retained-evidence verification under existing local policy; return a durable run ID. No approval is created."""
        return workflow.invoke("start", plan_sha256=plan_sha256, request_id=request_id)

    @server.tool(annotations=read)
    def status(run_id: str) -> dict[str, Any]:
        """Read verified progress, completion or human-decision blockers for a project-owned run."""
        return workflow.invoke("status", run_id=run_id)

    @server.tool(annotations=read)
    def events(run_id: str, after: int = 0, limit: int = 10) -> dict[str, Any]:
        """Read a verified journal page (at most 25 events); next_cursor supports bounded polling."""
        return workflow.invoke("events", run_id=run_id, after=after, limit=limit)

    @server.tool(annotations=read)
    def verify(run_id: str) -> dict[str, Any]:
        """Replay the journal. A verified human-decision halt remains incomplete, never a pass."""
        return workflow.invoke("verify", run_id=run_id)

    @server.tool(annotations=write)
    def export(run_id: str) -> dict[str, Any]:
        """Publish a verified terminal evidence bundle to a fixed run-owned path; return its hash and resource URI."""
        return workflow.invoke("export", run_id=run_id)

    @server.tool(annotations=write)
    def resume(run_id: str) -> dict[str, Any]:
        """Recover an interrupted run under its unchanged plan. OS locking excludes concurrent workers. Terminal runs stay terminal."""
        return workflow.invoke("resume", run_id=run_id)

    @server.resource("lightyear://plan/current", mime_type="application/json")
    def current_plan() -> str:
        """Full current plan and input bindings; no execution or authorization."""
        return json.dumps(workflow._plan(), sort_keys=True)

    @server.resource("lightyear://runs/{run_id}/events", mime_type="application/json")
    def run_events(run_id: str) -> str:
        """First verified journal page; use the events tool for subsequent pages."""
        return json.dumps(workflow.invoke("events", run_id=run_id), sort_keys=True)

    @server.resource("lightyear://runs/{run_id}/evidence", mime_type="application/json")
    def evidence(run_id: str) -> str:
        """Replay-verified terminal evidence; no export file is written by this read."""
        workflow._guard()
        return json.dumps(workflow.evidence(run_id), sort_keys=True)

    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    args = parser.parse_args()
    create_server(args.project).run(transport="stdio")


if __name__ == "__main__":
    main()
