#!/usr/bin/env python3
"""Exercise the deployed Logback XML with real Spring Boot and an OTel agent."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tempfile
import time
from urllib.error import URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
AGENT_VERSION = "2.18.1"
AGENT_SHA256 = "f5fafdc5684139b04db461c420a46630acf598b44de951efd756e68a73778cfa"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--maven", default="mvn")
    parser.add_argument("--agent", type=Path)
    parser.add_argument("--jar", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="ms67-logging-integration-") as directory:
        work = Path(directory)
        if args.jar:
            jar = args.jar.resolve()
        else:
            fixture = work / "application"
            shutil.copytree(ROOT / "tests/fixtures/request-logging", fixture, ignore=shutil.ignore_patterns("target"))
            subprocess.run([args.maven, "-B", "-q", "-DskipTests", "package"], cwd=fixture, check=True, timeout=360)
            jar = fixture / "target/request-logging-1.0.jar"
        if args.agent:
            agent = args.agent.resolve()
        else:
            agent = work / "agent.jar"
            url = ("https://repo.maven.apache.org/maven2/io/opentelemetry/javaagent/opentelemetry-javaagent/" +
                   AGENT_VERSION + "/opentelemetry-javaagent-" + AGENT_VERSION + ".jar")
            with urlopen(url, timeout=60) as response:
                agent.write_bytes(response.read(64 * 1024 * 1024))
        assert hashlib.sha256(agent.read_bytes()).hexdigest() == AGENT_SHA256, "agent digest mismatch"
        config = work / "logback-spring.xml"
        config.write_text((ROOT / "factory/cloudbank/platform-qualification/gke/logback-correlation.xml").read_text().replace(
            "{{PROJECT_ID}}", "example-project"), encoding="utf-8")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        env = {**os.environ, "LOGGING_CONFIG": str(config), "SERVER_PORT": str(port), "SERVER_ADDRESS": "127.0.0.1",
               "OTEL_TRACES_EXPORTER": "logging", "OTEL_METRICS_EXPORTER": "none", "OTEL_LOGS_EXPORTER": "none",
               "OTEL_SERVICE_NAME": "logging-integration", "OTEL_BSP_SCHEDULE_DELAY": "100",
               "MANAGEMENT_ENDPOINT_HEALTH_PROBES_ENABLED": "true"}
        log = work / "application.log"
        with log.open("w", encoding="utf-8") as stream:
            process = subprocess.Popen(["java", "-javaagent:" + str(agent), "-jar", str(jar)],
                                       env=env, stdout=stream, stderr=subprocess.STDOUT)
            try:
                base = f"http://127.0.0.1:{port}"
                deadline = time.monotonic() + 75
                while True:
                    assert process.poll() is None, log.read_text()
                    try:
                        with urlopen(base + "/actuator/health/readiness", timeout=1) as response:
                            if response.status == 200:
                                break
                    except (URLError, OSError):
                        pass
                    assert time.monotonic() < deadline, log.read_text()
                    time.sleep(0.5)
                trace_id = "29e36fa1b155de929ad951bf4af72d46"
                request = Request(base + "/probe?private=SENSITIVE_QUERY_MARKER", data=b"SENSITIVE_BODY_MARKER", headers={
                    "Authorization": "Bearer SENSITIVE_HEADER_MARKER", "Content-Type": "text/plain",
                    "traceparent": "00-" + trace_id + "-1234567890abcdef-01"}, method="POST")
                with urlopen(request, timeout=10) as response:
                    assert response.read() == b"ok"
                deadline = time.monotonic() + 15
                while True:
                    raw = log.read_text(encoding="utf-8")
                    events = [json.loads(line) for line in raw.splitlines() if line.startswith('{"severity"')]
                    correlated = [row for row in events if row.get("logging.googleapis.com/trace") ==
                                  "projects/example-project/traces/" + trace_id]
                    exported = [line for line in raw.splitlines() if "LoggingSpanExporter" in line and trace_id in line]
                    if correlated and exported:
                        break
                    assert time.monotonic() < deadline, raw
                    time.sleep(0.2)
                assert "business-logging-preserved" in raw
                # The test-only span exporter prints span attributes, including
                # url.query. Production exports spans over OTLP. Inspect the
                # application output separately from this test transport.
                application_output = "\n".join(line for line in raw.splitlines() if "LoggingSpanExporter" not in line)
                assert all(marker not in application_output for marker in (
                    "SENSITIVE_QUERY_MARKER", "SENSITIVE_BODY_MARKER", "SENSITIVE_HEADER_MARKER")), application_output
                for row in correlated:
                    assert set(row) == {"severity", "message", "event", "logging.googleapis.com/trace", "logging.googleapis.com/spanId"}
                    span = row["logging.googleapis.com/spanId"]
                    assert re.fullmatch(r"[0-9a-f]{16}", span) and span != "0000000000000000"
                    assert any(span in line for line in exported), "log span does not match an exported span"
                    assert row["message"] == row["event"] == "cloudbank-request-context"
                print(json.dumps({"status": "passed-real-request-logging", "spring_boot": "3.5.15",
                                  "java_agent": AGENT_VERSION, "correlated_events": len(correlated),
                                  "sensitive_markers_logged": 0, "business_logging_preserved": True}))
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)


if __name__ == "__main__":
    main()
