"""Bounded Cloud SQL HA failover evidence; no PITR or milestone admission.

The only source mutation is one operator-authorized failover. Application
processes stay running. Recovery observes the saved operation and removes the
owned SQL probe; it cannot replay business writes, restart apps, or fail back.
"""
from __future__ import annotations

import base64
import json
import math
import re
import time
from urllib.parse import quote, urlsplit

from .cloudbank_journeys import JourneyFailure, Journeys, SERVICES, hashed, require
from .cloudbank_journeys_gke import GkeRuntime
from .cloudbank_sql_recovery import (
    RETRYABLE_STATUS_READ_ERRORS, STATUS_READ_RETRY_LIMIT, invoke, source_profile, utc, write_signed,
)

STATE_TYPE = "lightyear-cloudbank-sql-ha-state"
OBSERVATION_TYPE = "lightyear-cloudbank-sql-ha-failover"
RECOVERY_LIMIT_SECONDS = 600
EVIDENCE_FILES = ("sql-ha-state.json", "sql-ha.json", "recovery-state.json", "ha-cleanup.json")
DATABASE_SERVICES = {"azn-server", "customer", "account", "checks", "testrunner"}


def reason(exc):
    return (str(exc) if isinstance(exc, JourneyFailure) else
            "operator-interrupted" if isinstance(exc, KeyboardInterrupt) else "input-or-runtime-error")


def ha_profile(instance, project, region, source, *, require_standby=True):
    profile = source_profile(instance, project, region, source)
    settings = instance.get("settings", {})
    require(settings.get("availabilityType") == "REGIONAL"
            and instance.get("instanceType") == "CLOUD_SQL_INSTANCE"
            and not instance.get("masterInstanceName"), "regional-native-primary-required")
    primary, standby = instance.get("gceZone", ""), instance.get("secondaryGceZone", "")
    require(all(re.fullmatch(re.escape(region) + r"-[a-z]", zone) for zone in (primary, standby))
            and primary != standby, "distinct-primary-and-standby-zones-required")
    if require_standby:
        require(instance.get("failoverReplica", {}).get("available") is not False, "standby-not-available")
    require(instance.get("connectionName") == f"{project}:{region}:{source}"
            and str(settings.get("settingsVersion", "")).isdigit(), "sql-connection-and-settings-identity-required")
    return {**profile, "connection_name": instance["connectionName"],
            "primary_zone": primary, "standby_zone": standby, "settings_version": str(settings["settingsVersion"])}


def unchanged_endpoint(before, after):
    return all(before[k] == after[k] for k in
               ("name", "project", "region", "create_time", "private_network", "private_ip", "connection_name"))


