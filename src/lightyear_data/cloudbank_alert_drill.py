"""Observe a synthetic Google Monitoring incident, then remove only owned resources.

The metric is deliberately independent of application availability. No service,
notification channel, existing policy, or existing metric is changed. Recovery
cleans up an interrupted run; it never awards qualification.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import copy
import json
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener

from .cloudbank_journeys import JourneyFailure, require
from .cloudbank_journeys_gke import NoRedirect, command
from .contracts import content_hash, verify_signature
from .cloudbank_secret_rotation_gke import hashed


STATE_TYPE = "lightyear-cloudbank-ms67-alert-drill-recovery"
OBSERVATION_TYPE = "lightyear-cloudbank-ms67-alert-drill-observation"
STATE_FILE = "alert-drill.recovery.json"
OBSERVATION_FILE = "alert-drill.observation.json"
LABEL = "lightyear_ms67_run"
POLL_SECONDS = 20
PHASE_SECONDS = 720
RUN_PATTERN = r"ms67-alert-[0-9a-f]{32}"
IDENTITY_PATTERN = r"[a-z0-9][a-z0-9-]{0,62}"
BINDINGS = {"image_lock_sha256", "ms64_receipt_sha256", "platform_profile_sha256"}
API_COLLECTIONS = {"metricDescriptors", "alertPolicies", "alerts", "timeSeries"}
ERROR_STATUSES = {"CANCELLED", "UNKNOWN", "INVALID_ARGUMENT", "DEADLINE_EXCEEDED", "NOT_FOUND",
                  "ALREADY_EXISTS", "PERMISSION_DENIED", "RESOURCE_EXHAUSTED", "FAILED_PRECONDITION",
                  "ABORTED", "OUT_OF_RANGE", "UNIMPLEMENTED", "INTERNAL", "UNAVAILABLE", "DATA_LOSS",
                  "UNAUTHENTICATED"}
ERROR_FIELDS = {"name", "parent", "filter", "orderBy", "order_by", "pageSize", "page_size", "pageToken",
                "page_token", "metric_descriptor", "metricDescriptor", "metric_descriptor.type", "metricDescriptor.type",
                "alert_policy", "alertPolicy", "time_series", "timeSeries", "interval", "interval.start_time",
                "interval.end_time", "interval.startTime", "interval.endTime"}


def error_metadata(raw):
    """Retain only known status/field identifiers, never provider messages or values."""
    if len(raw) > 16384:
        return {}
    try:
        value = json.loads(raw)
        error = value.get("error", {}) if isinstance(value, dict) else {}
        if not isinstance(error, dict):
            return {}
        result = {}
        if isinstance(error.get("status"), str) and error["status"] in ERROR_STATUSES:
            result["provider_status"] = error["status"]
        fields = set()
        for detail in error.get("details", []):
            if not isinstance(detail, dict) or detail.get("@type") != "type.googleapis.com/google.rpc.BadRequest":
                continue
            for row in detail.get("fieldViolations", []):
                field = row.get("field") if isinstance(row, dict) else None
                if isinstance(field, str) and field in ERROR_FIELDS:
                    fields.add(field)
        if fields:
            result["invalid_fields"] = sorted(fields)
        return result
    except (TypeError, ValueError, UnicodeError):
        return {}


def matches(pattern, value):
    return isinstance(value, str) and re.fullmatch(pattern, value) is not None


def canonical_resource_name(value, project, project_number, collection):
    """Resolve only the verified project's ID/number aliases, retaining the resource ID."""
    patterns = {"alertPolicies": r"[A-Za-z0-9_-]{1,160}",
                "alerts": r"[A-Za-z0-9_-][A-Za-z0-9_.-]{0,159}"}
    parts = value.split("/") if isinstance(value, str) else []
    if (collection not in patterns or len(parts) != 4 or parts[0] != "projects"
            or parts[1] not in {project, project_number} or parts[2] != collection
            or ".." in parts[3] or not matches(patterns[collection], parts[3])):
        return None
    return f"projects/{project_number}/{collection}/{parts[3]}"


