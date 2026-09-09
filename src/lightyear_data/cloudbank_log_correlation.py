"""Install bounded request logging and match real GKE logs to exported spans.

The application image is unchanged. A persistent Logback configuration emits
only a fixed request event and agent-supplied IDs. Readiness probes share a client
trace context; this does not claim a causal eight-service business transaction.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener

from .cloudbank_journeys import JourneyFailure, SERVICES, hashed, require
from .cloudbank_journeys_gke import NoRedirect, command
from .contracts import content_hash, verify_signature


STATE_TYPE = "lightyear-cloudbank-ms67-log-correlation-recovery"
OBSERVATION_TYPE = "lightyear-cloudbank-ms67-log-correlation-observation"
STATE_FILE = "log-correlation.recovery.json"
OBSERVATION_FILE = "log-correlation.observation.json"
LEASE = "ly-ms67-request-logging"
MANAGER = "lightyear-request-logging"
VOLUME = "lightyear-request-logging"
MOUNT = "/etc/lightyear/request-logging"
ENV = {"name": "LOGGING_CONFIG", "value": MOUNT + "/logback-spring.xml"}
HEX64 = r"[0-9a-f]{64}"


def stamp():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def configuration(project: str) -> str:
    require(re.fullmatch(r"[a-z][a-z0-9-]{4,61}[a-z0-9]", project), "logging-project-invalid")
    path = Path(__file__).resolve().parents[2] / "factory/cloudbank/platform-qualification/gke/logback-correlation.xml"
    return path.read_text(encoding="utf-8").replace("{{PROJECT_ID}}", project)


def config_name(project):
    return "cloudbank-request-logging-" + hashlib.sha256(configuration(project).encode()).hexdigest()[:12]


def config_object(project, namespace, run_id=None):
    value = {"apiVersion": "v1", "kind": "ConfigMap", "immutable": True,
             "metadata": {"name": config_name(project), "namespace": namespace,
                          "labels": {"app.kubernetes.io/managed-by": MANAGER}},
             "data": {"logback-spring.xml": configuration(project)}}
    if run_id:
        value["metadata"]["annotations"] = {"lightyear.ai/logging-run": run_id}
    return value


def controlled(project):
    return ENV, {"name": VOLUME, "mountPath": MOUNT, "readOnly": True}, {
        "name": VOLUME, "configMap": {"name": config_name(project), "defaultMode": 292}}


def container_index(spec, service):
    matches = [i for i, c in enumerate(spec["template"]["spec"]["containers"]) if c["name"] == service]
    require(len(matches) == 1, "logging-service-container-invalid")
    return matches[0]


def locations(spec, service):
    i = container_index(spec, service)
    pod = spec["template"]["spec"]
    c = pod["containers"][i]
    base = f"/spec/template/spec/containers/{i}/"
    return [(c, "env", base + "env"), (c, "volumeMounts", base + "volumeMounts"),
            (pod, "volumes", "/spec/template/spec/volumes")]


def logging_settings(spec, service, project=None):
    require(spec.get("replicas") == 2 and spec.get("strategy") == {
        "type": "RollingUpdate", "rollingUpdate": {"maxUnavailable": 0, "maxSurge": 1}},
        "logging-two-replica-rolling-strategy-required")
    fields = locations(spec, service)
    expected_fields = controlled(project or "example-project")
    already_installed = project is not None and all(
        [row for row in parent.get(key, []) if row.get("name") == expected["name"]] == [expected]
        for (parent, key, _), expected in zip(fields, expected_fields))
    for (parent, key, _), expected in zip(fields, expected_fields):
        if already_installed:
            continue
        require(not any(row.get("name") == expected["name"] or
                        (key == "volumeMounts" and row.get("mountPath", "").startswith(MOUNT))
                        for row in parent.get(key, [])), "logging-existing-configuration-conflict")
    return fields, already_installed


def baseline(deployment, service, project=None):
    spec = deployment["spec"]
    fields, already_installed = logging_settings(spec, service, project)
    require(bool(deployment.get("metadata", {}).get("uid")), "logging-live-deployment-uid-required")
    return {"uid": deployment["metadata"]["uid"], "spec_sha256": hashed(spec),
            "logging_preexisting": already_installed,
            "absent_lists": [path for parent, key, path in fields if key not in parent]}


def normalized(spec, service, project, recorded):
    if recorded.get("logging_preexisting"):
        require(hashed(spec) == recorded["spec_sha256"], "logging-deployment-spec-drift")
        require(all([row for row in parent.get(key, []) if row.get("name") == expected["name"]] == [expected]
                    for (parent, key, _), expected in zip(locations(spec, service), controlled(project))),
                "logging-preexisting-configuration-drift")
        return True
    value = copy.deepcopy(spec)
    present = []
    for (parent, key, path), expected in zip(locations(value, service), controlled(project)):
        rows = parent.get(key, [])
        matches = [row for row in rows if row.get("name") == expected["name"]]
        require(not matches or matches == [expected], "logging-owned-field-drift")
        present.append(bool(matches))
        parent[key] = [row for row in rows if row.get("name") != expected["name"]]
        if not parent[key] and path in recorded["absent_lists"]:
            parent.pop(key)
    require(all(present) or not any(present), "logging-partial-deployment-configuration")
    require(hashed(value) == recorded["spec_sha256"], "logging-deployment-spec-drift")
    return all(present)


def deployment_patch(deployment, service, project, recorded, *, install):
    require(deployment["metadata"]["uid"] == recorded["uid"], "logging-deployment-uid-drift")
    install = install or recorded.get("logging_preexisting", False)
    active = normalized(deployment["spec"], service, project, recorded)
    if active == install:
        return []
    result = [{"op": "test", "path": "/metadata/uid", "value": recorded["uid"]},
              {"op": "test", "path": "/metadata/resourceVersion", "value": deployment["metadata"]["resourceVersion"]}]
    for (parent, key, path), expected in zip(locations(deployment["spec"], service), controlled(project)):
        if install:
            result.append({"op": "add", "path": path + "/-" if key in parent else path,
                           "value": expected if key in parent else [expected]})
        elif path in recorded["absent_lists"]:
            result.append({"op": "remove", "path": path})
        else:
            index = next(i for i, row in enumerate(parent[key]) if row["name"] == expected["name"])
            result.append({"op": "remove", "path": path + "/" + str(index)})
    return result


def instrument_bundle(bundle, project, namespace):
    """Apply the same configuration to a freshly rendered deployment bundle."""
    result = copy.deepcopy(bundle)
    require(result.get("kind") == "List", "logging-kubernetes-list-required")
    seen = set()
    for item in result["items"]:
        name = item.get("metadata", {}).get("name")
        if item.get("kind") != "Deployment" or name not in SERVICES:
            continue
        require(item["metadata"].get("namespace") == namespace and name not in seen,
                "logging-bundle-context-invalid")
        # Fresh client-side manifests have no server-assigned UID yet.
        logging_settings(item["spec"], name)
        for (parent, key, _), expected in zip(locations(item["spec"], name), controlled(project)):
            parent.setdefault(key, []).append(copy.deepcopy(expected))
        seen.add(name)
    require(seen == set(SERVICES), "logging-eight-deployments-required")
    result["items"].insert(0, config_object(project, namespace))
    return result


class Telemetry:
    def __init__(self, project, invoke=command):
        self.project, self.invoke = project, invoke
        self.opener = build_opener(NoRedirect())

    def request(self, url, *, body=None, missing=False):
        token = self.invoke(["gcloud", "auth", "print-access-token", "--project", self.project]).strip()
        require(bool(token), "logging-api-token-unavailable")
        request = Request(url, data=None if body is None else json.dumps(body).encode(),
                          headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
        try:
            with self.opener.open(request, timeout=45) as response:
                raw = response.read(4 * 1024 * 1024 + 1)
                require(len(raw) <= 4 * 1024 * 1024, "logging-api-response-too-large")
                return json.loads(raw)
        except HTTPError as exc:
            if missing and exc.code == 404:
                return {}
            raise JourneyFailure("logging-api-http-" + str(exc.code)) from None
        except (URLError, OSError, ValueError):
            raise JourneyFailure("logging-api-transport-or-json-invalid") from None

    def trace(self, trace_id):
        return self.request(f"https://cloudtrace.googleapis.com/v1/projects/{self.project}/traces/{trace_id}?" +
                            urlencode({"fields": "projectId,traceId,spans(spanId,startTime,endTime,labels)"}), missing=True)

    def logs(self, environment, trace_id, start, end):
        # The fixed event makes this a bounded query without fetching messages,
        # bodies, query strings, or unrelated application output.
        clauses = [f'resource.type="k8s_container"', f'resource.labels.project_id="{self.project}"',
                   f'resource.labels.cluster_name="{environment["cluster"]}"',
                   f'resource.labels.namespace_name="{environment["namespace"]}"',
                   f'timestamp>="{start}"', f'timestamp<="{end}"',
                   f'jsonPayload.event="cloudbank-request-context"', f'SEARCH("{trace_id}")']
        body = {"resourceNames": ["projects/" + self.project], "filter": " AND ".join(clauses), "pageSize": 200}
        rows = []
        url = "https://logging.googleapis.com/v2/entries:list?" + urlencode({
            "fields": "entries(timestamp,insertId,resource,trace,spanId),nextPageToken"})
        for _ in range(5):
            value = self.request(url, body=body)
            rows.extend(value.get("entries", []))
            token = value.get("nextPageToken")
            if not token:
                return rows, True
            body["pageToken"] = token
        return rows, False


def correlate(trace, logs, *, project, environment, trace_id, pods, start, end):
    result = {}
    if not trace:
        return result
    require(trace.get("projectId") == project and trace.get("traceId") == trace_id, "logging-trace-identity-mismatch")
    spans = {}
    for span in trace.get("spans", []):
        raw = str(span.get("spanId", ""))
        # Cloud Trace v1 uses an unsigned decimal span ID; Cloud Logging uses hex.
        if not raw.isdigit() or not 0 < int(raw) < 2 ** 64:
            continue
        service = span.get("labels", {}).get("service.name")
        spans[(service, format(int(raw), "016x"))] = span
    lower, upper = datetime.fromisoformat(start.replace("Z", "+00:00")), datetime.fromisoformat(end.replace("Z", "+00:00"))
    for log in logs:
        resource = log.get("resource", {})
        labels = resource.get("labels", {})
        service, span_id = labels.get("container_name"), log.get("spanId", "")
        span = spans.get((service, span_id))
        if service not in SERVICES or not span or not re.fullmatch(r"[0-9a-f]{16}", span_id):
            continue
        if not (resource.get("type") == "k8s_container" and labels.get("project_id") == project
                and labels.get("cluster_name") == environment["cluster"]
                and labels.get("namespace_name") == environment["namespace"]
                and labels.get("pod_name") in pods[service]
                and log.get("trace") in {trace_id, f"projects/{project}/traces/{trace_id}"}):
            continue
        try:
            logged = datetime.fromisoformat(log["timestamp"].replace("Z", "+00:00"))
            began = datetime.fromisoformat(span["startTime"].replace("Z", "+00:00"))
            ended = datetime.fromisoformat(span["endTime"].replace("Z", "+00:00"))
        except (KeyError, ValueError, TypeError):
            continue
        if not (lower <= began <= logged <= ended <= upper):
            continue
        result[service] = {"trace_identity_sha256": hashed(trace_id), "span_identity_sha256": hashed(span_id),
                           "log_identity_sha256": hashed(log), "pod_identity_sha256": hashed(pods[service][labels["pod_name"]]),
                           "log_timestamp": log["timestamp"], "span_start": span["startTime"], "span_end": span["endTime"]}
    return result


def verify_observation(value, key):
    require(value.get("content_sha256") == content_hash(value) and verify_signature(value, key),
            "logging-observation-signature-invalid")
    require(value.get("observation_type") == OBSERVATION_TYPE and value.get("status") == "passed-service-log-trace-correlation"
            and value.get("service_correlation_qualified") is True and value.get("configuration_retained") is True,
            "logging-passing-observation-required")
    require(value.get("ms67_complete") is False and value.get("production_ready") is False
            and value.get("credentials_persisted") is False and value.get("raw_output_persisted") is False
            and value.get("production_environment") is False and value.get("business_journey_qualified") is False
            and value.get("scope") == "eight-service-readiness-probes-with-common-client-trace-context",
            "logging-observation-claim-invalid")
    require(set(value.get("services", {})) == set(SERVICES) and set(value.get("images", {})) == set(SERVICES)
            and set(value.get("bindings", {})) == {"image_lock_sha256", "ms64_receipt_sha256", "platform_profile_sha256"},
            "logging-observation-bindings-invalid")
    require(value.get("configuration_sha256") == hashlib.sha256(configuration(value["environment"]["project"]).encode()).hexdigest(),
            "logging-observation-configuration-mismatch")
    hashes = [value.get("configuration_sha256", ""), value.get("trace_identity_sha256", ""), *value["bindings"].values()]
    for service, row in value["services"].items():
        hashes.extend(row.get(k, "") for k in ("trace_identity_sha256", "span_identity_sha256", "log_identity_sha256", "pod_identity_sha256"))
        require(row.get("trace_identity_sha256") == value["trace_identity_sha256"]
                and value.get("ready_replicas", {}).get(service) == 2
                and re.fullmatch(r"[^\s]+@sha256:[0-9a-f]{64}", value["images"][service]), "logging-service-observation-invalid")
        try:
            times = [datetime.fromisoformat(v.replace("Z", "+00:00")) for v in (
                value["query_window"]["start"], row["span_start"], row["log_timestamp"], row["span_end"], value["query_window"]["end"])]
            require(all(v.tzinfo is not None for v in times) and times == sorted(times)
                    and 0 < (times[-1] - times[0]).total_seconds() <= 600, "logging-observation-timestamps-invalid")
        except (KeyError, TypeError, ValueError, AttributeError):
            raise JourneyFailure("logging-observation-timestamps-invalid") from None
    require(all(isinstance(h, str) and re.fullmatch(HEX64, h) for h in hashes), "logging-observation-hash-invalid")
    require(value.get("recovery") == {"status": "not-required", "errors": []}, "logging-observation-recovery-invalid")


class LoggingRollout:
    def __init__(self, runtime, journal, state, progress=lambda _: None):
        self.r, self.j, self.s, self.progress = runtime, journal, state, progress

    def save(self, phase):
        self.s.update(phase=phase, updated_at=stamp())
        self.j.write(self.s)

    def optional(self, kind, name):
        raw = self.r.kubectl("get", kind, name, "--ignore-not-found", "-o", "json")
        return json.loads(raw) if raw.strip() else None

    def patch(self, kind, value, changes):
        patch = [{"op": "test", "path": "/metadata/uid", "value": value["metadata"]["uid"]},
                 {"op": "test", "path": "/metadata/resourceVersion", "value": value["metadata"]["resourceVersion"]}, *changes]
        path = self.r.output / "logging-patch.json"
        try:
            path.write_text(json.dumps(patch), encoding="utf-8")
            self.r.kubectl("patch", kind, value["metadata"]["name"], "--type=json", "--patch-file", str(path))
        finally:
            path.unlink(missing_ok=True)

    def owned(self):
        lease = self.optional("lease", LEASE)
        require(lease and lease["metadata"].get("labels", {}).get("app.kubernetes.io/managed-by") == MANAGER
                and lease.get("spec", {}).get("holderIdentity") == self.s["run_id"]
                and lease["metadata"].get("annotations", {}).get("lightyear.ai/executor") == self.s["executor_id"]
                and lease["metadata"].get("annotations", {}).get("lightyear.ai/recovery-state") == self.s["recovery_uri"]
                and self.s.get("lease_uid") in {None, lease["metadata"]["uid"]}, "logging-lock-ownership-mismatch")
        return lease

    def acquire(self):
        self.save("before-lock")
        lease = self.optional("lease", LEASE)
        annotations = {"lightyear.ai/executor": self.s["executor_id"], "lightyear.ai/recovery-state": self.s["recovery_uri"]}
        if lease:
            require(lease["metadata"].get("labels", {}).get("app.kubernetes.io/managed-by") == MANAGER
                    and not lease.get("spec", {}).get("holderIdentity"), "logging-lock-held-recovery-required")
            self.patch("lease", lease, [{"op": "add", "path": "/spec/holderIdentity", "value": self.s["run_id"]},
                                         {"op": "add", "path": "/metadata/annotations", "value": annotations}])
        else:
            self.r.kubectl("create", "-f", "-", data=json.dumps({"apiVersion": "coordination.k8s.io/v1", "kind": "Lease",
                "metadata": {"name": LEASE, "namespace": self.r.namespace,
                             "labels": {"app.kubernetes.io/managed-by": MANAGER}, "annotations": annotations},
                "spec": {"holderIdentity": self.s["run_id"]}}))
        self.s["lease_uid"] = self.owned()["metadata"]["uid"]
        self.save("lock-held")

    def release(self):
        self.patch("lease", self.owned(), [{"op": "add", "path": "/spec/holderIdentity", "value": ""}])

    def check_config(self):
        value = self.optional("configmap", config_name(self.r.project))
        if value:
            expected = config_object(self.r.project, self.r.namespace)
            require(value.get("data") == expected["data"] and value.get("immutable") is True
                    and not value.get("binaryData") and value["metadata"].get("labels", {}).get("app.kubernetes.io/managed-by") == MANAGER,
                    "logging-configmap-drift")
            require(self.s.get("config_uid") in {None, value["metadata"]["uid"]}, "logging-configmap-uid-drift")
        return value

    def preflight(self):
        require(not (self.optional("lease", LEASE) or {}).get("spec", {}).get("holderIdentity"),
                "logging-lock-held-recovery-required")
        recorded = {}
        for service in SERVICES:
            self.r.service_ready(service)
            deployment = self.r.deployment(service)
            c = deployment["spec"]["template"]["spec"]["containers"][container_index(deployment["spec"], service)]
            values = {row["name"]: row.get("value", "") for row in c.get("env", [])}
            for source in c.get("envFrom", []):
                require(not source.get("prefix"), "logging-prefixed-environment-unsupported")
                kind, ref = ("configmap", source.get("configMapRef")) if "configMapRef" in source else ("secret", source.get("secretRef"))
                require(ref and not ref.get("optional"), "logging-environment-reference-invalid")
                # Values remain in memory. Only configuration key names are used
                # for the conflict gate; credentials are never checkpointed.
                fields = self.r.get(kind, ref["name"]).get("data", {})
                require(not any(k in {"LOGGING_CONFIG", "SPRING_APPLICATION_JSON"} for k in fields),
                        "logging-inherited-configuration-conflict")
            require("SPRING_APPLICATION_JSON" not in values and values.get("LOGGING_CONFIG", ENV["value"]) == ENV["value"]
                    and not any("logging.config" in str(v).lower() for k, v in values.items() if k.endswith("JAVA_OPTIONS") or k == "JAVA_TOOL_OPTIONS")
                    and not c.get("command") and not c.get("args"), "logging-configuration-override-conflict")
            recorded[service] = baseline(deployment, service, self.r.project)
        self.s["baseline"] = recorded
        config = self.check_config()
        require(config is not None or not any(row["logging_preexisting"] for row in recorded.values()),
                "logging-preexisting-configmap-missing")
        self.s["config_preexisting"] = config is not None
        self.s["config_uid"] = config["metadata"]["uid"] if config else None

    def update(self, service, install):
        install = install or self.s["baseline"][service].get("logging_preexisting", False)
        self.owned()
        value = self.r.deployment(service)
        patches = deployment_patch(value, service, self.r.project, self.s["baseline"][service], install=install)
        if patches:
            self.save(("before-install-" if install else "before-restore-") + service)
            self.owned()
            self.patch("deployment", value, patches[2:])
        self.r.kubectl("rollout", "status", "deployment/" + service, "--timeout=15m", timeout=920)
        self.r.wait_ready(service)
        require(normalized(self.r.deployment(service)["spec"], service, self.r.project,
                           self.s["baseline"][service]) == install, "logging-rollout-configuration-not-observed")
        self.save(("installed-" if install else "restored-") + service)

    def install(self):
        self.acquire()
        self.save("before-configmap")
        if not self.check_config():
            self.owned()
            self.r.kubectl("create", "-f", "-", data=json.dumps(config_object(self.r.project, self.r.namespace, self.s["run_id"])))
        self.s["config_uid"] = self.check_config()["metadata"]["uid"]
        self.save("configmap-ready")
        for service in SERVICES:
            self.progress("Installing request correlation logging on " + service)
            self.update(service, True)

    def recover(self):
        self.owned()
        errors = []
        for service in SERVICES:
            try:
                self.progress("Restoring the prior logging configuration on " + service)
                self.update(service, False)
            except Exception as exc:
                errors.append(str(exc) if isinstance(exc, JourneyFailure) else "logging-service-recovery-failed")
        if not errors:
            config = self.check_config()
            if config and not self.s["config_preexisting"]:
                require(config["metadata"].get("annotations", {}).get("lightyear.ai/logging-run") == self.s["run_id"],
                        "logging-configmap-owner-mismatch")
                users = self.r.get("pods").get("items", []) + self.r.get("deployments").get("items", [])
                require(not any(v.get("configMap", {}).get("name") == config_name(self.r.project)
                                for obj in users for v in obj["spec"].get("template", obj).get("spec", obj["spec"]).get("volumes", [])),
                        "logging-configmap-still-referenced")
                self.save("before-configmap-cleanup")
                self.owned()
                # API delete preconditions protect replacement resources.
                body = {"apiVersion": "v1", "kind": "DeleteOptions", "preconditions": {
                    "uid": config["metadata"]["uid"], "resourceVersion": config["metadata"]["resourceVersion"]}}
                path = self.r.output / "logging-delete.json"
                try:
                    path.write_text(json.dumps(body), encoding="utf-8")
                    self.r.kubectl("delete", "--raw", f"/api/v1/namespaces/{self.r.namespace}/configmaps/{config_name(self.r.project)}", "-f", str(path))
                finally:
                    path.unlink(missing_ok=True)
                require(self.optional("configmap", config_name(self.r.project)) is None, "logging-configmap-removal-unconfirmed")
            self.save("before-release-restored")
            self.release()
            self.s["cleanup_complete"] = True
            self.save("restored")
        return {"status": "recovery-required" if errors else "restored", "errors": sorted(set(errors))}

    def observe(self, telemetry, *, timeout=300):
        self.progress("Sending readiness probes with one shared client trace context")
        start = stamp()
        pods, ready = {}, {}
        for service in SERVICES:
            ready[service] = self.r.service_ready(service)["ready_replicas"]
            pods[service] = {p["metadata"]["name"]: p["metadata"]["uid"] for p in self.r.pods(service)}
            response = self.r.send(service, "GET", "/actuator/health/readiness", None, {})
            require(response.status == 200 and response.json().get("status") == "UP", "logging-probe-readiness-failed")
        end, trace_id = stamp(), hashed(self.s["run_id"])[:32]
        deadline = time.monotonic() + timeout
        while True:
            self.progress("Waiting for matching Cloud Logging entries and Cloud Trace spans")
            logs, complete = telemetry.logs(self.s["environment"], trace_id, start, end)
            matches = correlate(telemetry.trace(trace_id), logs, project=self.r.project, environment=self.s["environment"],
                                trace_id=trace_id, pods=pods, start=start, end=end)
            self.progress("Verified log and span matches for " + str(len(matches)) + "/8 services")
            if set(matches) == set(SERVICES):
                break
            if time.monotonic() >= deadline:
                self.s["correlation_diagnostic"] = {"observed_services": sorted(matches),
                    "missing_services": sorted(set(SERVICES) - set(matches)), "matching_log_records": len(logs),
                    "search_complete": complete, "query_window": {"start": start, "end": end}}
                self.save("correlation-incomplete")
            require(time.monotonic() < deadline, "logging-correlation-not-observed" if complete else "logging-search-bound-exceeded")
            time.sleep(10)
        for service in SERVICES:
            self.r.service_ready(service)
            require(normalized(self.r.deployment(service)["spec"], service, self.r.project, self.s["baseline"][service]),
                    "logging-configuration-changed-during-probe")
            require(pods[service] == {p["metadata"]["name"]: p["metadata"]["uid"] for p in self.r.pods(service)},
                    "logging-pods-changed-during-probe")
        require(self.check_config() is not None, "logging-configmap-missing")
        return {"schema_version": "1.0", "observation_type": OBSERVATION_TYPE, "run_id": self.s["run_id"],
                "status": "passed-service-log-trace-correlation", "environment": self.s["environment"],
                "bindings": self.s["bindings"], "images": self.s["images"], "ready_replicas": ready,
                "configuration_sha256": hashlib.sha256(configuration(self.r.project).encode()).hexdigest(),
                "trace_identity_sha256": hashed(trace_id), "services": matches, "query_window": {"start": start, "end": end},
                "scope": "eight-service-readiness-probes-with-common-client-trace-context", "configuration_retained": True,
                "service_correlation_qualified": True, "business_journey_qualified": False,
                "recovery": {"status": "not-required", "errors": []}, "credentials_persisted": False,
                "raw_output_persisted": False, "production_environment": False, "production_ready": False, "ms67_complete": False}
