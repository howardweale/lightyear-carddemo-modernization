"""Loopback transport for MCP; the HTTP service remains the sole journal writer."""

import json
from urllib.parse import urlsplit, quote
from urllib.request import Request, build_opener, ProxyHandler
from urllib.error import HTTPError
from .decisions import DecisionUnauthorized


class ConsoleClient:
    def __init__(self, url):
        u = urlsplit(url)
        if (
            u.scheme != "http"
            or u.hostname != "127.0.0.1"
            or not u.port
            or u.path not in {"", "/"}
            or u.query
            or u.fragment
            or u.username
        ):
            raise ValueError("MCP requires an explicit loopback console URL")
        self.url = "http://127.0.0.1:" + str(u.port)
        self.opener = build_opener(ProxyHandler({}))

    def _call(self, route, token=None, payload=None):
        headers = {"Origin": self.url}
        if token:
            headers["Authorization"] = "Bearer " + token
        if payload is not None:
            headers["Content-Type"] = "application/json"
        req = Request(
            self.url + "/api/tower/" + route,
            headers=headers,
            data=json.dumps(payload).encode() if payload is not None else None,
        )
        try:
            with self.opener.open(req, timeout=30) as response:
                raw = response.read(8 * 1024 * 1024 + 1)
                if len(raw) > 8 * 1024 * 1024:
                    raise ValueError("Console response exceeds bound")
                return json.loads(raw)
        except HTTPError as exc:
            if exc.code == 403:
                raise DecisionUnauthorized(
                    "Console credential or role refused"
                ) from None
            raise ValueError("Console request refused: " + str(exc.code)) from None

    def login(self, credential):
        return self._call("session", payload={"credential": credential})

    def logout(self, token):
        return self._call("logout", token, {})

    def _read_access(self, token):
        pass  # Every actual HTTP route authenticates.

    def queue(self, token):
        return self._call("queue", token)

    def item(self, token, item_id):
        return self._call("item?id=" + quote(item_id, safe=""), token)

    def campaign_status(self, token, campaign_id):
        return self._call("campaign?id=" + quote(campaign_id, safe=""), token)

    def catalogue(self, token):
        return self._call("catalogue", token)

    def propose(self, token, kind, payload):
        return self._call("propose", token, {**payload, "proposal_type": kind})