def validate_bindings(value):
    require(isinstance(value, dict) and set(value) == BINDINGS
            and all(matches(r"[0-9a-f]{64}", v) for v in value.values()), "alert-bindings-invalid")


def validate_environment(value):
    require(isinstance(value, dict) and set(value) ==
            {"project", "region", "cluster", "namespace", "namespace_uid_sha256"}
            and all(matches(IDENTITY_PATTERN, value[k]) for k in ("project", "region", "cluster", "namespace"))
            and matches(r"[0-9a-f]{64}", value["namespace_uid_sha256"]), "alert-environment-invalid")


def validate_state(value, key, *, project, region, cluster, namespace, project_number, evidence_bucket):
    require(value.get("content_sha256") == content_hash(value) and verify_signature(value, key),
            "alert-recovery-signature-invalid")
    validate_environment(value.get("environment"))
    validate_bindings(value.get("bindings"))
    require(value.get("schema_version") == "1.0" and value.get("state_type") == STATE_TYPE
            and matches(RUN_PATTERN, value.get("run_id")) and value.get("project_number") == project_number
            and value.get("context") == f"gke_{project}_{region}_{cluster}"
            and all(value["environment"][k] == v for k, v in
                    (("project", project), ("region", region), ("cluster", cluster), ("namespace", namespace)))
            and all(value.get(k) is False for k in
                    ("credentials_persisted", "raw_output_persisted", "production_environment")),
            "alert-recovery-identity-invalid")
    require(value.get("recovery_uri") == evidence_bucket + "/" + value["run_id"] + "/" + STATE_FILE,
            "alert-recovery-uri-invalid")
    for kind in ("descriptor", "policy"):
        require(value.get(kind + "_phase") in {"not-started", "creating", "created", "rejected", "deleting", "deleted"},
                "alert-recovery-resource-phase-invalid")
    name = value.get("policy_name")
    require(name is None or canonical_resource_name(name, project, project_number, "alertPolicies") is not None,
            "alert-recovery-policy-identity-invalid")
    require(value["policy_phase"] not in {"created", "deleting"} or
            (name is not None and matches(r"[0-9a-f]{64}", value.get("policy_version_sha256"))),
            "alert-recovery-policy-version-required")
    require(type(value.get("cleanup_complete")) is bool and
            (not value["cleanup_complete"] or value["descriptor_phase"] == value["policy_phase"] == "deleted")
            and isinstance(value.get("observations"), dict), "alert-recovery-cleanup-invalid")
    instant(value.get("updated_at"))
    return value


def stamp(value=None):
    return (value or datetime.now(timezone.utc)).isoformat().replace("+00:00", "Z")


def instant(value):
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        require(result.utcoffset() is not None, "alert-timestamp-timezone-required")
        return result
    except (AttributeError, TypeError, ValueError):
        raise JourneyFailure("alert-timestamp-invalid") from None


def metric_type(run_id):
    require(re.fullmatch(RUN_PATTERN, run_id) is not None, "alert-run-identity-invalid")
    return "custom.googleapis.com/lightyear/ms67/alert_probe_" + run_id.removeprefix("ms67-alert-")


def descriptor_spec(run_id):
    return {"type": metric_type(run_id), "metricKind": "GAUGE", "valueType": "INT64", "unit": "1",
            "displayName": run_id, "description": "Temporary MS67 synthetic alert qualification signal.",
            "labels": [{"key": "run_id", "valueType": "STRING", "description": "Owned qualification run."}]}


def metric_filter(project, run_id):
    return (f'metric.type = "{metric_type(run_id)}" AND resource.type = "global" '
            f'AND resource.labels.project_id = "{project}" AND metric.labels.run_id = "{run_id}"')


def policy_spec(project, run_id):
    return {"displayName": run_id, "enabled": True, "combiner": "OR", "userLabels": {LABEL: run_id},
            "notificationChannels": [], "alertStrategy": {"autoClose": "1800s"},
            "conditions": [{"displayName": "Synthetic probe exceeds zero", "conditionThreshold": {
                "filter": metric_filter(project, run_id), "comparison": "COMPARISON_GT", "thresholdValue": 0.5,
                "duration": "60s", "aggregations": [{"alignmentPeriod": "60s", "perSeriesAligner": "ALIGN_MAX"}],
                "trigger": {"count": 1}, "evaluationMissingData": "EVALUATION_MISSING_DATA_NO_OP"}}]}


