"""Read and draft-only Tower MCP. Never exposes approve/decide or engine tools."""

from pathlib import Path
from .decisions import DecisionUnauthorized, utcnow


class TowerTools:
    def __init__(self, service, credential):
        self.service = service
        session = service.login(credential)
        if session["actor"]["kind"] != "agent" or "agent" not in session["roles"]:
            service.logout(session["token"])
            raise DecisionUnauthorized("Tower MCP requires an agent identity")
        self.token = session["token"]

    def queue(self):
        return self.service.queue(self.token)

    def item(self, item_id):
        return self.service.item(self.token, item_id)

    def campaign_status(self, campaign_id):
        if hasattr(self.service, "campaign_status"):
            return self.service.campaign_status(self.token, campaign_id)
        from .features import feature

        self.service._read_access(self.token)
        adapter = feature("campaigns")
        if adapter is None:
            return {"available": False, "reason": "Campaign adapter not installed"}
        return adapter.CampaignRegistry(self.service.root, self.service.scope).view(
            campaign_id, now=utcnow()
        )

    def catalogue(self):
        if hasattr(self.service, "catalogue"):
            return self.service.catalogue(self.token)
        from .features import feature

        self.service._read_access(self.token)
        adapter = feature("catalogue")
        if adapter is None:
            return {
                "available": False,
                "entries": [],
                "reason": "Catalogue adapter not installed",
            }
        return adapter.read_catalogue(
            self.service.root, self.service.public_key, scope=self.service.scope
        )

    def propose_rule(self, payload):
        return self.service.propose(self.token, "rule-proposal", payload)

    def prepare_classification(self, payload):
        return self.service.propose(self.token, "classification-draft", payload)

    def annotate_request(self, payload):
        return self.service.propose(self.token, "annotation", payload)


def create_server(service, credential):
    from mcp.server import MCPServer
    from mcp.types import ToolAnnotations

    tools = TowerTools(service, credential)
    server = MCPServer(
        "Lightyear decision drafts",
        version="1.0.0",
        instructions="Read scoped evidence and prepare drafts only. People approve in the Decision Console. No engine dispatch or decision tools exist here.",
    )
    read = ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, openWorldHint=False
    )
    draft = ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )

    @server.tool(annotations=read)
    def queue() -> dict:
        return tools.queue()

    @server.tool(annotations=read)
    def item(item_id: str) -> dict:
        return tools.item(item_id)

    @server.tool(annotations=read)
    def campaign_status(campaign_id: str) -> dict:
        return tools.campaign_status(campaign_id)

    @server.tool(annotations=read)
    def catalogue() -> dict:
        return tools.catalogue()

    @server.tool(annotations=draft)
    def propose_rule(payload: dict) -> dict:
        return tools.propose_rule(payload)

    @server.tool(annotations=draft)
    def prepare_classification(payload: dict) -> dict:
        return tools.prepare_classification(payload)

    @server.tool(annotations=draft)
    def annotate_request(payload: dict) -> dict:
        return tools.annotate_request(payload)

    return server


def main(argv=None):
    import argparse
    from .client import ConsoleClient

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--url", default="http://127.0.0.1:8766")
    p.add_argument("--credential-file", type=Path, required=True)
    args = p.parse_args(argv)
    service = ConsoleClient(args.url)
    create_server(
        service, args.credential_file.read_text(encoding="utf-8").strip()
    ).run(transport="stdio")


if __name__ == "__main__":
    main()
