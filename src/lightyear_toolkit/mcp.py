"""Agent-side stdio tools. All evaluation execution is in the operator's service."""

import argparse
import base64
import json
import os
from pathlib import Path
from typing import Any
from .client import JudgeClient
from .workspace import Workspace, Refused, ARTIFACT_LIMIT


def create_server(workspace, client):
    from mcp.server import MCPServer
    from mcp.types import ToolAnnotations

    server = MCPServer(
        "Lightyear Verify",
        instructions="Use public development inputs. Submit candidate code, never output records. Human decisions belong in Control Tower. Evaluation records and raw logs are never available.",
    )
    read = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
    submit = ToolAnnotations(
        readOnlyHint=False, idempotentHint=True, openWorldHint=False
    )

    def safe(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Refused as exc:
            return {"ok": False, "error": str(exc)}
        except Exception:
            return {"ok": False, "error": "operation-refused"}

    @server.tool(annotations=read)
    def describe_copybook(path: str) -> dict[str, Any]:
        """Describe a bound public copybook's fields, offsets and record length."""
        return safe(workspace.describe, path)

    @server.tool(annotations=read)
    def decode_records(
        path: str, copybook: str, codec: str = "cp037", framing: str = "fixed"
    ) -> dict[str, Any]:
        """Decode only operator-bound public development files in this workspace."""
        return safe(workspace.decode, path, copybook, codec, framing)

    @server.tool(annotations=read)
    def read_job_log(path: str) -> dict[str, Any]:
        """Parse a bound public development job log. No evaluation log access."""
        return safe(workspace.log, path)

    @server.tool(annotations=read)
    def lane_status(source: str = "CBACT04C", target: str = "Java") -> dict[str, Any]:
        """Return the bound lane catalogue status, without upgrading qualification."""
        return safe(workspace.lane, source, target)

    @server.tool(annotations=read)
    def get_task() -> dict[str, Any]:
        """Read the public work order, shapes, development inputs and submission budget."""
        return safe(client.call, "get_task")

    @server.tool(annotations=submit)
    def submit_candidate(path: str, request_id: str) -> dict[str, Any]:
        """Submit a JAR with an idempotency UUID; returns an attempt ID and pending verdict."""

        def send():
            if not path.endswith(".jar"):
                raise Refused("artifact-format-refused")
            artifact = workspace.read(path, limit=ARTIFACT_LIMIT)
            return client.call(
                "submit_candidate",
                request_id=request_id,
                artifact=base64.b64encode(artifact).decode("ascii"),
            )

        return safe(send)

    @server.tool(annotations=read)
    def get_verdict(attempt_id: str) -> dict[str, Any]:
        """Poll pending, or read the final verdict and policy-limited diagnostics."""
        return safe(client.call, "get_verdict", attempt_id=attempt_id)

    @server.tool(annotations=read)
    def get_budget() -> dict[str, Any]:
        """Read fixed operator budgets; agents cannot raise them."""
        return safe(client.call, "get_budget")

    @server.tool(annotations=read)
    def get_receipt(attempt_id: str) -> dict[str, Any]:
        """Read a stable, signed value-free receipt for offline signature verification."""
        return safe(client.call, "get_receipt", attempt_id=attempt_id)

    @server.tool(annotations=submit)
    def propose_normalization(
        attempt_id: str, dataset: str, field: str
    ) -> dict[str, Any]:
        """Draft a human review request for a declared timestamp field. Cannot approve or apply it."""
        return safe(
            client.call,
            "propose_normalization",
            attempt_id=attempt_id,
            dataset=dataset,
            field=field,
        )

    return server


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--public-manifest", required=True, type=Path)
    parser.add_argument("--judge-url", required=True)
    args = parser.parse_args(argv)
    config = json.loads(args.public_manifest.read_text(encoding="utf-8"))
    create_server(
        Workspace(args.workspace, config["files"], config.get("catalogue")),
        JudgeClient(args.judge_url, os.environ["LIGHTYEAR_VERIFY_TOKEN"]),
    ).run(transport="stdio")


if __name__ == "__main__":
    main()