def normalized_policy(value):
    result = {k: value.get(k) for k in ("displayName", "enabled", "combiner")}
    result.update(userLabels=value.get("userLabels", {}), notificationChannels=value.get("notificationChannels", []),
                  alertStrategy=value.get("alertStrategy", {}), conditions=[])
    for row in value.get("conditions", []):
        condition = copy.deepcopy({k: v for k, v in row.items() if k != "name"})
        threshold = condition.get("conditionThreshold", {})
        for key, default in (("denominatorFilter", ""), ("denominatorAggregations", [])):
            if threshold.get(key) == default:
                threshold.pop(key)
        for aggregation in threshold.get("aggregations", []):
            for key, default in (("crossSeriesReducer", "REDUCE_NONE"), ("groupByFields", [])):
                if aggregation.get(key) == default:
                    aggregation.pop(key)
        result["conditions"].append(condition)
    return result


def policy_version(value):
    return hashed({k: value.get(k) for k in ("creationRecord", "mutationRecord")})


class ApiFailure(JourneyFailure):
    def __init__(self, code, *, method=None, collection=None, metadata=None):
        self.code = code
        self.diagnostic = {"http_status": code}
        if method in {"GET", "POST", "DELETE"} and collection in API_COLLECTIONS:
            self.diagnostic.update(method=method, collection=collection)
        self.diagnostic.update(metadata or {})
        super().__init__("alert-api-http-" + str(code))


