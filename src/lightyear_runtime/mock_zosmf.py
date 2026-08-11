from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit


class MockZosmfServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], fixture: dict[str, Any]) -> None:
        super().__init__(address, MockZosmfHandler)
        self.fixture = fixture
        self.requests: list[dict[str, Any]] = []


class MockZosmfHandler(BaseHTTPRequestHandler):
    server: MockZosmfServer

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
        parsed = urlsplit(self.path)
        self.server.requests.append({
            "method": "GET",
            "path": parsed.path,
            "query": parse_qs(parsed.query),
            "authorization_present": bool(self.headers.get("Authorization")),
            "record_range": self.headers.get("X-IBM-Record-Range"),
        })
        fixture = self.server.fixture
        base = "/zosmf/restjobs/jobs"
        job = fixture["job"]
        job_path = f"{base}/{job['jobname']}/{job['jobid']}"
        if parsed.path == base:
            self._json([job])
        elif parsed.path == job_path:
            self._json(job)
        elif parsed.path == f"{job_path}/files":
            self._json(fixture["files"])
        elif parsed.path.startswith(f"{job_path}/files/") and parsed.path.endswith("/records"):
            identifier = parsed.path.split("/")[-2]
            body = fixture["records"].get(identifier)
            if body is None:
                self._json({"message": "spool file not found"}, 404)
            else:
                self._body(body.encode("utf-8"), "text/plain")
        else:
            self._json({"message": "resource not found"}, 404)

    def log_message(self, format: str, *args: object) -> None:
        return

    def _json(self, value: Any, status: int = 200) -> None:
        self._body(json.dumps(value, sort_keys=True).encode("utf-8"), "application/json", status)

    def _body(self, body: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def load_mock_fixture(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload.get("job"), dict) or not isinstance(payload.get("files"), list):
        raise ValueError("Invalid z/OSMF simulator fixture")
    if not isinstance(payload.get("records"), dict):
        raise ValueError("Invalid z/OSMF simulator records")
    return payload


class RunningMockZosmf:
    def __init__(self, fixture: dict[str, Any], port: int = 0) -> None:
        self.server = MockZosmfServer(("127.0.0.1", port), fixture)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> "RunningMockZosmf":
        self.thread.start()
        return self

    def __exit__(self, *args: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}"
