"""Loopback HTTP client; never starts a judge and never imports its package."""

import json
import urllib.request
from urllib.parse import urlsplit
from .workspace import Refused, ARTIFACT_LIMIT


class JudgeClient:
    def __init__(self, url, token):
        parts = urlsplit(url)
        if (
            parts.scheme != "http"
            or parts.hostname != "127.0.0.1"
            or not parts.port
            or parts.path not in {"", "/"}
            or parts.query
            or parts.fragment
            or parts.username
        ):
            raise Refused("judge-endpoint-refused")
        self.url, self.token = url.rstrip("/"), token

    def call(self, method, **args):
        request = urllib.request.Request(
            self.url + "/" + method,
            data=json.dumps(args).encode(),
            headers={
                "Authorization": "Bearer " + self.token,
                "Content-Type": "application/json",
            },
            method="POST",
        )

        # Do not use environment proxies, cookies or redirects for a session token.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                raise Refused("judge-redirect-refused")

        try:
            with urllib.request.build_opener(
                urllib.request.ProxyHandler({}), NoRedirect
            ).open(request, timeout=340) as response:
                raw = response.read(4 * 1024 * 1024 + 1)
            if len(raw) > 4 * 1024 * 1024:
                raise Refused("judge-response-too-large")
            return json.loads(raw)
        except (OSError, ValueError):
            raise Refused("judge-unavailable") from None