class Monitoring:
    def __init__(self, project, project_number, invoke=command):
        require(re.fullmatch(r"[a-z][a-z0-9-]{4,61}[a-z0-9]", project) is not None
                and re.fullmatch(r"[1-9][0-9]{0,19}", project_number) is not None, "alert-project-invalid")
        self.project, self.number, self.invoke = project, project_number, invoke
        self.prefix = "projects/" + project_number
        self.token, self.token_at = "", 0.0
        self.opener = build_opener(NoRedirect())

    def request(self, method, path, *, query=None, body=None, absent=False):
        require(method in {"GET", "POST", "DELETE"} and path.startswith(self.prefix + "/")
                and ".." not in path and re.fullmatch(r"[A-Za-z0-9/_.\-]+", path) is not None,
                "alert-api-boundary-invalid")
        collection = path.removeprefix(self.prefix + "/").split("/", 1)[0]
        require(collection in API_COLLECTIONS, "alert-api-collection-invalid")
        if not self.token or time.monotonic() - self.token_at > 900:
            self.token = self.invoke(["gcloud", "auth", "print-access-token", "--project", self.project]).strip()
            require(bool(self.token) and not any(c.isspace() for c in self.token), "alert-access-token-invalid")
            self.token_at = time.monotonic()
        url = "https://monitoring.googleapis.com/v3/" + path
        if query:
            url += "?" + urlencode(query)
        request = Request(url, method=method, data=None if body is None else json.dumps(body).encode(), headers={
            "Authorization": "Bearer " + self.token, "Content-Type": "application/json",
            "x-goog-user-project": self.project})
        try:
            with self.opener.open(request, timeout=30) as response:
                raw = response.read(4 * 1024 * 1024 + 1)
            require(len(raw) <= 4 * 1024 * 1024, "alert-api-response-too-large")
            value = json.loads(raw or b"{}")
            require(isinstance(value, dict), "alert-api-response-invalid")
            return value
        except HTTPError as exc:
            code = exc.code
            try:
                metadata = error_metadata(exc.read(16385))
            except (OSError, ValueError):
                metadata = {}
            finally:
                exc.close()
            if code == 404 and absent and method == "GET":
                return None
            raise ApiFailure(code, method=method, collection=collection, metadata=metadata) from None
        except (URLError, TimeoutError, OSError):
            raise JourneyFailure("alert-api-unavailable-or-timed-out") from None

    def listing(self, kind, query=None):
        require(kind in {"alertPolicies", "alerts", "timeSeries"}, "alert-list-kind-invalid")
        params = {"pageSize": 100, **(query or {})}
        rows = []
        for _ in range(20):
            value = self.request("GET", self.prefix + "/" + kind, query=params)
            require(not value.get("executionErrors"), "alert-query-partial-error")
            page = value.get(kind, [])
            require(isinstance(page, list) and all(isinstance(row, dict) for row in page), "alert-query-response-invalid")
            rows.extend(page)
            token = value.get("nextPageToken")
            if not token:
                return rows
            params["pageToken"] = token
        raise JourneyFailure("alert-query-incomplete")

    def descriptor(self, run_id):
        return self.request("GET", self.descriptor_path(run_id), absent=True)

    def descriptor_path(self, run_id):
        # Google binds name=projects/*/metricDescriptors/**. The metric's slashes
        # are resource-path separators, not an encoded single path segment.
        # metric_type only contains a fixed prefix and a validated UUID.
        return self.prefix + "/metricDescriptors/" + metric_type(run_id)

    def check_descriptor(self, run_id, value):
        expected = descriptor_spec(run_id)
        actual = copy.deepcopy({k: value.get(k) for k in expected}) if value is not None else {}
        for label in actual.get("labels", []):
            label.setdefault("valueType", "STRING")
        require(actual == expected,
                "alert-descriptor-ownership-or-config-drift")

    def policy_name(self, name):
        canonical = canonical_resource_name(name, self.project, self.number, "alertPolicies")
        require(canonical is not None, "alert-policy-project-or-name-invalid")
        return canonical

    def policy(self, name):
        canonical = self.policy_name(name)
        value = self.request("GET", canonical, absent=True)
        if value is not None:
            require(self.policy_name(value.get("name")) == canonical, "alert-policy-readback-identity-mismatch")
        return value

    def check_policy(self, run_id, value):
        require(value is not None and not value.get("validity")
                and normalized_policy(value) == policy_spec(self.project, run_id),
                "alert-policy-ownership-or-config-drift")
        return self.policy_name(value.get("name"))

    def point(self, run_id, value, timestamp):
        require(type(value) is int and value in {0, 1}, "alert-synthetic-value-invalid")
        return self.request("POST", self.prefix + "/timeSeries", body={"timeSeries": [{
            "metric": {"type": metric_type(run_id), "labels": {"run_id": run_id}},
            "resource": {"type": "global", "labels": {"project_id": self.project}},
            "metricKind": "GAUGE", "valueType": "INT64",
            "points": [{"interval": {"endTime": timestamp}, "value": {"int64Value": str(value)}}]}]})

    def observed_point(self, run_id, value, since, now):
        rows = self.listing("timeSeries", {"filter": metric_filter(self.project, run_id), "view": "FULL",
                    "interval.startTime": stamp(instant(since) - timedelta(microseconds=1)), "interval.endTime": now})
        matches = []
        for row in rows:
            require(row.get("metric") == {"type": metric_type(run_id), "labels": {"run_id": run_id}}
                    and row.get("resource") == {"type": "global", "labels": {"project_id": self.project}},
                    "alert-series-identity-mismatch")
            for point in row.get("points", []):
                timestamp = point.get("interval", {}).get("endTime")
                if str(point.get("value", {}).get("int64Value")) == str(value) \
                        and instant(since) <= instant(timestamp) <= instant(now):
                    matches.append({"value": value, "timestamp": timestamp, "point_sha256": hashed(point)})
        return min(matches, key=lambda p: instant(p["timestamp"])) if matches else None

    def matching_alerts(self, run_id, policy_name):
        result = []
        policy_name = self.policy_name(policy_name)
        for value in self.listing("alerts", {"orderBy": "openTime desc"}):
            observed_policy = canonical_resource_name(value.get("policy", {}).get("name"),
                                                       self.project, self.number, "alertPolicies")
            if observed_policy != policy_name:
                continue
            alert_name = canonical_resource_name(value.get("name"), self.project, self.number, "alerts")
            require(value.get("policy", {}).get("userLabels", {}).get(LABEL) == run_id
                    and value.get("metric", {}).get("type") == metric_type(run_id)
                    and value.get("metric", {}).get("labels", {}).get("run_id") == run_id
                    and value.get("resource", {}).get("type") == "global"
                    and value.get("resource", {}).get("labels", {}).get("project_id") in {self.project, self.number}
                    and alert_name is not None, "alert-incident-identity-mismatch")
            result.append({"alert_identity_sha256": hashed(alert_name), "state": value.get("state"),
                           "open_time": value.get("openTime"), "close_time": value.get("closeTime"),
                           "policy_sha256": hashed(policy_spec(self.project, run_id))})
        return result


