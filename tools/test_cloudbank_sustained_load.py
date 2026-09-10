#!/usr/bin/env python3
"""Exercise the actual k6 script against a local HTTP application double.

This validates request/response handling and native k6 metrics, not a GKE or
performance qualification. It never emits a signed live observation.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import sys
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from lightyear_data.cloudbank_journeys import ROLE_SCOPES, JourneyFailure  # noqa: E402
from lightyear_data.cloudbank_sustained_load import HTTP_SERVICES, execute_k6, validate_summary  # noqa: E402


class Application:
    def __init__(self, fault=""):
        self.fault, self.lock, self.requests, self.next_journal = fault, threading.Lock(), 0, 1
        self.accounts, self.journals, self.commands, self.fixtures = {}, {}, {}, []
        self.methods = set()
        self.transfer_response_statuses = []
        for vu in range(10):
            accounts = []
            marker = "lightyear-synthetic-journey:load-test-" + str(vu)
            for balance in (1000, 250, 5):
                key = len(self.accounts) + 1
                accounts.append(key)
                self.accounts[key] = {"accountId": key, "accountCustomerId": "test-owner",
                                      "accountOtherDetails": marker, "accountBalance": balance}
                self.journals[key] = []
            self.fixtures.append({"accounts": accounts, "marker": marker})

    def journal(self, account, kind, amount, key):
        value = {"journalId": self.next_journal, "accountId": account, "journalType": kind,
                 "journalAmount": amount, "lraId": key}
        self.next_journal += 1
        self.journals[account].append(value)
        return value

    def reply(self, method, path, headers, raw):
        with self.lock:
            self.requests += 1
            self.methods.add(method + " " + urlsplit(path).path)
            parts = urlsplit(path)
            service, _, route = parts.path[1:].partition("/")
            route = "/" + route
            if route == "/oauth2/token":
                params = parse_qs(raw)
                client, password = base64.b64decode(headers["Authorization"].split()[1]).decode().split(":", 1)
                assert password == "private-test-password"
                scopes = params["scope"][0]
                claims = {"sub": client, "scope": scopes.split(), "exp": time.time() + 31}
                encoded = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
                return 200, {"access_token": "test." + encoded + ".signature", "token_type": "Bearer", "scope": scopes}
            if not headers.get("Authorization", "").startswith("Bearer "):
                return 401, {}
            if service == "customer":
                return 200, {"customerId": "wrong" if self.fault == "semantic" else "test-owner",
                             "customerOtherDetails": "lightyear-synthetic-journey-owner"}
            if service == "account":
                bits = route.split("/")
                key = int(bits[4])
                return 200, self.journals[key] if route.endswith("/journal") else self.accounts[key]
            if service == "transfer":
                if self.fault == "transfer_http":
                    return 503, {"private": "private-test-response"}
                params = parse_qs(parts.query)
                source, target, amount = (int(params[n][0]) for n in ("fromAccount", "toAccount", "amount"))
                if amount <= 0:
                    return 400, {}
                if amount > self.accounts[source]["accountBalance"]:
                    return 409, {}
                self.accounts[source]["accountBalance"] -= amount
                self.accounts[target]["accountBalance"] += amount
                self.journal(source, "WITHDRAW", amount, headers["Idempotency-Key"])
                self.journal(target, "DEPOSIT", amount, headers["Idempotency-Key"])
                return 200, {}
            if service == "testrunner":
                key = headers["Idempotency-Key"]
                if key in self.commands:
                    return 200, {}
                self.commands[key] = True
                body = json.loads(raw)
                if route.endswith("/deposit"):
                    self.journal(body["accountId"], "PENDING", body["amount"], key)
                else:
                    row = next(row for rows in self.journals.values() for row in rows if row["journalId"] == body["journalId"])
                    row["journalType"] = "DEPOSIT"
                return 201, {}
            if service == "creditscore":
                return (500, {"private": "private-test-response"}) if self.fault == "http" else (200, {"Credit Score": "600"})
            if service == "chatbot":
                return 200, "A checking account is a bank deposit account."
            raise AssertionError("unexpected endpoint")


def exercise(fault="", *, full=False):
    app = Application(fault)

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def setup(self):
            super().setup()
            self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

        def handle(self):
            try:
                super().handle()
            except (BrokenPipeError, ConnectionResetError):
                pass  # A deliberate global k6 abort closes keep-alive sockets.

        def do_GET(self):
            self.respond()

        def do_POST(self):
            self.respond()

        def respond(self):
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode()
            status, value = app.reply(self.command, self.path, self.headers, raw)
            body = value.encode() if isinstance(value, str) else json.dumps(value).encode()
            transfer = urlsplit(self.path).path == "/transfer/transfer"
            if transfer:
                app.transfer_response_statuses.append(status)
            broken_body = transfer and fault == "transfer_truncated"
            broken_encoding = transfer and fault == "transfer_encoding"
            self.send_response(status)
            self.send_header("Content-Type", "text/plain" if isinstance(value, str) else "application/json")
            if broken_encoding:
                self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(body) + (100 if broken_body else 0)))
            if broken_body or broken_encoding:
                self.send_header("Connection", "close")
                self.close_connection = True
            self.end_headers()
            try:
                self.wfile.write(body)
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass  # A negative control aborts other virtual users in flight.

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    config = {"run_id": "ms67-load-local-test", "duration_seconds": 300 if full else 5,
              "vus": 10, "cycle_seconds": 10 if full else 0.5,
              "endpoints": {s: [f"http://127.0.0.1:{server.server_port}/{s}"] * 2 for s in HTTP_SERVICES},
              "credentials": {role: ["test-owner" if role == "owner" else "test-" + role, "private-test-password"]
                              for role in ROLE_SCOPES}, "scopes": ROLE_SCOPES, "owner": "test-owner", "fixtures": app.fixtures}
    try:
        code, value = execute_k6(ROOT, config, timeout=450 if full else 30)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)
    text = json.dumps(value)
    assert "private-test-password" not in text and "private-test-response" not in text and "access_token" not in text
    if not fault:
        assert value["http_requests"] == value["requests"] == app.requests, json.dumps(value)
    # Fast local checks cannot be admitted as a live five-minute observation.
    if full:
        validate_summary(value, config["run_id"])
    else:
        try:
            validate_summary(value, config["run_id"])
        except JourneyFailure:
            pass
        else:
            raise AssertionError("short local test admitted as live evidence")
    if fault:
        assert code != 0 and value["errors"] > 0
        assert value["failure_diagnostics"], json.dumps(value)
        if fault.startswith("transfer_"):
            diagnostics = [row for row in value["failure_diagnostics"] if row["operation"] == "transfer"]
            assert diagnostics, json.dumps(value)
            kind = "http_status" if fault == "transfer_http" else "transport"
            assert any(row["kinds"].get(kind) for row in diagnostics), json.dumps(diagnostics)
            assert value["http_failures"] > 0
            if fault != "transfer_http":
                assert app.transfer_response_statuses and set(app.transfer_response_statuses) == {200}
                assert any(app.journals.values()), "the server must commit before the client-side failure"
                cause = "unexpected_eof" if fault == "transfer_truncated" else "decompression"
                assert any(row["transport_causes"].get(cause) for row in diagnostics), json.dumps(diagnostics)
                assert all(row["k6_error_code"]["min"] > 0 for row in diagnostics)
                if fault == "transfer_encoding":
                    assert all(row["k6_error_code"]["min"] == row["k6_error_code"]["max"] == 1701 for row in diagnostics)
                print("K6_SERVER_200_CLIENT_FAILURE=" + fault + " " + json.dumps(diagnostics))
        if fault == "http":
            assert value["http_failures"] > 0
        print("K6_NATIVE_NEGATIVE_CONTROL=" + fault + " PASSED")
        return
    assert code == 0, json.dumps({"code": code, "summary": value})
    assert value["errors"] == value["http_failures"] == 0
    assert value["failure_diagnostics"] == []
    assert value["cycles_started"] == value["cycles_completed"] == value["iterations"]
    assert value["checks_effects"] == 2 * value["cycles_completed"]
    assert value["operations"]["oauth"]["requests"] > 50, "short-lived tokens were not refreshed"
    assert all(n > 0 for n in value["replica_requests"].values())
    assert value["latency_samples"] == app.requests
    for vu, fixture in enumerate(app.fixtures, 1):
        count = value["vu_cycles"][str(vu)]
        assert count > 0
        for i, account in enumerate(fixture["accounts"]):
            assert app.accounts[account]["accountBalance"] == [1000, 250, 5][i]
            assert len(app.journals[account]) == count * [3, 2, 0][i]
    print("K6_NATIVE_BUSINESS_WORKLOAD=PASSED REQUESTS=" + str(app.requests))


if __name__ == "__main__":
    # Confirm inherited debugging/export configuration cannot leak credentials.
    os.environ["K6_HTTP_DEBUG"] = "full"
    os.environ["K6_DURATION"] = "1s"
    os.environ["K6_NEW_MACHINE_READABLE_SUMMARY"] = "true"
    if sys.argv[1:] == ["--full-duration"]:
        exercise(full=True)
    else:
        exercise()
        exercise("semantic")
        exercise("http")
        exercise("transfer_http")
        exercise("transfer_truncated")
        exercise("transfer_encoding")
