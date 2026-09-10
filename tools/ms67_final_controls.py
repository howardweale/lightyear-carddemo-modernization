#!/usr/bin/env python3
"""Read current MS67 runtime identities, metrics, TLS and secret synchronization."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import http.client
import json
from pathlib import Path
import socket
import ssl
import subprocess
import tempfile
import time
from urllib.parse import urlsplit
import warnings

from cloudbank_ms65_rehearsal import cluster_identity
from cloudbank_operational_baseline import GoogleReadClient, KubernetesReader, secret_sync
from lightyear_data.cloudbank_journeys import SERVICES, hashed, require
from lightyear_data.cloudbank_runtime_identity import container, pod_observation
from lightyear_data.cloudbank_ms67_drills import node_plan
from lightyear_data.cloudbank_sql_recovery import verified
from lightyear_data.contracts import sign
from lightyear_data.cloudbank_image_security import child_environment


def instant(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def tls(profile):
    host, url = profile["expected_hostname"], urlsplit(profile["ingress_url"])
    require(url.scheme == "https" and url.hostname == host and url.port in (None, 443)
            and not url.username and not url.password, "final-tls-host-invalid")
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    with socket.create_connection((host, 443), timeout=15) as conn:
        with context.wrap_socket(conn, server_hostname=host) as secure:
            cert, protocol = secure.getpeercert(), secure.version()
            digest = hashlib.sha256(secure.getpeercert(binary_form=True)).hexdigest()
    days = int((ssl.cert_time_to_seconds(cert["notAfter"]) - time.time()) // 86400)
    require(days >= 30 and protocol in {"TLSv1.2", "TLSv1.3"}, "final-tls-certificate-or-version-invalid")
    legacy = {}
    for name, version in (("TLSv1", ssl.TLSVersion.TLSv1), ("TLSv1.1", ssl.TLSVersion.TLSv1_1)):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            old = ssl.create_default_context()
            old.minimum_version = old.maximum_version = version
            old.set_ciphers("DEFAULT:@SECLEVEL=0")
        try:
            with socket.create_connection((host, 443), timeout=15) as conn:
                with old.wrap_socket(conn, server_hostname=host):
                    legacy[name] = False
        except ssl.SSLError as exc:
            legacy[name] = getattr(exc, "reason", "") == "TLSV1_ALERT_PROTOCOL_VERSION"
        require(legacy[name], "legacy-tls-rejection-not-proven-" + name)
    plain = http.client.HTTPConnection(host, 80, timeout=15)
    try:
        plain.request("GET", url.path or "/", headers={"Connection": "close"})
        response = plain.getresponse()
        location = urlsplit(response.getheader("Location", ""))
        rejected = response.status in (403, 426) or (response.status in (301, 302, 303, 307, 308)
            and location.scheme == "https" and location.hostname == host and location.port in (None, 443)
            and not location.username and not location.password)
        status = response.status
        response.close()
    finally:
        plain.close()
    require(rejected, "plaintext-rejection-not-proven")
    return {"summary": {"hostname": host, "trusted_chain": True, "san_match": True,
        "minimum_protocol": "TLSv1.2", "certificate_days_remaining": days, "plaintext_rejected": True},
        "certificate_sha256": digest, "legacy_protocols_rejected": legacy, "plaintext_status": status}


def metric_rows(data, expected, project, cluster, namespace, start, end):
    """Bind fresh samples to the current named pod's lifetime, not just a service label."""
    require(not data.get("nextPageToken"), "current-metrics-query-truncated")
    found = {}
    for series in data.get("timeSeries", []):
        resource = series.get("resource", {})
        labels = resource.get("labels", {})
        name = labels.get("pod_name")
        if name not in expected:
            continue
        wanted = expected[name]
        require(resource.get("type") == "k8s_container"
                and all(labels.get(k) == v for k, v in {"project_id": project, "cluster_name": cluster,
                    "namespace_name": namespace, "container_name": wanted["service"]}.items())
                and series.get("metric", {}).get("type") == "kubernetes.io/container/cpu/core_usage_time",
                "current-metric-resource-mismatch")
        points = [p for p in series.get("points", []) if max(start, instant(wanted["created_at"])) <=
                  instant(p["interval"]["endTime"]) <= end and any(k in p.get("value", {}) for k in ("doubleValue", "int64Value"))]
        if points:
            found[name] = {"service": wanted["service"], "pod_uid_sha256": wanted["pod_uid_sha256"],
                           "samples": len(points), "series_sha256": hashed(series),
                           "latest_sample": max(p["interval"]["endTime"] for p in points)}
    return found