class HaRuntime(GkeRuntime):
    def send(self, service, method, path, data, headers):
        response = super().send(service, method, path, data, headers)
        if (method == "GET" or (service == "azn-server" and path == "/oauth2/token")) and response.status >= 500:
            raise JourneyFailure("ha-transient-read-failed")
        return response

    def forbidden(self, *args, **kwargs):
        raise JourneyFailure("ha-drill-must-not-restart-or-reconfigure-applications")

    stop = start = restart = restart_all = crash_stopped = forbidden
    block_checks_delivery = patch_checks_delivery = forbidden

    def close(self, **kwargs):
        require(not self.stopped and self.checks_delivery is None, "ha-recovery-must-not-contain-app-mutations")
        result = super().close(**kwargs)
        if result["status"] == "restored":
            deadline = time.monotonic() + 60
            while self.kubectl("get", "pod/" + self.probe_name, "--ignore-not-found", "-o", "json").strip():
                require(time.monotonic() < deadline, "ha-probe-deletion-not-observed")
                time.sleep(min(2, max(0, deadline - time.monotonic())))
        return result

    def process_identities(self):
        identities = {}
        for service in SERVICES:
            deployment = self.deployment(service)
            require(deployment["spec"].get("replicas") == 2, "ha-replica-count-changed")
            pods = self.pods(service)
            require(len(pods) == 2, "ha-process-set-changed")
            records = []
            for pod in pods:
                rows = [c for c in pod.get("status", {}).get("containerStatuses", []) if c.get("name") == service]
                require(len(rows) == 1 and not pod["metadata"].get("deletionTimestamp"), "ha-process-set-changed")
                row = rows[0]
                started = row.get("state", {}).get("running", {}).get("startedAt")
                require(bool(row.get("containerID") and started) and type(row.get("restartCount")) is int,
                        "ha-process-not-running")
                require(row.get("imageID", "").endswith(self.images[service].split("@")[-1]), "deployment-image-drift")
                records.append({"uid": pod["metadata"]["uid"], "container": row["containerID"],
                    "restarts": row["restartCount"], "started": started, "pod_spec_sha256": hashed(pod["spec"])})
            identities[service] = hashed({"deployment_uid": deployment["metadata"]["uid"],
                "template": deployment["spec"]["template"], "processes": sorted(records, key=lambda r: r["uid"])})
        return identities

    def datasource_bindings(self, profile):
        result, probe_url = {}, None
        for service in SERVICES:
            name = "cloudbank-" + service + "-external"
            secret = self.get("secret", name)
            encoded = secret.get("data", {}).get("SPRING_DATASOURCE_URL")
            if not encoded:
                continue
            jdbc = base64.b64decode(encoded, validate=True).decode()
            parsed = urlsplit(jdbc.removeprefix("jdbc:"))
            require(jdbc.startswith("jdbc:postgresql://") and parsed.hostname == profile["private_ip"]
                    and (parsed.port or 5432) == 5432 and not parsed.username and not parsed.password
                    and not parsed.query and not parsed.fragment and re.fullmatch(r"/[A-Za-z0-9_-]+", parsed.path),
                    "datasource-source-binding-invalid-" + service)
            require(all(k in secret["data"] for k in ("SPRING_DATASOURCE_USERNAME", "SPRING_DATASOURCE_PASSWORD")),
                    "database-credentials-missing-" + service)
            # Check the running pods, not just a possibly newer Deployment template.
            for pod in self.pods(service):
                container = next(c for c in pod["spec"]["containers"] if c["name"] == service)
                env_from = container.get("envFrom", [])
                require(env_from and env_from[-1] == {"secretRef": {"name": name}}
                        and not any(e.get("name", "").startswith("SPRING_DATASOURCE_") for e in container.get("env", [])),
                        "running-datasource-override-not-supported-" + service)
                actual = self.kubectl("exec", "pod/" + pod["metadata"]["name"], "-c", service, "--",
                                      "printenv", "SPRING_DATASOURCE_URL").strip()
                require(actual == jdbc, "running-datasource-differs-from-synced-secret-" + service)
            result[service] = {"jdbc_url_sha256": hashed(jdbc), "secret_uid_sha256": hashed(secret["metadata"]["uid"])}
            if service == "checks":
                probe_url = jdbc
        require(set(result) == DATABASE_SERVICES and probe_url, "five-application-datasource-bindings-required")
        return result, probe_url