class AlertDrill:
    def __init__(self, api, journal, state, *, progress=lambda _: None, now=lambda: datetime.now(timezone.utc),
                 sleep=time.sleep, monotonic=time.monotonic, phase_seconds=PHASE_SECONDS):
        self.api, self.journal, self.state, self.progress = api, journal, state, progress
        self.now, self.sleep, self.monotonic, self.phase_seconds = now, sleep, monotonic, phase_seconds
        self.checkpoint_failed = False

    def save(self, phase):
        self.state.update(phase=phase, updated_at=stamp(self.now()))
        try:
            self.journal.write(self.state)
        except Exception:
            self.checkpoint_failed = True
            raise JourneyFailure("alert-checkpoint-not-confirmed-recovery-required") from None

    def fresh(self):
        run_id = self.state["run_id"]
        require(self.api.descriptor(run_id) is None, "alert-descriptor-already-exists")
        require(not any(p.get("userLabels", {}).get(LABEL) == run_id for p in self.api.listing("alertPolicies")),
                "alert-policy-already-exists")
        # Access to incidents is a prerequisite, before any metric/policy creation.
        self.api.listing("alerts")

    def create(self, kind):
        state, run_id = self.state, self.state["run_id"]
        state[kind + "_phase"] = "creating"
        self.save("before-" + kind + "-creation")
        path, body = (("metricDescriptors", descriptor_spec(run_id)) if kind == "descriptor"
                      else ("alertPolicies", policy_spec(self.api.project, run_id)))
        try:
            result = self.api.request("POST", self.api.prefix + "/" + path, body=body)
        except ApiFailure as exc:
            if exc.code in {400, 401, 403, 404, 422}:
                state[kind + "_phase"] = "rejected"
                self.save(kind + "-creation-rejected")
            raise
        if kind == "descriptor":
            self.api.check_descriptor(run_id, result)
        else:
            name = self.api.check_policy(run_id, result)
            state.update(policy_name=name, policy_version_sha256=policy_version(result))
        self.save(kind + "-creation-acknowledged")
        started = self.monotonic()
        while True:
            observed = self.api.descriptor(run_id) if kind == "descriptor" else self.api.policy(state["policy_name"])
            if observed is not None:
                (self.api.check_descriptor if kind == "descriptor" else self.api.check_policy)(run_id, observed)
                break
            require(self.monotonic() - started < 180, "alert-" + kind + "-creation-not-visible")
            self.sleep(POLL_SECONDS)
        state[kind + "_phase"] = "created"
        self.save(kind + "-created")

    def reconcile(self):
        state, run_id = self.state, self.state["run_id"]
        if state["descriptor_phase"] == "creating":
            candidate = self.api.descriptor(run_id)
            require(candidate is not None, "alert-descriptor-creation-ambiguous")
            self.api.check_descriptor(run_id, candidate)
            state["descriptor_phase"] = "created"
            self.save("descriptor-reconciled")
        if state["policy_phase"] == "creating":
            rows = [p for p in self.api.listing("alertPolicies") if p.get("userLabels", {}).get(LABEL) == run_id]
            require(len(rows) == 1, "alert-policy-creation-ambiguous")
            name = self.api.check_policy(run_id, rows[0])
            if state.get("policy_name"):
                require(name == self.api.policy_name(state["policy_name"])
                        and policy_version(rows[0]) == state.get("policy_version_sha256"),
                        "alert-policy-changed-after-creation-acknowledgment")
            state.update(policy_name=name, policy_phase="created",
                         policy_version_sha256=policy_version(rows[0]))
            self.save("policy-reconciled")

    def guard(self):
        self.api.check_descriptor(self.state["run_id"], self.api.descriptor(self.state["run_id"]))
        if self.state.get("policy_name"):
            current = self.api.policy(self.state["policy_name"])
            self.api.check_policy(self.state["run_id"], current)
            require(policy_version(current) == self.state["policy_version_sha256"], "alert-policy-changed-during-drill")

    def publish(self, value):
        self.guard()
        last = self.state.get("last_point_time")
        if last:
            delay = 6 - (self.now() - instant(last)).total_seconds()
            if delay > 0:
                self.sleep(delay)
        timestamp = stamp(self.now())
        self.state.update(last_point_time=timestamp, last_point_value=value)
        self.save("before-synthetic-point-" + str(value))
        self.api.point(self.state["run_id"], value, timestamp)
        return timestamp

    def wait(self, stage, value, expected_state=None):
        self.progress(stage)
        state, started = self.state, self.monotonic()
        first = self.publish(value)
        self.state[stage + "_since"] = first
        self.save(stage + "-started")
        while self.monotonic() - started < self.phase_seconds:
            now = stamp(self.now())
            point = self.api.observed_point(state["run_id"], value, first, now)
            alerts = [] if not expected_state else self.api.matching_alerts(state["run_id"], state["policy_name"])
            if expected_state == "OPEN":
                matches = [a for a in alerts if a["state"] == "OPEN" and instant(a["open_time"]) >= instant(first)]
            elif expected_state == "CLOSED":
                opened = state["observations"]["opened"]
                matches = [a for a in alerts if a["state"] == "CLOSED"
                           and a["alert_identity_sha256"] == opened["alert_identity_sha256"]
                           and a["open_time"] == opened["open_time"]
                           and instant(a["close_time"]) >= instant(first)]
            else:
                matches = [None]
            if point and len(matches) == 1:
                # Neither disappearance, expiry, nor deleting/disabling the policy proves recovery.
                if expected_state == "CLOSED":
                    require(instant(matches[0]["close_time"]) >= instant(point["timestamp"]),
                            "alert-close-precedes-observed-healthy-point")
                self.guard()
                if expected_state == "CLOSED":
                    require((instant(matches[0]["close_time"]) - instant(matches[0]["open_time"])).total_seconds() < 1800,
                            "alert-close-too-late-to-exclude-auto-close")
                state["observations"][stage] = {"point": point, **(matches[0] or {})}
                self.save(stage + "-observed")
                return
            require(len(matches) <= 1, "alert-multiple-active-incidents")
            self.sleep(POLL_SECONDS)
            self.publish(value)
        raise JourneyFailure("alert-" + stage + "-timeout")

    def cleanup(self):
        require(not self.checkpoint_failed, "alert-checkpoint-not-confirmed-recovery-required")
        self.reconcile()
        state, run_id = self.state, self.state["run_id"]
        # Remove the owned policy first: no synthetic series is written after this point.
        name = state.get("policy_name")
        if name:
            name = self.api.policy_name(name)
            state["policy_name"] = name
            current = self.api.policy(name)
            if current is not None:
                require(state["policy_phase"] in {"created", "deleting"}, "alert-unowned-policy")
                self.api.check_policy(run_id, current)
                require(policy_version(current) == state["policy_version_sha256"], "alert-policy-changed-during-drill")
                state["policy_phase"] = "deleting"
                self.save("before-policy-deletion")
                self.api.request("DELETE", name)
            require(self.api.policy(name) is None, "alert-policy-removal-unconfirmed")
            state["policy_phase"] = "deleted"
            self.save("policy-removed")
        current = self.api.descriptor(run_id)
        if current is not None:
            require(state["descriptor_phase"] in {"created", "deleting"}, "alert-unowned-descriptor")
            self.api.check_descriptor(run_id, current)
            state["descriptor_phase"] = "deleting"
            self.save("before-descriptor-deletion")
            self.api.request("DELETE", self.api.descriptor_path(run_id))
        require(self.api.descriptor(run_id) is None, "alert-descriptor-removal-unconfirmed")
        state.update(descriptor_phase="deleted", policy_phase="deleted", cleanup_complete=True)
        self.save("restored")
        return {"status": "restored", "policy_absent": True, "metric_descriptor_absent": True, "errors": []}

    def run(self):
        self.fresh()
        self.progress("Creating the owned synthetic metric")
        self.create("descriptor")
        self.wait("baseline", 0)
        self.progress("Creating the owned alert policy without notification recipients")
        self.create("policy")
        self.wait("opened", 1, "OPEN")
        self.wait("closed", 0, "CLOSED")
        self.progress("Removing the owned alert policy and synthetic metric")
        recovery = self.cleanup()
        return self.observation("passed-synthetic-alert-and-recovery", recovery)

    def observation(self, status, recovery):
        state = self.state
        return {"schema_version": "1.0", "observation_type": OBSERVATION_TYPE, "status": status,
                "run_id": state["run_id"], "environment": state["environment"], "bindings": state["bindings"],
                "policy_sha256": hashed(policy_spec(self.api.project, state["run_id"])),
                "observations": state["observations"], "recovery": recovery,
                "notification_recipients": 0, "application_mutations": 0,
                "alert_fired": status == "passed-synthetic-alert-and-recovery",
                "alert_recovered": status == "passed-synthetic-alert-and-recovery",
                "service_correlation_qualified": False, "credentials_persisted": False,
                "raw_output_persisted": False, "production_environment": False,
                "ms67_complete": False, "production_ready": False}