def metrics(runtime, client, *, pause=time.sleep, clock=time.monotonic):
    expected = {p["metadata"]["name"]: {"service": service, "pod_uid_sha256": hashed(p["metadata"]["uid"]),
                "created_at": p["metadata"]["creationTimestamp"]} for service in SERVICES for p in runtime.pods(service)}
    require(len(expected) == 16, "current-metrics-sixteen-pods-required")
    deadline = clock() + 360
    while True:
        end = datetime.now(timezone.utc)
        start = end - timedelta(minutes=10)
        query = ('metric.type="kubernetes.io/container/cpu/core_usage_time" AND resource.type="k8s_container" '
                 f'AND resource.labels.cluster_name="{runtime.cluster}" AND resource.labels.namespace_name="{runtime.namespace}"')
        data = client.request("metrics", {"filter": query, "interval.startTime": start.isoformat(),
            "interval.endTime": end.isoformat(), "view": "FULL", "pageSize": 1000})
        found = metric_rows(data, expected, runtime.project, runtime.cluster, runtime.namespace, start, end)
        if set(found) == set(expected):
            current = {p["metadata"]["name"]: hashed(p["metadata"]["uid"]) for s in SERVICES for p in runtime.pods(s)}
            require(current == {n: r["pod_uid_sha256"] for n, r in expected.items()}, "pods-changed-during-metric-read")
            return {"services": list(SERVICES), "pods": found, "start": start.isoformat(), "end": end.isoformat(),
                    "scope": "GKE container CPU metrics for all sixteen current application pods; not JVM or business metrics"}
        require(clock() < deadline, "current-pod-metrics-not-observed")
        runtime.progress("MS67_FINAL_METRICS=waiting for current pod samples")
        pause(20)


def manifest_scan(deployments):
    # Transient manifests can contain non-secret configuration. They are removed
    # on every exit; scanner output is reduced to hashes and finding counts.
    with tempfile.TemporaryDirectory(prefix="ms67-manifest-") as directory:
        folder = Path(directory) / "manifests"
        folder.mkdir()
        config = Path(directory) / "trivy.yaml"
        config.write_text("{}\n")
        ignore = Path(directory) / "ignore"
        ignore.write_text("")
        for service, value in deployments.items():
            (folder / (service + ".json")).write_text(json.dumps(value))
        completed = subprocess.run(["trivy", "config", "--format", "json", "--exit-code", "0",
            "--config", str(config), "--ignorefile", str(ignore), "--include-non-failures",
            "--disable-telemetry", str(folder)], capture_output=True, timeout=300, check=False,
            cwd=directory, env=child_environment(Path(directory)))
        require(completed.returncode == 0 and len(completed.stdout) <= 16*1024*1024, "manifest-scanner-failed")
        report = json.loads(completed.stdout)
        rows = report.get("Results", [])
        require(report.get("SchemaVersion") == 2 and isinstance(rows, list) and len(rows) == 8,
                "manifest-eight-results-required")
        names = {Path(r.get("Target", "")).name for r in rows}
        require(names == {s + ".json" for s in SERVICES}, "manifest-scan-coverage-invalid")
        counts = {"high": 0, "critical": 0}
        for row in rows:
            require(row.get("Type") == "kubernetes" and row.get("MisconfSummary", {}).get("Successes", 0) > 0
                    and not row.get("MisconfSummary", {}).get("Exceptions")
                    and not row.get("ModifiedFindings"), "manifest-policy-coverage-or-exceptions-invalid")
            for finding in row.get("Misconfigurations") or []:
                require(finding.get("Status") in {"PASS", "FAIL"}, "manifest-check-status-invalid")
                level = finding.get("Severity", "").lower()
                if level in counts and finding["Status"] == "FAIL":
                    counts[level] += 1
        require(counts == {"high": 0, "critical": 0}, "manifest-high-or-critical-policy-finding")
        return {**counts, "scan_sha256": hashlib.sha256(completed.stdout).hexdigest(),
                "deployment_specs": {s: hashed(d["spec"]) for s, d in deployments.items()}}


