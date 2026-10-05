"""Agent-side stdio tools. All evaluation execution is in the operator's service."""

import argparse
import base64
import json
import os
import sys
from pathlib import Path
from typing import Any
from .client import JudgeClient
from .workspace import Workspace, Refused, ARTIFACT_LIMIT


def create_server(workspace, client, graph=None):
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

    def decode_records(
        path: str, copybook: str, codec: str = "cp037", framing: str = "fixed"
    ) -> dict[str, Any]:
        """Decode only operator-bound public development files in this workspace."""
        return safe(workspace.decode, path, copybook, codec, framing)

    if graph is None:
        server.tool(annotations=read)(decode_records)
    else:
        @server.tool(name="decode_records", annotations=read)
        def decode_page(path: str, copybook: str, codec: str = "cp037", framing: str = "fixed",
                        offset: int = 0, limit: int = 50, fields: list[str] | None = None,
                        summary: bool = False) -> dict[str, Any]:
            """Page/project public development records, or summarize all public records."""
            return safe(workspace.decode_page, path, copybook, codec, framing, offset, limit, fields, summary)

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

    if graph is not None:
        @server.tool(annotations=read)
        def graph_search(query: str, kind: str = "", limit: int = 10, cursor: str = "") -> dict[str, Any]:
            """Search approved structure; opaque cursors are scoped to this query and projection."""
            return safe(graph.call, "graph_search", query=query, kind=kind, limit=limit, cursor=cursor)

        @server.tool(annotations=read)
        def graph_node(node_id: str, include_source: bool = False) -> dict[str, Any]:
            """Read an approved node, optionally with bounded approved source."""
            return safe(graph.call, "graph_node", node_id=node_id, include_source=include_source)

        @server.tool(annotations=read)
        def graph_neighbors(node_id: str, relations: list[str] = [], direction: str = "both",
                            depth: int = 1, limit: int = 25, cursor: str = "") -> dict[str, Any]:
            """Read approved structural neighbors, depth one or two."""
            return safe(graph.call, "graph_neighbors", node_id=node_id, relations=relations,
                        direction=direction, depth=depth, limit=limit, cursor=cursor)

        @server.tool(annotations=read)
        def graph_references(node_id: str, cursor: str = "") -> dict[str, Any]:
            """Locate approved lexical source references to a field; at most fifty results."""
            return safe(graph.call, "graph_references", node_id=node_id, cursor=cursor)

        @server.tool(annotations=read)
        def explain_divergence(attempt_id: str, cursor: str = "") -> dict[str, Any]:
            """Map only the existing visible verdict to approved code; never reveal values."""
            return safe(graph.call, "explain_divergence", attempt_id=attempt_id, cursor=cursor)
        original_list = server.list_tools
        retired = False

        async def list_current_tools():
            nonlocal retired
            if not graph.active() and not retired:
                for name in ("graph_search","graph_node","graph_neighbors","graph_references","explain_divergence","decode_records"):
                    server.remove_tool(name)
                server.tool(annotations=read)(decode_records)
                retired = True
            listed = await original_list()
            if retired:
                order = ("describe_copybook","decode_records","read_job_log","lane_status",
                         "get_task","submit_candidate","get_verdict","get_budget","get_receipt","propose_normalization")
                listed.sort(key=lambda tool: order.index(tool.name))
            return listed

        server.list_tools = list_current_tools
    return server


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--public-manifest", required=True, type=Path)
    parser.add_argument("--judge-url", required=True)
    parser.add_argument("--graph-projection", type=Path)
    parser.add_argument("--graph-decision", type=Path)
    args = parser.parse_args(argv)
    config = json.loads(args.public_manifest.read_text(encoding="utf-8"))
    client = JudgeClient(args.judge_url, os.environ["LIGHTYEAR_VERIFY_TOKEN"])
    graph = None
    if args.graph_projection or args.graph_decision:
        try:
            if not args.graph_projection or not args.graph_decision:
                raise Refused("graph-arguments-incomplete")
            from .graph import GraphTools
            graph = GraphTools.approved(args.graph_projection,
                json.loads(args.graph_decision.read_bytes()), config["graph_trust"], args.workspace, client)
        except Exception:
            print("graph tools disabled: projection approval verification failed", file=sys.stderr)
    create_server(Workspace(args.workspace, config["files"], config.get("catalogue")),
                  client, graph).run(transport="stdio")


if __name__ == "__main__":
    main()
