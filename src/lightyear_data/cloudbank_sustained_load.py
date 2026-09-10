"""Bounded k6 business traffic; evidence contains no request or credential data."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import re
import socket
import subprocess
import tempfile
import time
from datetime import datetime

from .cloudbank_journeys import JourneyFailure, SERVICES, hashed, require
from .cloudbank_platform_qualification import (
    MINIMUM_LOAD_SECONDS, MINIMUM_LOAD_REQUESTS, MINIMUM_LOAD_CONCURRENCY, MAXIMUM_P95_MS,
)
from .contracts import content_hash, verify_signature

OBSERVATION_TYPE = "lightyear-cloudbank-ms67-sustained-load-observation"
OBSERVATION_FILE = "sustained-load.observation.json"
PASS = "passed-bounded-sustained-business-load"
SCRIPT = Path("factory/cloudbank/platform-qualification/gke/sustained-load.js")
HTTP_SERVICES = tuple(service for service in SERVICES if service != "checks")
OPERATIONS = ("oauth", "unauthenticated", "customer", "account", "journals", "transfer",
              "invalid_transfer", "insufficient_transfer", "deposit", "clearance",
              "deposit_replay", "clearance_replay", "credit", "chat")
CYCLE_SECONDS = 10
MAX_RUN_SECONDS = MINIMUM_LOAD_SECONDS + 150
SUMMARY_PREFIX = "MS67_K6_SUMMARY="
HEX = r"[0-9a-f]{64}"


def workload(root):
    return {"script_sha256": hashed((root / SCRIPT).read_text(encoding="utf-8")),
            "executor": "constant-vus", "duration_seconds": MINIMUM_LOAD_SECONDS,
            "concurrency": MINIMUM_LOAD_CONCURRENCY, "cycle_seconds": CYCLE_SECONDS,
            "transport": "operator-loopback-to-locked-pod-port-forwards",
            "direct_http_services": list(HTTP_SERVICES), "checks_coverage": "observed-deposit-and-clearance-effects",
            "operations": list(OPERATIONS), "fixture_accounts_per_user": 3,
            "disruptions_during_load": False, "public_ingress_performance_qualified": False}


def number(value):
    return type(value) in {float, int} and math.isfinite(value) and value >= 0


def counter(value):
    return number(value) and value == int(value)


def validate_summary(value, run_id):
    """Recompute the gate independently; never trust k6's exit status alone."""
    require(isinstance(value, dict) and value.get("format") == "lightyear-k6-business-summary-v1"
            and value.get("run_id") == run_id, "load-summary-identity-invalid")
    expected = {"format", "run_id", "configured_duration_seconds", "configured_vus", "cycle_seconds",
                "measured_duration_ms", "requests", "errors", "http_requests", "http_failures", "p95_ms",
                "latency_samples", "cycles_started", "cycles_completed", "checks_effects", "checks_delivery_p95_ms",
                "iterations", "vus_max", "operations", "vu_cycles", "replica_requests"}
    require(set(value) == expected, "load-summary-fields-invalid")
    require(value["configured_duration_seconds"] == MINIMUM_LOAD_SECONDS
            and value["configured_vus"] == MINIMUM_LOAD_CONCURRENCY
            and value["cycle_seconds"] == CYCLE_SECONDS
            and value["vus_max"] == MINIMUM_LOAD_CONCURRENCY
            and number(value["measured_duration_ms"])
            and MINIMUM_LOAD_SECONDS * 1000 <= value["measured_duration_ms"] <= MAX_RUN_SECONDS * 1000,
            "load-duration-or-concurrency-invalid")
    for field in ("requests", "errors", "http_requests", "http_failures", "latency_samples", "cycles_started",
                  "cycles_completed", "checks_effects", "iterations"):
        require(counter(value[field]), "load-summary-counter-invalid")
    require(value["errors"] == 0 and value["http_failures"] == 0, "load-business-or-http-errors")
    require(number(value["p95_ms"]) and value["p95_ms"] <= MAXIMUM_P95_MS, "load-p95-threshold-exceeded")
    require(MINIMUM_LOAD_REQUESTS <= value["requests"] <= 50000
            and value["latency_samples"] == value["requests"] == value["http_requests"],
            "load-request-or-latency-coverage-invalid")
    require(value["cycles_completed"] >= MINIMUM_LOAD_CONCURRENCY
            and value["cycles_started"] == value["cycles_completed"] == value["iterations"]
            and value["checks_effects"] == value["cycles_completed"] * 2
            and number(value["checks_delivery_p95_ms"]), "load-business-cycles-incomplete")
    require(isinstance(value["vu_cycles"], dict)
            and set(value["vu_cycles"]) == {str(i) for i in range(1, MINIMUM_LOAD_CONCURRENCY + 1)}
            and all(counter(count) and 1 <= count <= 31 for count in value["vu_cycles"].values())
            and sum(value["vu_cycles"].values()) == value["cycles_completed"], "load-user-coverage-incomplete")
    require(isinstance(value["operations"], dict) and set(value["operations"]) == set(OPERATIONS),
            "load-operation-coverage-incomplete")
    for name, row in value["operations"].items():
        require(isinstance(row, dict) and set(row) == {"requests", "p95_ms", "latency_samples", "errors"}
                and counter(row["requests"]) and row["requests"] > 0 and number(row["p95_ms"])
                and row["latency_samples"] == row["requests"] and row["errors"] == 0, "load-operation-metrics-invalid")
        minimum = 5 * MINIMUM_LOAD_CONCURRENCY if name == "oauth" else value["cycles_completed"]
        if name == "transfer":
            minimum *= 2
        require(row["requests"] >= minimum, "load-operation-coverage-incomplete")
    require(sum(row["requests"] for row in value["operations"].values()) == value["requests"],
            "load-operation-counts-inconsistent")
    require(isinstance(value["replica_requests"], dict) and set(value["replica_requests"]) ==
            {f"{service}_{i}" for service in HTTP_SERVICES for i in range(2)}
            and all(counter(n) and n > 0 for n in value["replica_requests"].values())
            and sum(value["replica_requests"].values()) == value["requests"], "load-replica-coverage-incomplete")
    return {"tool": "k6", "requests": int(value["requests"]), "duration_seconds": MINIMUM_LOAD_SECONDS,
            "concurrency": MINIMUM_LOAD_CONCURRENCY, "errors": 0, "p95_ms": value["p95_ms"],
            "requests_per_second": value["requests"] / (value["measured_duration_ms"] / 1000)}