def verify_observation(value, key):
    require(value.get("content_sha256") == content_hash(value) and verify_signature(value, key),
            "alert-observation-signature-invalid")
    require(value.get("observation_type") == OBSERVATION_TYPE and value.get("schema_version") == "1.0"
            and value.get("status") == "passed-synthetic-alert-and-recovery"
            and re.fullmatch(RUN_PATTERN, value.get("run_id", "")) is not None,
            "alert-passing-observation-required")
    validate_environment(value.get("environment"))
    validate_bindings(value.get("bindings"))
    require(value.get("alert_fired") is True and value.get("alert_recovered") is True
            and all(type(value.get(k)) is int and value[k] == 0 for k in
                    ("notification_recipients", "application_mutations"))
            and all(value.get(k) is False for k in ("service_correlation_qualified", "credentials_persisted",
                    "raw_output_persisted", "production_environment", "ms67_complete", "production_ready")),
            "alert-observation-claims-invalid")
    require(value.get("recovery") == {"status": "restored", "policy_absent": True,
                                     "metric_descriptor_absent": True, "errors": []}, "alert-cleanup-required")
    rows = value.get("observations", {})
    require(set(rows) == {"baseline", "opened", "closed"}, "alert-three-observations-required")
    baseline, opened, closed = (rows[k] for k in ("baseline", "opened", "closed"))
    for row, expected in ((baseline, 0), (opened, 1), (closed, 0)):
        point = row.get("point", {})
        require(type(point.get("value")) is int and point["value"] == expected
                and re.fullmatch(r"[0-9a-f]{64}", point.get("point_sha256", "")) is not None,
                "alert-metric-proof-invalid")
        instant(point.get("timestamp"))
    project = value.get("environment", {}).get("project", "")
    expected_policy = hashed(policy_spec(project, value["run_id"]))
    require(value.get("policy_sha256") == expected_policy
            and opened.get("policy_sha256") == closed.get("policy_sha256") == expected_policy
            and re.fullmatch(r"[0-9a-f]{64}", opened.get("alert_identity_sha256", "")) is not None
            and opened.get("alert_identity_sha256") == closed.get("alert_identity_sha256")
            and opened.get("state") == "OPEN" and opened.get("close_time") is None
            and closed.get("state") == "CLOSED" and opened.get("open_time") == closed.get("open_time")
            and instant(baseline["point"]["timestamp"]) < instant(opened["point"]["timestamp"])
            and instant(opened["point"]["timestamp"]) <= instant(opened["open_time"])
            and instant(opened["open_time"]) < instant(closed["point"]["timestamp"]) <= instant(closed["close_time"])
            and (instant(closed["close_time"]) - instant(opened["open_time"])).total_seconds() < 1800,
            "alert-open-close-proof-invalid")
