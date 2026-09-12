"""Controlled AlloyDB failover using the existing acknowledged business probes."""
from __future__ import annotations

import json
import math
import time

from .cloudbank_journeys import JourneyFailure, Journeys, require, hashed
from .cloudbank_journeys_gke import command
from .cloudbank_managed_target import ManagedGkeRuntime, observe_target, validate_profile
from .cloudbank_secret_rotation_gke import Journal
from .cloudbank_sql_ha import HaRuntime, SqlHa, reason
from .cloudbank_sql_recovery import utc, verified
from .contracts import sign

TYPE = "lightyear-alloydb-controlled-primary-failover"


class AlloyHaRuntime(HaRuntime, ManagedGkeRuntime):
    """Preserve no-restart guard and inspect the deployed namespace's secrets."""


class AlloyHa(SqlHa):
    def __init__(self, runtime, profile, key, signer, prefix):
        validate_profile(profile)
        require(profile["provider"] == "alloydb-postgresql", "alloydb-ha-provider-required")
        super().__init__(runtime, profile["resource"].split("/")[-3], key, signer)
        self.managed_profile = profile
        self.resource = profile["resource"]
        self.region_path = self.resource.split("/clusters/")[0]
        self.primary = self.resource.rsplit("/", 1)[1]
        self.state.update(state_type=TYPE, managed_profile=profile, alloydb_platform_qualified=False)
        self.journal = Journal(runtime.output / "alloydb-ha-state.json", prefix + "/alloydb-ha-state.json",
                               runtime.project, key, signer)

    def save(self):
        self.journal.write({**self.state, "observation": self.observation})

    def cloud(self, *args, timeout=120):
        return json.loads(command(["gcloud", "--quiet", "--project=" + self.runtime.project, "alloydb", *args,
                                  "--region=" + self.runtime.region, "--format=json"], timeout=timeout))

    def profile(self, *, require_standby=True):
        value = self.cloud("instances", "describe", self.primary, "--cluster=" + self.state["source"])
        cluster = self.cloud("clusters", "describe", self.state["source"])
        require(value["name"] == self.resource and value["state"] == "READY"
                and value["availabilityType"] == "REGIONAL" and value.get("instanceType") == "PRIMARY"
                and value.get("clientConnectionConfig", {}).get("sslConfig", {}).get("sslMode") == "ENCRYPTED_ONLY"
                and not value.get("publicIpAddress") and cluster["state"] == "READY", "alloydb-regional-private-primary-required")
        zones = sorted({r["zoneId"] for r in value.get("nodes", [])})
        require(len(zones) == 1 and zones[0].startswith(self.runtime.region + "-"), "alloydb-active-primary-zone-required")
        return {"resource": value["name"], "instance_uid": value["uid"], "cluster_uid": cluster["uid"],
                "private_ip": value["ipAddress"], "active_zone": zones[0], "availability_type": "REGIONAL",
                "network": cluster["networkConfig"]["network"], "database_version": cluster["databaseVersion"]}

    def idle(self):
        operations = self.cloud("operations", "list")
        require(not any(not r.get("done", False) and r.get("metadata", {}).get("target") in
                        {self.resource, self.resource.rsplit("/instances/", 1)[0]} for r in operations),
                "alloydb-ha-source-has-active-operations")

    def preflight(self):
        managed = observe_target(self.runtime, self.managed_profile, command)
        result = super().preflight()
        require(result["source_profile"]["private_ip"] == managed["database"]["address"], "alloydb-ha-address-drift")
        result["managed_target"] = managed
        return result

    def submit(self):
        require(self.state["operation"] is None, "alloydb-ha-submission-already-attempted")
        self.same_processes()
        self.idle()
        require(self.profile() == self.state["source_profile"], "alloydb-ha-source-drift")
        self.state["operation"] = {"name": None, "requested_at": utc(), "target": self.resource}
        self.save()
        operation = self.cloud("instances", "failover", self.primary, "--cluster=" + self.state["source"], "--async")
        require(operation.get("name", "").startswith(self.region_path + "/operations/"), "alloydb-ha-operation-invalid")
        self.state["operation"]["name"] = operation["name"]
        self.save()

    def wait_operation(self, timeout=1800):
        intent = self.state.get("operation")
        require(intent and intent.get("name"), "alloydb-ha-uncertain-submission-requires-reconciliation")
        deadline = time.monotonic() + timeout
        while True:
            operation = self.cloud("operations", "describe", intent["name"].rsplit("/", 1)[1])
            require(operation.get("name") == intent["name"] and operation.get("metadata", {}).get("target") == self.resource,
                    "alloydb-ha-operation-target-mismatch")
            if operation.get("done"):
                intent["result"] = operation
                intent["observation"] = {"status": "DONE", "has_error": bool(operation.get("error"))}
                self.save()
                require(not operation.get("error"), "alloydb-ha-provider-failover-failed")
                return operation
            require(time.monotonic() < deadline, "alloydb-ha-operation-timeout")
            self.runtime.progress("ALLOYDB_HA=waiting for the submitted primary failover")
            time.sleep(10)

    def promoted(self):
        after, before = self.profile(), self.state["source_profile"]
        require(all(after[k] == before[k] for k in before if k != "active_zone")
                and after["active_zone"] != before["active_zone"], "alloydb-ha-zone-promotion-or-endpoint-invalid")
        return after

    def execute(self):
        self.observation = {"schema_version": "1.0", "observation_type": TYPE, "run_id": self.runtime.run_id,
            "status": "running", "profile": self.managed_profile, "environment": self.runtime.environment(),
            "images": self.runtime.images, "bindings": self.state.get("bindings", {}),
            "scope": "controlled regional AlloyDB primary failover with acknowledged transaction and queue checks",
            "not_proven": ["unplanned-zone-outage", "continuous-write-rpo", "regional-disaster"],
            "credentials_persisted": False, "raw_database_rows_persisted": False,
            "alloydb_platform_qualified": False, "production_ready": False, "recovery_limit_seconds": 600}
        began = None
        try:
            self.observation["preflight"] = self.preflight()
            journey = Journeys(self.runtime, self.runtime.run_id)
            self.observation["before"] = self.prepare(journey)
            self.save()
            began = time.monotonic()
            self.observation["incident_declared_at"] = utc()
            self.submit()
            self.wait_operation()
            self.observation["promoted_profile"] = self.promoted()
            self.observation["after"] = self.reconnect(journey)
            seconds = math.ceil(time.monotonic() - began)
            self.observation.update(recovery_seconds=seconds, recovery_within_limit=seconds <= 600)
            require(seconds <= 600, "alloydb-ha-recovery-exceeds-600-seconds")
            self.observation["status"] = "passed-alloydb-primary-failover"
        except (Exception, KeyboardInterrupt) as exc:
            self.observation.update(status="failed", reason=reason(exc))
            if began:
                self.observation["elapsed_before_cleanup_seconds"] = math.ceil(time.monotonic() - began)
        finally:
            operation = self.state.get("operation") or {}
            recovery = self.cleanup(observe_operation=bool(operation) and not operation.get("result", {}).get("done"))
            if operation.get("result", {}).get("done") and not operation["result"].get("error"):
                recovery["operation_completion_observed"] = True
            self.observation.update(recovery=recovery, operation=self.state.get("operation"), finished_at=utc())
            if recovery["status"] != "restored":
                self.observation["status"] = "failed"
            self.save()
        return sign(self.observation, self.key, self.signer)


