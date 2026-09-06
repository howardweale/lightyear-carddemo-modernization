#!/usr/bin/env python3
"""Collect a bounded, read-only MS67 secret-sync and telemetry baseline.

This observer reads Kubernetes status and Google telemetry metadata. It never
reads Kubernetes Secret values, log bodies, or trace payloads, and it cannot
declare MS65, MS66, or MS67 complete.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener


SERVICES = ("azn-server", "customer", "account", "transfer", "checks",
            "testrunner", "creditscore", "chatbot")
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
OBSERVER_VERSION = "1.0"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def stamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def digest(value) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


class ObservationError(Exception):
    def __init__(self, reason: str, code: int | None = None, api_error: dict | None = None):
        super().__init__(reason)
        self.reason = reason
        self.code = code
        self.api_error = api_error or {}


def error_record(exc: Exception) -> dict:
    result = {"status": "inconclusive", "error_type": type(exc).__name__}
    if isinstance(exc, ObservationError):
        result.update(reason=exc.reason, code=exc.code)
        if exc.api_error:
            result["api_error"] = exc.api_error
    return result


def safe_api_error(raw: bytes) -> dict:
    """Retain structured Google error identifiers while excluding free text."""
    try:
        if len(raw) > 65536:
            return {}
        error = json.loads(raw).get("error", {})
        result = {}
        status = error.get("status")
        if isinstance(status, str) and re.fullmatch(r"[A-Z_]{1,64}", status):
            result["status"] = status
        details = []
        for item in error.get("details", []):
            if item.get("@type") != "type.googleapis.com/google.rpc.ErrorInfo":
                continue
            safe = {}
            for key, pattern in {"reason": r"[A-Z_]{1,80}",
                                 "domain": r"[a-z0-9.-]{1,120}"}.items():
                value = item.get(key)
                if isinstance(value, str) and re.fullmatch(pattern, value):
                    safe[key] = value
            metadata = {}
            for key, pattern in {
                "service": r"[a-z0-9.-]{1,160}\.googleapis\.com",
                "consumer": r"projects/[a-z0-9-]{1,80}",
                "permission": r"[a-zA-Z0-9_.]{1,160}",
            }.items():
                value = item.get("metadata", {}).get(key)
                if isinstance(value, str) and re.fullmatch(pattern, value):
                    metadata[key] = value
            if metadata:
                safe["metadata"] = metadata
            if safe:
                details.append(safe)
        if details:
            result["error_info"] = details[:4]
        return result
    except (ValueError, TypeError, AttributeError):
        return {}


def command(args: list[str], timeout: int = 60) -> str:
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    if result.returncode:
        raise ObservationError("command-failed", result.returncode)
    return result.stdout


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class GoogleReadClient:
    def __init__(self, project: str, timeout_seconds: int = 600):
        self.project = project
        self.endpoints = {
            "descriptors": f"https://monitoring.googleapis.com/v3/projects/{project}/metricDescriptors",
            "metrics": f"https://monitoring.googleapis.com/v3/projects/{project}/timeSeries",
            "logs": "https://logging.googleapis.com/v2/entries:list",
            "traces": f"https://cloudtrace.googleapis.com/v1/projects/{project}/traces",
        }
        self.token = command(["gcloud", "auth", "print-access-token", "--project", project]).strip()
        if not self.token or any(character.isspace() for character in self.token):
            raise ObservationError("access-token-unavailable")
        self.opener = build_opener(NoRedirect())
        self.deadline = time.monotonic() + timeout_seconds

    def request(self, endpoint: str, params: dict, body: dict | None = None) -> dict:
        if endpoint not in self.endpoints:
            raise ObservationError("unexpected-google-api-endpoint")
        if time.monotonic() >= self.deadline:
            raise ObservationError("telemetry-query-time-budget-exhausted")
        url = self.endpoints[endpoint] + "?" + urlencode(params)
        payload = json.dumps(body).encode() if body is not None else None
        request = Request(url, data=payload, headers={
            "Authorization": f"Bearer {self.token}",
            "x-goog-user-project": self.project,
            "Content-Type": "application/json",
        })
        try:
            with self.opener.open(request, timeout=20) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise ObservationError("api-response-size-limit")
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ObservationError("unexpected-api-response")
            return result
        except HTTPError as exc:
            code = exc.code
            try:
                detail = safe_api_error(exc.read(65537))
            except (OSError, ValueError):
                detail = {}
            finally:
                exc.close()
            raise ObservationError("google-api-http-error", code, detail) from None
        except (URLError, TimeoutError):
            raise ObservationError("google-api-network-error") from None


class KubernetesReader:
    ALLOWED = {
        "deployments", "daemonsets", "secretstores.external-secrets.io",
        "externalsecrets.external-secrets.io",
    }

    def __init__(self, context: str):
        self.context = context

    def get(self, kind: str, namespace: str, name: str | None = None) -> dict:
        if kind not in self.ALLOWED:
            raise ObservationError("unexpected-kubernetes-resource")
        args = ["kubectl", "--context", self.context, "--request-timeout=30s",
                "-n", namespace, "get", kind]
        if name:
            args.append(name)
        return json.loads(command(args + ["-o", "json"]))


def ready_condition(resource: dict) -> bool:
    generation = resource.get("metadata", {}).get("generation")
    for condition in resource.get("status", {}).get("conditions", []):
        if condition.get("type") == "Ready":
            observed = condition.get("observedGeneration")
            return condition.get("status") == "True" and (observed is None or observed == generation)
    return False


def deployment_summary(resource: dict) -> dict:
    metadata = resource.get("metadata", {})
    spec = resource.get("spec", {})
    status = resource.get("status", {})
    desired = spec.get("replicas", 1)
    ready = status.get("readyReplicas", 0)
    updated = status.get("updatedReplicas", 0)
    available = status.get("availableReplicas", 0)
    current = status.get("observedGeneration", -1) >= metadata.get("generation", 0)
    passed = desired > 0 and current and min(ready, updated, available) >= desired
    return {"desired": desired, "ready": ready, "updated": updated,
            "available": available, "current_generation": current,
            "status": "ready" if passed else "not-ready"}


def secret_sync(reader: KubernetesReader, *, project: str, region: str,
                cluster: str, namespace: str, store_name: str) -> dict:
    controller = deployment_summary(reader.get("deployments", "external-secrets", "external-secrets"))
    store = reader.get("secretstores.external-secrets.io", namespace, store_name)
    provider = store.get("spec", {}).get("provider", {}).get("gcpsm", {})
    identity = provider.get("auth", {}).get("workloadIdentity", {})
    store_matches = (
        provider.get("projectID") == project
        and identity.get("clusterProjectID") == project
        and identity.get("clusterName") == cluster
        and identity.get("clusterLocation") == region
        and identity.get("serviceAccountRef", {}).get("name") == "cloudbank-secret-reader"
    )
    resources = reader.get("externalsecrets.external-secrets.io", namespace).get("items", [])
    indexed = {item.get("metadata", {}).get("name"): item for item in resources}
    rows = {}
    current = utc_now()
    for service in SERVICES:
        resource = indexed.get(f"cloudbank-{service}", {})
        spec = resource.get("spec", {})
        refreshed = resource.get("status", {}).get("refreshTime")
        age = None
        try:
            age = round((current - datetime.fromisoformat(refreshed.replace("Z", "+00:00"))).total_seconds())
        except (TypeError, ValueError, AttributeError):
            pass
        ready = ready_condition(resource)
        fresh = age is not None and -60 <= age <= 300
        target_matches = spec.get("target", {}).get("name") == f"cloudbank-{service}-external"
        reference_matches = spec.get("secretStoreRef") == {"name": store_name, "kind": "SecretStore"}
        synced = ready and fresh and target_matches and reference_matches
        rows[service] = {"status": "synced" if synced else "not-observed",
                         "ready_condition": ready, "refresh_age_seconds": age,
                         "refresh_within_tolerance": fresh,
                         "target_matches": target_matches,
                         "store_reference_matches": reference_matches}
    passed = (controller["status"] == "ready" and ready_condition(store) and store_matches
              and all(row["status"] == "synced" for row in rows.values()))
    return {"status": "observed" if passed else "incomplete", "controller": controller,
            "store_ready": ready_condition(store), "store_identity_matches": store_matches,
            "store_reference_sha256": digest({"name": store_name, "namespace": namespace,
                                               "spec": store.get("spec", {})}),
            "services": rows, "rotation_observed": False, "secret_values_read": False}


def metric_service(series: dict) -> str | None:
    metric = series.get("metric", {})
    labels = metric.get("labels", {})
    service = labels.get("service_name") or labels.get("service.name")
    if not str(metric.get("type", "")).startswith("workload.googleapis.com/"):
        return None
    return service if service in SERVICES else None


def metrics_probe(client: GoogleReadClient, start: str, end: str) -> dict:
    params = {"filter": 'metric.type = starts_with("workload.googleapis.com/")',
              "activeOnly": "true", "pageSize": 1000,
              "fields": "metricDescriptors(type),nextPageToken"}
    types = set()
    for _ in range(3):
        data = client.request("descriptors", params)
        types.update(item["type"] for item in data.get("metricDescriptors", []) if "type" in item)
        token = data.get("nextPageToken")
        if not token:
            break
        params["pageToken"] = token
    candidates = sorted(
        metric_type for metric_type in types
        if re.search(r"/(?:jvm|process[./]runtime[./]jvm)[./]", metric_type)
    )
    candidates.sort(key=lambda value: (0 if "uptime" in value else 1 if "thread" in value else 2, value))
    rows = {}
    queried = []
    for metric_type in candidates[:6]:
        query = {"filter": f'metric.type = "{metric_type}"', "view": "HEADERS",
                 "interval.startTime": start, "interval.endTime": end, "pageSize": 1000,
                 "fields": "timeSeries(metric,resource),nextPageToken,executionErrors"}
        queried.append(metric_type)
        for _ in range(3):
            data = client.request("metrics", query)
            if data.get("executionErrors"):
                raise ObservationError("monitoring-partial-query-error")
            for series in data.get("timeSeries", []):
                service = metric_service(series)
                if service and service not in rows:
                    rows[service] = {"status": "observed", "metric_type": metric_type,
                                     "series_identity_sha256": digest(series),
                                     "resource_type": series.get("resource", {}).get("type")}
            token = data.get("nextPageToken")
            if len(rows) == len(SERVICES) or not token:
                break
            query["pageToken"] = token
        if len(rows) == len(SERVICES):
            break
    return {"status": "observed" if len(rows) == len(SERVICES) else "incomplete",
            "scope": "project-and-service-name; deployment-identity-not-proven",
            "services": {service: rows.get(service, {"status": "not-observed"})
                         for service in SERVICES},
            "queried_metric_types": queried,
            "stopped_after_full_service_coverage": len(rows) == len(SERVICES),
            "absence_is_not_export_failure": True}


def log_probe(client: GoogleReadClient, service: str, start: str, end: str,
              *, project: str, cluster: str, namespace: str) -> dict:
    expected = {"project_id": project, "cluster_name": cluster,
                "namespace_name": namespace, "container_name": service}
    clauses = [f'resource.labels.{key}="{value}"' for key, value in expected.items()]
    query = 'resource.type="k8s_container" AND ' + " AND ".join(clauses)
    query += f' AND timestamp>="{start}" AND timestamp<="{end}"'
    body = {"resourceNames": [f"projects/{project}"], "filter": query,
            "orderBy": "timestamp desc", "pageSize": 1}
    data = client.request("logs", {"fields": "entries(timestamp,insertId,resource),nextPageToken"}, body)
    entries = data.get("entries", [])
    if not entries:
        return {"status": "not-observed", "search_complete": not bool(data.get("nextPageToken"))}
    entry = entries[0]
    labels = entry.get("resource", {}).get("labels", {})
    if entry.get("resource", {}).get("type") != "k8s_container" or any(
            labels.get(key) != value for key, value in expected.items()):
        raise ObservationError("log-resource-identity-mismatch")
    return {"status": "observed", "timestamp": entry.get("timestamp"),
            "entry_identity_sha256": digest(entry)}


def trace_rows(client: GoogleReadClient, start: str, end: str) -> tuple[dict, bool]:
    params = {"startTime": start, "endTime": end, "view": "COMPLETE",
              "pageSize": 100, "orderBy": "start desc",
              "fields": "traces(traceId,spans(labels)),nextPageToken"}
    rows = {}
    search_complete = False
    for _ in range(3):
        data = client.request("traces", params)
        for trace in data.get("traces", []):
            trace_id = trace.get("traceId", "")
            if not re.fullmatch(r"[a-fA-F0-9]{32}", trace_id):
                raise ObservationError("unexpected-trace-identity")
            names = {
                str((span.get("labels") or {}).get("service.name", ""))
                for span in trace.get("spans", []) if isinstance(span, dict)
            } & set(SERVICES)
            for service in names:
                rows.setdefault(service, {"status": "observed",
                    "matched_attribute": "service.name",
                    "trace_identity_sha256": digest({"project": client.project,
                                                     "trace_id": trace_id,
                                                     "service": service})})
        if len(rows) == len(SERVICES):
            break
        token = data.get("nextPageToken")
        if not token:
            search_complete = True
            break
        params["pageToken"] = token
    return rows, search_complete


def service_logs(client, start: str, end: str, *, project: str,
                 cluster: str, namespace: str) -> dict:
    rows = {}
    for service in SERVICES:
        try:
            rows[service] = log_probe(client, service, start, end, project=project,
                                      cluster=cluster, namespace=namespace)
        except Exception as exc:
            rows[service] = error_record(exc)
            if isinstance(exc, ObservationError) and exc.code in {401, 403}:
                for remaining in SERVICES:
                    rows.setdefault(remaining, {"status": "inconclusive",
                                                "reason": "backend-access-unavailable"})
                break
    return {"status": "observed" if all(row["status"] == "observed" for row in rows.values())
            else "incomplete", "services": rows,
            "scope": "project-cluster-namespace-container; current-pod-not-proven",
            "absence_is_not_export_failure": True}


def service_traces(client, start: str, end: str) -> dict:
    try:
        observed, search_complete = trace_rows(client, start, end)
        rows = {service: observed.get(service, {"status": "not-observed",
                                                "search_complete": search_complete})
                for service in SERVICES}
    except Exception as exc:
        first = SERVICES[0]
        rows = {first: error_record(exc)}
        for service in SERVICES[1:]:
            rows[service] = {"status": "inconclusive", "reason": "backend-access-unavailable"}
    return {"status": "observed" if all(row["status"] == "observed" for row in rows.values())
            else "incomplete", "services": rows,
            "scope": "project-and-service-name; deployment-identity-not-proven",
            "absence_is_not_export_failure": True}


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--project", default=os.environ.get("GCP_PROJECT_ID", ""))
    root.add_argument("--region", default=os.environ.get("GCP_REGION", ""))
    root.add_argument("--cluster", default=os.environ.get("GKE_CLUSTER_NAME", ""))
    root.add_argument("--namespace", default=os.environ.get(
        "GKE_NAMESPACE", os.environ.get("KUBERNETES_NAMESPACE", "cloudbank-ms67")))
    root.add_argument("--secret-store", default="cloudbank-gcp-secret-manager")
    root.add_argument("--lookback-minutes", type=int, default=30)
    root.add_argument("--evidence-bucket", required=True)
    root.add_argument("--output-root", type=Path)
    return root


def validate_args(args) -> None:
    if not args.project or not args.region or not args.cluster:
        raise ObservationError("explicit-gcp-context-required")
    if not 5 <= args.lookback_minutes <= 1440:
        raise ObservationError("lookback-minutes-out-of-range")
    if not args.evidence_bucket.startswith("gs://") or any(character.isspace()
                                                            for character in args.evidence_bucket):
        raise ObservationError("private-evidence-prefix-required")
    label = command(["gcloud", "projects", "describe", args.project,
                     "--format=value(labels.environment)"]).strip()
    if label != "non-production":
        raise ObservationError("non-production-project-label-required")


def output_root(candidate: Path | None) -> Path:
    if candidate:
        root = candidate.resolve()
        if root.exists():
            raise ObservationError("fresh-output-directory-required")
        root.mkdir(parents=True, mode=0o700)
        return root
    parent = Path.home() / "ms67-evidence"
    parent.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="ms67-operations.", dir=parent))


def write_evidence(root: Path, observation: dict) -> tuple[Path, Path]:
    path = root / "operational-baseline.observation.json"
    path.write_text(json.dumps(observation, indent=2, sort_keys=True) + "\n")
    path.chmod(0o600)
    sums = root / "SHA256SUMS"
    sums.write_text(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n")
    sums.chmod(0o600)
    return path, sums


def main(argv=None) -> int:
    os.umask(0o077)
    args = parser().parse_args(argv)
    root = None
    observation = {"status": "incomplete"}
    uploaded = False
    try:
        missing = [tool for tool in ("gcloud", "kubectl") if shutil.which(tool) is None]
        if missing:
            raise ObservationError("required-tools-missing")
        validate_args(args)
        root = output_root(args.output_root)
        context = f"gke_{args.project}_{args.region}_{args.cluster}"
        end = utc_now()
        start_text = stamp(end - timedelta(minutes=args.lookback_minutes))
        end_text = stamp(end)
        observation = {
            "schema_version": "1.0",
            "observation_type": "lightyear-cloudbank-ms67-operational-baseline",
            "observer_version": OBSERVER_VERSION,
            "observer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "project": args.project,
            "region": args.region,
            "cluster": args.cluster,
            "namespace": args.namespace,
            "query_window": {"start": start_text, "end": end_text,
                             "lookback_minutes": args.lookback_minutes},
            "status": "incomplete",
            "credentials_persisted": False,
            "secret_values_read": False,
            "raw_payloads_persisted": False,
            "qualification_complete": False,
            "not_exercised": ["secret-rotation", "telemetry-correlation",
                              "alert-fire-and-recovery", "load", "rolling-deployment",
                              "cutover-and-rollback", "receipt-signature-validation"],
        }
        reader = KubernetesReader(context)
        try:
            observation["secret_sync"] = secret_sync(
                reader, project=args.project, region=args.region, cluster=args.cluster,
                namespace=args.namespace, store_name=args.secret_store)
        except Exception as exc:
            observation["secret_sync"] = error_record(exc)
        try:
            observation["collector"] = deployment_summary(
                reader.get("deployments", "observability", "otel-collector"))
        except Exception as exc:
            observation["collector"] = error_record(exc)
        client = GoogleReadClient(args.project)
        try:
            observation["metrics"] = metrics_probe(client, start_text, end_text)
        except Exception as exc:
            observation["metrics"] = error_record(exc)
        observation["logs"] = service_logs(client, start_text, end_text,
                                           project=args.project, cluster=args.cluster,
                                           namespace=args.namespace)
        observation["traces"] = service_traces(client, start_text, end_text)
        if (all(observation.get(key, {}).get("status") == "observed"
                for key in ("secret_sync", "metrics", "logs", "traces"))
                and observation.get("collector", {}).get("status") == "ready"):
            observation["status"] = "observed-all-baseline-signals"
    except (Exception, KeyboardInterrupt) as exc:
        observation["collection_error"] = error_record(exc)
    finally:
        if root:
            observation["finished_at"] = stamp(utc_now())
            path, sums = write_evidence(root, observation)
            destination = args.evidence_bucket.rstrip("/") + "/" + root.name + "/"
            try:
                command(["gcloud", "storage", "cp", str(path), str(sums), destination,
                         "--project", args.project], timeout=180)
                uploaded = True
                print("MS67_OPERATIONS_BUCKET=" + destination, flush=True)
            except Exception:
                print("MS67_OPERATIONS_EVIDENCE_UPLOAD=FAILED; local evidence retained", flush=True)
    for name in ("secret_sync", "metrics", "logs", "traces"):
        rows = observation.get(name, {}).get("services", {})
        count = sum(row.get("status") in {"synced", "observed"} for row in rows.values())
        print(f"MS67_{name.upper()}_OBSERVED={count}/8", flush=True)
    if root:
        print("MS67_OPERATIONS_ROOT=" + str(root), flush=True)
    print("MS67_OPERATIONS_EVIDENCE_UPLOAD=" + ("PASSED" if uploaded else "FAILED"), flush=True)
    print("MS67_OPERATIONS_BASELINE=" + observation.get("status", "incomplete").upper(), flush=True)
    print("Read-only baseline only; full MS65/MS66/MS67 qualification remains open.", flush=True)
    return 0 if observation.get("status") == "observed-all-baseline-signals" and uploaded else 1


if __name__ == "__main__":
    raise SystemExit(main())
