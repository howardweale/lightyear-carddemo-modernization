#!/usr/bin/env python3
"""Verify the real transfer facade's HTTP framing with Tomcat and native k6.

Copies the governed controller into a temporary Spring application. Synthetic
local identities and responses only; this never emits live MS67 evidence.
"""
from __future__ import annotations

import base64
import http.client
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/transfer-framing"
CONTROLLER = ROOT / "factory/cloudbank/production-oauth/patches/TransferOAuthService.java"
AUTH = "Basic " + base64.b64encode(b"test-owner:synthetic-password").decode()

SCRIPT = r"""
import http from 'k6/http';
import { check } from 'k6';
export const options = {
  scenarios: { framing: { executor: 'per-vu-iterations', vus: 10, iterations: 3, maxDuration: '30s' } },
  thresholds: { checks: ['rate==1'] },
};
export default function () {
  const params = { headers: { Authorization: AUTH }, timeout: '10s' };
  const legacy = http.post(BASE + '/legacy-transfer', null, params);
  check(legacy, { 'legacy framing reproduces status 0 code 1000': r =>
    r.status === 0 && r.error_code === 1000 && /too many transfer encodings/i.test(r.error) });
  const path = BASE + '/transfer?fromAccount=1&toAccount=2&amount=';
  const ok = http.post(path + '1', null, params);
  check(ok, { 'fixed response is complete UTF-8 JSON': r =>
    r.status === 200 && !r.error_code && r.json().accepted === true && r.json().message === 'Transfer café' });
  const denied = http.post(path + '13', null, params);
  check(denied, { 'upstream rejection remains intact': r =>
    r.status === 409 && r.json().accepted === false && r.json().message === 'Transfer café' });
  const invalid = http.post(path + '0', null, params);
  check(invalid, { 'invalid amount remains rejected': r => r.status === 400 });
  const anonymous = http.post(path + '1', null, { timeout: '10s' });
  check(anonymous, { 'anonymous transfer remains rejected': r => r.status === 403 });
}
export function handleSummary(data) {
  return { stdout: JSON.stringify({ checks: data.metrics.checks.values,
    iterations: data.metrics.iterations.values.count, requests: data.metrics.http_reqs.values.count }) + '\n' };
}
"""


def headers(port, path):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        connection.request("POST", path, headers={"Authorization": AUTH})
        response = connection.getresponse()
        result = response.getheaders()
        # Only inspect headers here. k6 independently validates body framing.
        assert response.status == 200
        return result
    finally:
        connection.close()


def main():
    version = subprocess.check_output(["k6", "version"], text=True)
    assert version.startswith("k6 v2.2.0 "), version
    with tempfile.TemporaryDirectory(prefix="ms67-transfer-framing-") as directory:
        work = Path(directory)
        shutil.copytree(FIXTURE, work, dirs_exist_ok=True)
        shutil.copyfile(CONTROLLER, work / "src/main/java/com/example/transfer/TransferService.java")
        build = subprocess.run(["mvn", "-B", "-q", "-DskipTests", "package"], cwd=work,
                               capture_output=True, text=True, timeout=240)
        if build.returncode:
            raise AssertionError("Framing fixture build failed:\n" + build.stdout[-6000:] + build.stderr[-2000:])
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        with (work / "java.log").open("w+") as log:
            process = subprocess.Popen(["java", "-jar", str(work / "target/transfer-framing-1.0.jar"),
                "--server.address=127.0.0.1", f"--server.port={port}",
                f"--account.transaction.url={base}/upstream"], stdout=log, stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic() + 45
                while time.monotonic() < deadline and process.poll() is None:
                    try:
                        with urllib.request.urlopen(base + "/ready", timeout=1) as response:
                            if response.status == 200:
                                break
                    except OSError:
                        time.sleep(0.2)
                else:
                    log.seek(0)
                    raise AssertionError("Framing fixture did not start:\n" + log.read()[-6000:])
                legacy = headers(port, "/legacy-transfer")
                encodings = [v for k, v in legacy if k.lower() == "transfer-encoding"]
                assert encodings == ["chunked", "chunked"], legacy
                fixed = headers(port, "/transfer?fromAccount=1&toAccount=2&amount=1")
                assert not any(k.lower() in {"transfer-encoding", "x-upstream-hop", "set-cookie"}
                               for k, v in fixed), fixed
                assert not any(k.lower() == "connection" and "x-upstream-hop" in v.lower()
                               for k, v in fixed), fixed
                config = work / "empty-config.json"
                config.write_text("{}\n")
                env = {k: v for k, v in os.environ.items() if k.upper() in
                       {"PATH", "HOME", "TMPDIR", "TEMP", "SYSTEMROOT"}}
                source = "const BASE = " + json.dumps(base) + "; const AUTH = " + json.dumps(AUTH) + ";\n" + SCRIPT
                result = subprocess.run(["k6", "run", "--quiet", "--no-usage-report", "--log-output=none",
                    "--include-system-env-vars=false", "--traces-output=none", "--address=", "--config", str(config),
                    "--new-machine-readable-summary=false", "-"], input=source, text=True,
                    capture_output=True, cwd=work, env=env, timeout=45)
                assert result.returncode == 0, result.stdout + result.stderr
                summary = json.loads(result.stdout)
                assert summary["checks"]["fails"] == 0 and summary["checks"]["passes"] == 150, summary
                assert summary["iterations"] == 30 and summary["requests"] == 150, summary
                print("MS67_TRANSFER_FRAMING=PASSED " + json.dumps(summary))
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


if __name__ == "__main__":
    main()