def execute_k6(root, configuration, *, executable="k6", timeout=MAX_RUN_SECONDS):
    """Feed credentials via a pipe; ignore user k6 outputs/config/proxy overrides."""
    text = (root / SCRIPT).read_text(encoding="utf-8")
    source = "const CONFIG = " + json.dumps(configuration, ensure_ascii=True) + ";\n" + text
    # Only executable/OS discovery variables enter the child. No evidence key,
    # cloud access tokens, K6_HTTP_DEBUG, exporters or arbitrary environment.
    allowed = {"PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "TMPDIR", "TMP", "TEMP"}
    env = {k: v for k, v in os.environ.items() if k.upper() in allowed}
    with tempfile.TemporaryDirectory(prefix="ms67-k6-private-") as directory:
        config_file = Path(directory) / "empty-config.json"
        config_file.write_text("{}\n", encoding="utf-8")
        env["XDG_CONFIG_HOME"] = directory
        argv = [executable, "run", "--quiet", "--no-color", "--log-output=none", "--no-usage-report",
                "--include-system-env-vars=false", "--traces-output=none", "--address=", "--config", str(config_file),
                "--new-machine-readable-summary=false", "-"]
        process = None
        try:
            process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                       text=True, encoding="utf-8", cwd=directory, env=env)
            stdout, _ = process.communicate(source, timeout=timeout)
            require(len(stdout) <= 128 * 1024, "load-summary-output-too-large")
            lines = [line for line in stdout.splitlines() if line.startswith(SUMMARY_PREFIX)]
            require(len(lines) == 1, "load-k6-summary-missing")
            result = json.loads(lines[0][len(SUMMARY_PREFIX):])
            require(isinstance(result, dict), "load-k6-summary-invalid")
            return process.returncode, result
        except subprocess.TimeoutExpired:
            raise JourneyFailure("load-k6-timeout") from None
        except (OSError, ValueError, UnicodeError):
            raise JourneyFailure("load-k6-command-or-summary-invalid") from None
        finally:
            if process and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