def observe(runtime, context, key, signer):
    profile = context["profile"]
    environment = runtime.environment()
    uid = runtime.get("namespace", runtime.namespace)["metadata"]["uid"]
    require(environment == context["environment"] and profile["context"] == runtime.context
            and profile["cluster_uid_sha256"] == cluster_identity(runtime.project, runtime.region, runtime.cluster)
            and profile["namespace_uid_sha256"] == hashlib.sha256(uid.encode()).hexdigest(), "final-live-context-mismatch")
    nodes = runtime.get("nodes")["items"]
    node_plan(nodes)
    version = json.loads(runtime.kubectl("version", "-o", "json"))["serverVersion"]["gitVersion"]
    deployments, identities = {}, {}
    for service in SERVICES:
        runtime.progress("MS67_FINAL_CURRENT_RUNTIME=" + service)
        d = runtime.deployment(service)
        container(d, service, runtime.namespace, runtime.images[service])
        runtime.service_ready(service)
        identities[service] = pod_observation(runtime.pods(service), service, runtime.namespace,
                                             runtime.images[service], corrected=True)
        deployments[service] = {k: d[k] for k in ("apiVersion", "kind", "metadata", "spec")}
        deployments[service]["metadata"] = {"name": service, "namespace": runtime.namespace}
    scan = manifest_scan(deployments)
    sync = secret_sync(KubernetesReader(runtime.context), project=runtime.project, region=runtime.region,
                       cluster=runtime.cluster, namespace=runtime.namespace, store_name="cloudbank-gcp-secret-manager")
    require(sync["status"] == "observed", "final-secret-synchronization-incomplete")
    result = {"schema_version": "1.0", "observation_type": "lightyear-ms67-final-current-controls", "status": "passed",
        "bindings": context["bindings"], "images": runtime.images, "environment": environment,
        "observed_at": datetime.now(timezone.utc).isoformat(), "identities": identities, "manifest_scan": scan,
        "metrics": metrics(runtime, GoogleReadClient(runtime.project)), "secrets": sync, "tls": tls(profile),
        "cluster": {**{k: profile[k] for k in ("context", "cluster_uid_sha256", "namespace", "namespace_uid_sha256", "provider", "region")},
                    "kubernetes_version": version, "node_count": len(nodes),
                    "failure_domains": sorted({n["metadata"]["labels"]["topology.kubernetes.io/zone"] for n in nodes})},
        "credentials_persisted": False, "ms67_complete": False}
    return sign(result, key, signer)


def verify_result(value, context, key):
    verified(value, key)
    require(value.get("observation_type") == "lightyear-ms67-final-current-controls" and value.get("status") == "passed"
            and all(value.get(k) == context[k] for k in ("bindings", "images", "environment"))
            and value.get("credentials_persisted") is False, "current-controls-context-invalid")
    require(set(value.get("identities", {})) == set(SERVICES) and value.get("secrets", {}).get("status") == "observed",
            "current-controls-eight-identities-and-secret-sync-required")
    for service, row in value["identities"].items():
        require(row.get("image") == context["images"][service] and row.get("ready_replicas") == 2
                and row.get("startup_uids") == row.get("startup_gids") == [65532, 65532], "current-runtime-policy-invalid")
    require(len(value.get("metrics", {}).get("pods", {})) == 16
            and value["metrics"].get("services") == list(SERVICES)
            and all(value["manifest_scan"].get(k) == 0 for k in ("critical", "high")), "current-metrics-or-manifest-invalid")
    return value