def verify_ha(value, key, profile, images, environment):
    verified(value, key)
    require(value.get("observation_type") == TYPE and value.get("status") == "passed-alloydb-primary-failover"
            and value.get("profile") == profile and value.get("images") == images
            and value.get("environment") == environment, "alloydb-ha-result-binding-invalid")
    before, after = value["preflight"]["source_profile"], value["promoted_profile"]
    require(before["resource"] == profile["resource"] and before["availability_type"] == "REGIONAL"
            and before["active_zone"] != after["active_zone"] and
            all(before[k] == after[k] for k in before if k != "active_zone"), "alloydb-ha-promotion-unproven")
    require(value["preflight"]["processes"] == value["after"]["processes"] and
            value["after"]["acknowledged_state_matches"] is True and value["after"]["transfer_replay_no_extra_effects"] is True
            and value["recovery_within_limit"] is True and 0 < value["recovery_seconds"] <= 600
            and value["recovery"]["status"] == "restored" and value["recovery"]["errors"] == []
            and value["recovery"]["operation_completion_observed"] is True, "alloydb-ha-recovery-unproven")
    require(all(value.get(k) is False for k in ("production_ready", "alloydb_platform_qualified", "credentials_persisted",
                                               "raw_database_rows_persisted")), "alloydb-ha-scope-invalid")
    return value