class SqlHa:
    def __init__(self, runtime, source, key, signer, *, state=None):
        require(re.fullmatch(r"[a-z][a-z0-9-]{0,97}", source) is not None, "source-instance-name-invalid")
        self.runtime, self.key, self.signer = runtime, key, signer
        self.state = state if state is not None else {"state_type": STATE_TYPE, "run_id": runtime.run_id,
            "source": source, "project": runtime.project, "region": runtime.region, "context": runtime.context,
            "namespace": runtime.namespace, "images": runtime.images, "probe_image": runtime.probe_image,
            "operation": None, "fixture_marker": "lightyear-synthetic-journey:" + runtime.run_id}
        require(self.state.get("state_type") == STATE_TYPE and self.state.get("source") == source
                and self.state.get("run_id") == runtime.run_id and self.state.get("images") == runtime.images
                and self.state.get("project") == runtime.project and self.state.get("region") == runtime.region
                and self.state.get("context") == runtime.context and self.state.get("namespace") == runtime.namespace,
                "ha-recovery-environment-mismatch")
        self.observation = None

    def save(self):
        write_signed(self.runtime.output / "sql-ha-state.json", self.state, self.key, self.signer)
        if self.observation is not None:
            write_signed(self.runtime.output / "sql-ha.json", self.observation, self.key, self.signer)

    def cloud(self, *args, timeout=90):
        raw = invoke(["gcloud", "sql", *args, "--project", self.runtime.project,
                      "--format=json", "--quiet"], timeout=timeout)
        return json.loads(raw)

    def profile(self, *, require_standby=True):
        return ha_profile(self.cloud("instances", "describe", self.state["source"]),
                          self.runtime.project, self.runtime.region, self.state["source"], require_standby=require_standby)

    def idle(self):
        rows = self.cloud("operations", "list", "--instance", self.state["source"], "--filter=status!=DONE")
        require(isinstance(rows, list) and not rows, "source-has-active-operations")

    def preflight(self):
        self.runtime.progress("Checking regional Cloud SQL, running processes, datasources and OAuth")
        profile = self.profile()
        self.idle()
        services = self.runtime.ready()
        processes = self.runtime.process_identities()
        datasources, _ = self.runtime.datasource_bindings(profile)
        authorization = self.runtime.authorize()
        self.state.update(source_profile=profile, processes=processes, datasources=datasources)
        self.runtime.recovery_checkpoint()
        self.save()
        return {"source_profile": profile, "services": services, "processes": processes,
                "datasources": datasources, "authorization": authorization}

    def same_processes(self):
        current = self.runtime.process_identities()
        require(current == self.state["processes"], "application-process-changed-during-ha-drill")
        return current

    def submit(self):
        require(self.state.get("operation") is None, "ha-intent-already-exists-use-recover")
        self.same_processes()
        self.idle()
        require(self.profile() == self.state["source_profile"], "source-changed-before-failover")
        self.state["operation"] = {"name": None, "requested_at": utc(), "target": self.state["source"]}
        self.save()  # A lost response leaves an explicit uncertain intent, never a blind retry.
        response = self.cloud("instances", "failover", self.state["source"], "--async")
        require(isinstance(response, dict) and re.fullmatch(r"[a-zA-Z0-9-]{1,100}", response.get("name", "")),
                "ha-operation-name-missing-inspect-saved-intent")
        self.state["operation"]["name"] = response["name"]
        self.save()

    def wait_operation(self, timeout=1800):
        intent = self.state.get("operation")
        require(intent and intent.get("name"), "ha-submission-uncertain-inspect-source-operations")
        deadline, failures = time.monotonic() + timeout, 0
        while True:
            remaining = deadline - time.monotonic()
            require(remaining > 0, "ha-operation-timeout-use-recover")
            try:
                operation = self.cloud("operations", "describe", intent["name"], timeout=min(90, remaining))
            except JourneyFailure as exc:
                failures += 1
                remaining = deadline - time.monotonic()
                retry = str(exc) in RETRYABLE_STATUS_READ_ERRORS and failures <= STATUS_READ_RETRY_LIMIT and remaining > 0
                delay = min(2 ** failures, remaining) if retry else 0
                diagnostic = intent.setdefault("status_read_failures", {"count": 0, "recent": []})
                diagnostic["count"] += 1
                diagnostic["recent"] = (diagnostic["recent"] + [{"reason": str(exc), "observed_at": utc(),
                    "retry_scheduled": retry, "retry_delay_seconds": delay}])[-5:]
                self.save()
                require(time.monotonic() < deadline, "ha-operation-timeout-use-recover")
                if not retry:
                    raise
                self.runtime.progress("Cloud SQL status read failed; retrying the same saved failover operation")
                time.sleep(min(delay, max(0, deadline - time.monotonic())))
                continue
            require(time.monotonic() < deadline, "ha-operation-timeout-use-recover")
            require(isinstance(operation, dict) and operation.get("name") == intent["name"]
                    and operation.get("targetId") == self.state["source"]
                    and operation.get("targetProject") == self.runtime.project
                    and operation.get("operationType") == "FAILOVER", "ha-operation-identity-mismatch")
            intent["observation"] = {k: operation[k] for k in
                ("status", "operationType", "insertTime", "startTime", "endTime") if k in operation}
            intent["observation"]["has_error"] = bool(operation.get("error"))
            self.save()
            if operation.get("status") == "DONE":
                require(not operation.get("error"), "ha-provider-operation-failed")
                return operation
            time.sleep(min(10, max(0, deadline - time.monotonic())))

    def promoted(self):
        after, before = self.profile(require_standby=False), self.state["source_profile"]
        require(unchanged_endpoint(before, after), "ha-source-endpoint-or-identity-changed")
        require(after["primary_zone"] == before["standby_zone"]
                and after["standby_zone"] == before["primary_zone"], "ha-standby-promotion-not-observed")
        return after

    def wait_readiness(self, *, same_processes=True, timeout=600):
        deadline = time.monotonic() + timeout
        while True:
            if same_processes:
                self.same_processes()
            try:
                services = self.runtime.ready()
                require(time.monotonic() < deadline, "ha-readiness-timeout")
                return services
            except JourneyFailure as exc:
                if str(exc) not in {"service-not-ready", "service-http-readiness-failed", "http-transport-failed", "ha-transient-read-failed",
                                    "service-port-forward-unavailable", "running-container-image-or-readiness-mismatch"}:
                    raise
            require(time.monotonic() < deadline, "ha-readiness-timeout")
            time.sleep(min(5, max(0, deadline - time.monotonic())))

    def customer_state(self):
        response = self.runtime.request("customer", "GET", "/api/v1/customer/" + quote(self.runtime.owner, safe=""), "owner")
        require(response.status == 200, "ha-customer-read-failed")
        row = response.json()
        require(isinstance(row, dict) and row.get("customerId") == self.runtime.owner
                and row.get("customerOtherDetails") == "lightyear-synthetic-journey-owner", "ha-customer-identity-mismatch")
        return hashed(row)

    def prepare(self, journey):
        self.runtime.progress("Preparing marked accounts, acknowledged transfers and durable Checks messages")
        _, jdbc = self.runtime.datasource_bindings(self.state["source_profile"])
        self.runtime.create_probe(jdbc_url=jdbc)
        journey.customer()
        try:
            journey.prepare_accounts()
        finally:
            # Partial fixture IDs are useful after interruption, without replaying creation.
            self.state["fixture_account_ids"] = list(journey.accounts)
            self.save()
        transfer = journey.success("ha-before", 25)
        deposit, clearance = journey.deposit(), journey.clearance()
        checkpoint = {"account_state_sha256": hashed(journey.state()), "customer_state_sha256": self.customer_state(),
            "deposit_id": journey.deposit_id, "clearance_id": journey.clear_id,
            "deposit_journal_id": journey.deposit_journal, "captured_at": utc()}
        self.state["checkpoint"] = checkpoint
        self.save()
        return {"transfer": transfer, "deposit": deposit, "clearance": clearance, "checkpoint": checkpoint}

    def reconnect(self, journey):
        self.runtime.progress("Checking automatic reconnection, acknowledged data, replay and new transactions")
        checkpoint = self.state["checkpoint"]
        self.wait_readiness()
        deadline = time.monotonic() + 600
        while True:
            self.same_processes()
            try:
                authorization = self.runtime.authorize()  # Fresh tokens, not pre-failover cached tokens.
                account_state = hashed(journey.state())
                customer_state = self.customer_state()
                require(time.monotonic() < deadline, "ha-reconnection-timeout")
                break
            except JourneyFailure as exc:
                # Only read paths and token issuance can be retried here. A
                # missing row, invalid token or changed ledger fails immediately.
                if str(exc) not in {"http-transport-failed", "ha-transient-read-failed", "service-port-forward-unavailable"}:
                    raise
            require(time.monotonic() < deadline, "ha-reconnection-timeout")
            time.sleep(min(5, max(0, deadline - time.monotonic())))
        require(account_state == checkpoint["account_state_sha256"], "ha-acknowledged-account-state-lost")
        require(customer_state == checkpoint["customer_state_sha256"], "ha-customer-state-changed")
        for identifier in (journey.deposit_id, journey.clear_id):
            require(self.runtime.queue(identifier).get("state") == "PROCESSED", "ha-acknowledged-message-state-lost")
        replay = journey.transfer(0, 1, 25, "ha-before")
        require(replay.status == 200 and hashed(journey.state()) == checkpoint["account_state_sha256"],
                "ha-transfer-replay-created-extra-effects")
        self.state["post_failover_writes_started_at"] = utc()
        self.save()
        transfer = journey.success("ha-after", 7)
        journey.deposit_id, journey.clear_id = journey.message_id("ha-after-deposit"), journey.message_id("ha-after-clearance")
        deposit, clearance = journey.deposit(), journey.clearance()
        credit, chat = journey.credit(), journey.chat()
        services = self.runtime.ready()
        datasources, _ = self.runtime.datasource_bindings(self.state["source_profile"])
        require(datasources == self.state["datasources"], "ha-datasource-bindings-changed")
        final_state = hashed(journey.state())
        processes = self.same_processes()
        return {"services": services, "processes": processes, "authorization": authorization,
            "acknowledged_state_matches": True, "transfer_replay_no_extra_effects": True,
            "new_transfer": transfer, "new_deposit": deposit, "new_clearance": clearance,
            "credit": credit, "chat": chat, "final_account_state_sha256": final_state}

    def cleanup(self, *, observe_operation=False):
        errors, operation_observed, services = [], self.state.get("operation") is None, None
        if observe_operation and self.state.get("operation"):
            try:
                self.wait_operation()
                self.promoted()
                operation_observed = True
            except (Exception, KeyboardInterrupt) as exc:
                errors.append({"stage": "failover-observation", "reason": reason(exc)})
        try:
            services = self.wait_readiness(same_processes=False)
        except (Exception, KeyboardInterrupt) as exc:
            errors.append({"stage": "application-readiness", "reason": reason(exc)})
        try:
            restored = self.runtime.close()
            require(restored.get("status") == "restored", "ha-probe-or-tunnel-cleanup-failed")
        except (Exception, KeyboardInterrupt) as exc:
            errors.append({"stage": "probe-and-tunnel-cleanup", "reason": reason(exc)})
        return {"status": "failed" if errors else "restored", "errors": errors,
            "services": services, "operation_completion_observed": operation_observed,
            "applications_restarted_by_drill": False, "failback_requested": False,
            "fixture_retained": True, "remaining_stopped_services": []}

    def execute(self, *, preflight_only=False):
        require(self.state.get("operation") is None, "ha-intent-already-exists-use-recover")
        self.observation = {"schema_version": "1.0", "observation_type": OBSERVATION_TYPE,
            "run_id": self.runtime.run_id, "started_at": utc(), "status": "running",
            "bindings": self.state.get("bindings", {}), "ms65_complete": False, "ms66_complete": False,
            "ms67_complete": False, "credentials_persisted": False, "raw_database_rows_persisted": False,
            "scope": "controlled Cloud SQL standby failover and selected service HTTP paths; all 16 process identities",
            "not_proven": ["pitr-rto", "continuous-write-rpo", "every-replica-connection-pool", "zone-outage",
                           "gke-node-recovery", "full-ms67-qualification"],
            "timing_scope": "before failover submission through provider, process, data and business validation; includes polling",
            "recovery_limit_seconds": RECOVERY_LIMIT_SECONDS}
        began, stage = None, "preflight"
        try:
            self.observation["preflight"] = self.preflight()
            self.save()
            if preflight_only:
                self.observation["status"] = "preflight-passed"
            else:
                journey = Journeys(self.runtime, self.runtime.run_id)
                stage = "synthetic-checkpoint"
                self.observation["before"] = self.prepare(journey)
                self.save()
                self.runtime.progress("Submitting one Cloud SQL HA failover; applications remain running")
                began = time.monotonic()
                self.observation["incident_declared_at"] = utc()
                stage = "failover-submission"
                self.submit()
                stage = "failover-observation"
                self.wait_operation()
                self.observation["promoted_profile"] = self.promoted()
                stage = "application-reconnection"
                self.observation["after"] = self.reconnect(journey)
                duration = time.monotonic() - began
                self.observation.update(validated_at=utc(), recovery_seconds=math.ceil(duration),
                    recovery_within_limit=duration <= RECOVERY_LIMIT_SECONDS)
                require(duration <= RECOVERY_LIMIT_SECONDS, "ha-application-recovery-exceeds-600-seconds")
                self.observation["status"] = "passed-cloud-sql-ha-failover"
        except (Exception, KeyboardInterrupt) as exc:
            self.observation.update(status="failed", reason=reason(exc), failure_stage=stage)
            if began is not None:
                self.observation["elapsed_before_cleanup_seconds"] = round(time.monotonic() - began, 6)
        finally:
            # A preflight must never create or delete a probe. Close only local tunnels.
            if preflight_only:
                errors = []
                for service in list(self.runtime.forwards):
                    try:
                        self.runtime.close_forward(service)
                    except (Exception, KeyboardInterrupt) as exc:
                        errors.append({"stage": "local-tunnel-cleanup", "reason": reason(exc)})
                recovery = {"status": "failed" if errors else "restored", "errors": errors, "mutations_requested": False}
            else:
                operation = self.state.get("operation") or {}
                recovery = self.cleanup(observe_operation=bool(operation) and
                    operation.get("observation", {}).get("status") != "DONE")
                if operation.get("observation", {}).get("status") == "DONE":
                    recovery["operation_completion_observed"] = True
            self.observation.update(recovery=recovery, operation=self.state.get("operation"), finished_at=utc())
            if recovery["status"] != "restored":
                self.observation["status"] = "failed"
            self.save()
        return self.observation