class PodForwards:
    """Own only local processes, with both exact ready pods of every HTTP service."""

    def __init__(self, runtime):
        self.runtime, self.processes, self.identities = runtime, [], {}

    def open(self):
        endpoints = {}
        for service in HTTP_SERVICES:
            self.runtime.service_ready(service)
            pods = sorted(self.runtime.pods(service), key=lambda p: p["metadata"]["uid"])
            require(len(pods) == 2, "load-two-ready-pods-required")
            self.identities[service] = {
                "pod_uid_sha256": [hashed(p["metadata"]["uid"]) for p in pods],
                "pod_identity_sha256": hashed(sorted(p["metadata"]["uid"] for p in pods)),
            }
            endpoints[service] = [self.forward(p["metadata"]["name"]) for p in pods]
        return endpoints

    def forward(self, name):
        require(re.fullmatch(r"[a-z0-9-]{1,253}", name), "load-pod-name-invalid")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        process = subprocess.Popen(["kubectl", "--context", self.runtime.context, "-n", self.runtime.namespace,
            "port-forward", "--address=127.0.0.1", "pod/" + name, f"{port}:8080"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.processes.append(process)
        deadline = time.monotonic() + 30
        while process.poll() is None and time.monotonic() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=1):
                    return f"http://127.0.0.1:{port}"
            except OSError:
                time.sleep(0.2)
        raise JourneyFailure("load-pod-port-forward-unavailable")

    def close(self):
        for process in self.processes:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


def verify_observation(value, key, *, bindings, images, environment, profile, root):
    require(value.get("content_sha256") == content_hash(value) and verify_signature(value, key),
            "load-observation-signature-invalid")
    require(value.get("observation_type") == OBSERVATION_TYPE and value.get("status") == PASS
            and value.get("k6_exit_code") == 0 and not any(field in value for field in ("reason", "evidence_upload")),
            "load-passing-observation-required")
    require(set(value) == {"schema_version", "observation_type", "status", "deployment_mutations",
            "synthetic_data_only", "credentials_persisted", "raw_output_persisted", "production_environment",
            "ms67_complete", "production_ready", "local_processes_stopped", "run_id", "started_at", "bindings",
            "images", "environment", "workload", "k6_version", "live", "deployment_specs", "model",
            "cluster_identity_sha256", "profile_namespace_uid_sha256", "phase", "fixtures", "http_pod_identities",
            "load_started_at", "k6_exit_code", "summary", "load_finished_at", "load", "finished_at",
            "content_sha256", "signature"} and value.get("schema_version") == "1.0" and value.get("phase") == "complete",
            "load-observation-fields-invalid")
    require(value.get("bindings") == bindings and value.get("images") == images
            and value.get("environment") == environment and value.get("workload") == workload(root),
            "load-observation-bindings-invalid")
    require(value.get("cluster_identity_sha256") == profile["cluster_uid_sha256"]
            and value.get("profile_namespace_uid_sha256") == profile["namespace_uid_sha256"],
            "load-observation-profile-identity-invalid")
    require(value.get("load") == validate_summary(value.get("summary"), value.get("run_id")), "load-metrics-mismatch")
    require(re.fullmatch(r"ms67-load-[a-z0-9-]{1,45}", value.get("run_id", ""))
            and re.fullmatch(r"k6 v2\.2\.0 .+", value.get("k6_version", "")), "load-tool-or-run-identity-invalid")
    try:
        moments = [datetime.fromisoformat(value[k].replace("Z", "+00:00")) for k in
                   ("started_at", "load_started_at", "load_finished_at", "finished_at")]
        require(all(m.tzinfo for m in moments) and moments == sorted(moments)
                and MINIMUM_LOAD_SECONDS <= (moments[2] - moments[1]).total_seconds() <= MAX_RUN_SECONDS,
                "load-observed-window-invalid")
    except (KeyError, TypeError, ValueError):
        raise JourneyFailure("load-observed-window-invalid") from None
    for phase in ("before", "after"):
        live, specs = value.get("live", {}).get(phase, {}), value.get("deployment_specs", {}).get(phase, {})
        require(set(live) == set(specs) == set(SERVICES)
                and all(row.get("image") == images[s] and row.get("ready_replicas") == 2
                        and re.fullmatch(HEX, row.get("pod_identity_sha256", "")) for s, row in live.items())
                and all(re.fullmatch(HEX, h) for h in specs.values()), "load-live-service-evidence-incomplete")
    require(value["deployment_specs"]["before"] == value["deployment_specs"]["after"]
            and all(value["live"]["before"][s]["pod_identity_sha256"] ==
                    value["live"]["after"][s]["pod_identity_sha256"] for s in SERVICES), "load-live-deployment-drift")
    identities = value.get("http_pod_identities", {})
    require(set(identities) == set(HTTP_SERVICES)
            and all(isinstance(row, dict) and set(row) == {"pod_uid_sha256", "pod_identity_sha256"}
                    and isinstance(row["pod_uid_sha256"], list)
                    and len(row["pod_uid_sha256"]) == len(set(row["pod_uid_sha256"])) == 2
                    and all(re.fullmatch(HEX, item) for item in row["pod_uid_sha256"])
                    and row["pod_identity_sha256"] == value["live"]["before"][service]["pod_identity_sha256"]
                    for service, row in identities.items()),
            "load-http-pod-identities-incomplete")
    model = value.get("model", {})
    before = model.get("before", {})
    require(before == model.get("after") and before.get("image") == profile["model_image"]
            and before.get("ready_replicas") == 2 and re.fullmatch(HEX, before.get("spec_sha256", "")),
            "load-model-evidence-invalid")
    fixtures = value.get("fixtures", {})
    require(set(fixtures) == {"account_count", "final_state_verified", "synthetic_records_retained",
                             "final_state_sha256", "identity_sha256"}
            and fixtures.get("account_count") == 3 * MINIMUM_LOAD_CONCURRENCY
            and fixtures.get("final_state_verified") is True
            and fixtures.get("synthetic_records_retained") is True
            and re.fullmatch(HEX, fixtures.get("final_state_sha256", ""))
            and re.fullmatch(HEX, fixtures.get("identity_sha256", "")), "load-fixture-state-unverified")
    require(value.get("credentials_persisted") is False and value.get("raw_output_persisted") is False
            and value.get("synthetic_data_only") is True and value.get("production_environment") is False
            and value.get("deployment_mutations") == 0 and value.get("ms67_complete") is False
            and value.get("production_ready") is False
            and value.get("local_processes_stopped") is True, "load-safety-or-cleanup-invalid")
