"""Owned AlloyDB backup/PITR restores with measured, unchanged acceptance limits.

Reuse the existing read-only snapshot/probe and application recovery machinery.
Provider operations and identities are explicitly AlloyDB; no Cloud SQL aliases.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import math
import time

from .cloudbank_journeys import JourneyFailure, SERVICES, hashed, require
from .cloudbank_managed_target import observe_target, validate_profile
from .cloudbank_journeys_gke import command
from .cloudbank_secret_rotation_gke import Journal
from .cloudbank_sql_recovery import SqlRecovery, SNAPSHOT_SQL, epoch, utc, verified
from .cloudbank_recovery_policy import recovery_acceptance_policy
from .contracts import sign, content_hash

TYPE = "lightyear-alloydb-platform-database-recovery"
# Managed extension catalogs are provider metadata, not application relations.
# Exclude only objects PostgreSQL itself records as extension-owned. All other
# persistent tables, materialized views, partitions and sequences remain covered.
APPLICATION_SNAPSHOT_SQL = SNAPSHOT_SQL.replace("n.nspname <> 'information_schema'",
    "n.nspname <> 'information_schema' AND NOT EXISTS (SELECT 1 FROM pg_depend ed "
    "WHERE ed.classid='pg_class'::regclass AND ed.objid=c.oid AND ed.deptype='e' "
    "AND ed.refclassid='pg_extension'::regclass)")

# PostgreSQL may WAL-log future sequence allocations. Re-log the *unchanged*
# current counters while writers are quiesced, before selecting the backup point.
# No table rows, counter values, or credentials are exported by this statement.
SEQUENCE_CHECKPOINT_SQL = r"""
BEGIN READ WRITE;
SET LOCAL synchronous_commit = on;
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM pg_stat_activity WHERE datname=current_database()
  AND usename=current_user AND pid<>pg_backend_pid() AND backend_type='client backend')
THEN RAISE EXCEPTION 'concurrent application sessions prevent sequence checkpoint'; END IF;
END $$;
SELECT format($q$SELECT json_build_object('sequence',%L,'sha256',
encode(sha256(convert_to(json_build_array(setval(%L::regclass,last_value,is_called),is_called)::text,'UTF8')),'hex'))
FROM %I.%I$q$,n.nspname||'.'||c.relname,format('%I.%I',n.nspname,c.relname),n.nspname,c.relname)
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema' AND c.relkind='S'
AND NOT EXISTS (SELECT 1 FROM pg_depend ed WHERE ed.classid='pg_class'::regclass
AND ed.objid=c.oid AND ed.deptype='e' AND ed.refclassid='pg_extension'::regclass)
ORDER BY n.nspname,c.relname
\gexec
COMMIT;
"""


class AlloyRecovery(SqlRecovery):
    snapshot_sql = APPLICATION_SNAPSHOT_SQL

    def __init__(self, runtime, profile, key, signer, prefix, *, state=None, generation="0"):
        validate_profile(profile)
        require(profile["provider"] == "alloydb-postgresql", "alloydb-recovery-provider-required")
        source = profile["resource"].split("/")[-3]
        super().__init__(runtime, source, key, signer)
        self.profile, self.prefix = profile, prefix.rstrip("/")
        self.region_path = f"projects/{runtime.project}/locations/{runtime.region}"
        self.cluster_path = self.region_path + "/clusters/" + source
        self.journal = Journal(runtime.output / "alloydb-recovery-state.json",
            self.prefix + "/alloydb-recovery-state.json", runtime.project, key, signer, generation=generation)
        if state is not None:
            verified(state, key)
            require(state.get("state_type") == TYPE and state.get("profile") == profile
                    and state.get("run_id") == runtime.run_id and state.get("images") == runtime.images
                    and state.get("context") == runtime.context and state.get("namespace") == runtime.namespace,
                    "alloydb-recovery-saved-context-mismatch")
            self.state = {k: v for k, v in state.items() if k not in {"signature", "content_sha256"}}
            for kind, record in self.state["targets"].items():
                expected = "ly-alloy-" + kind + "-" + hashed(runtime.run_id)[:16]
                require(kind in {"pitr", "backup"} and record["name"] == expected
                        and record["resource"] == self.region_path + "/clusters/" + expected,
                        "alloydb-recovery-saved-target-mismatch")
        else:
            self.state.update(state_type=TYPE, profile=profile, targets={}, backup=None,
                              source_cluster_uid=None, cleanup_complete=False, alloydb_platform_qualified=False)

    def save(self):
        self.journal.write(self.state)

    def cloud(self, *args, timeout=120):
        raw = command(["gcloud", "--quiet", "--project=" + self.runtime.project, "alloydb", *args,
                       "--region=" + self.runtime.region, "--format=json"], timeout=timeout)
        return json.loads(raw) if raw.strip() else {}

    def source_guard(self):
        cluster = self.cloud("clusters", "describe", self.state["source"])
        require(cluster["name"] == self.cluster_path and cluster["state"] == "READY"
                and cluster["databaseVersion"] == self.profile["database_version"]
                and cluster.get("continuousBackupConfig", {}).get("enabled") is True
                and cluster.get("automatedBackupPolicy", {}).get("enabled") is True,
                "alloydb-source-or-backup-policy-invalid")
        if self.state["source_cluster_uid"]:
            require(cluster["uid"] == self.state["source_cluster_uid"], "alloydb-source-uid-drift")
        else:
            self.state["source_cluster_uid"] = cluster["uid"]
            self.state["network"] = cluster["networkConfig"]["network"]
            self.save()
        return cluster

    def submit(self, label, target, *args):
        require(label not in self.state["operations"], "alloydb-operation-already-submitted-or-uncertain")
        record = {"target": target, "requested_at": utc(), "name": None}
        self.state["operations"][label] = record
        self.save()  # Durable intent precedes mutation; never blindly resubmit.
        operation = self.cloud(*args, "--async")
        require(operation.get("name", "").startswith(self.region_path + "/operations/"),
                "alloydb-operation-identity-invalid")
        record["name"] = operation["name"]
        self.save()
        return label

    def wait(self, label, timeout=2400):
        record = self.state["operations"][label]
        require(record.get("name"), "alloydb-operation-response-uncertain")
        deadline = time.monotonic() + timeout
        while True:
            operation = self.cloud("operations", "describe", record["name"].rsplit("/", 1)[1])
            require(operation.get("name") == record["name"] and
                    operation.get("metadata", {}).get("target") == record["target"],
                    "alloydb-operation-target-mismatch")
            if operation.get("done"):
                record["result"] = operation
                self.save()
                require(not operation.get("error"), "alloydb-operation-failed-" + label)
                return operation
            require(time.monotonic() < deadline, "alloydb-operation-timeout-" + label)
            self.runtime.progress("ALLOYDB_OPERATION=" + label + "; waiting for provider completion")
            time.sleep(10)

    def discover(self):
        self.source_guard()
        target = observe_target(self.runtime, self.profile, command)
        self.state["managed_target"] = target
        for service, row in target["services"].items():
            if row["connection"]:
                self.databases.setdefault(row["connection"]["database"], "cloudbank-" + service + "-external")
        require(bool(self.databases), "alloydb-application-databases-required")
        self.state["coverage"] = {"database_names_sha256": hashed(sorted(self.databases)),
            "database_count": len(self.databases), "query_sha256": hashed(self.snapshot_sql),
            "scope": "all non-extension-owned persistent application tables, materialized views and sequences; no raw rows exported"}
        self.save()
        return target["database"]["address"]

    def checkpoint_sequences(self, address, before):
        require(self.runtime.stopped == set(SERVICES)
                and all(not self.runtime.pods(s) for s in SERVICES), "sequence-checkpoint-requires-quiesced-writers")
        self.source_guard()
        require(address == self.state["managed_target"]["database"]["address"], "sequence-checkpoint-source-address-drift")
        record = {"status": "prepared", "before": before, "query_sha256": hashed(SEQUENCE_CHECKPOINT_SQL),
                  "method": "setval-to-current-value-and-is-called-while-quiesced", "sequence_hashes": {}}
        self.state["sequence_checkpoint"] = record
        self.save()
        self.connect_probes(address)
        for database, probe in self.probes.items():
            self.owned_resource(probe)
            raw = self.runtime.kubectl("exec", "-i", probe["name"], "--", "env", "PGHOST=" + address,
                "PGOPTIONS=-c default_transaction_read_only=off -c statement_timeout=60000",
                "psql", "-X", "-qAt", "--no-password", "--set=ON_ERROR_STOP=1", data=SEQUENCE_CHECKPOINT_SQL, timeout=90)
            rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
            require(len(rows) == before["databases"][hashed(database)]["sequence_count"]
                    and all(set(row) == {"sequence", "sha256"} for row in rows), "sequence-checkpoint-coverage-invalid")
            record["sequence_hashes"][hashed(database)] = rows
        record["after"] = self.snapshot(address)
        record["status"] = "passed" if record["after"] == before else "failed"
        self.save()
        require(record["status"] == "passed", "sequence-checkpoint-changed-application-state")
        return record

    def start_restore(self, kind, selector):
        name = "ly-alloy-" + kind + "-" + hashed(self.runtime.run_id)[:16]
        require(name != self.state["source"], "alloydb-source-restore-forbidden")
        existing = self.cloud("clusters", "list")
        resource = self.region_path + "/clusters/" + name
        require(not any(row["name"] == resource for row in existing), "alloydb-restore-target-must-be-absent")
        self.state["targets"][kind] = {"name": name, "resource": resource, "uid": None,
                                       "absent_before": True, "deleted": False}
        self.save()
        self.submit(kind, resource, "clusters", "restore", name, "--network=" + self.state["network"], *selector)

    def target_guard(self, kind):
        record = self.state["targets"][kind]
        require(record["absent_before"] and record["name"] != self.state["source"], "alloydb-owned-restore-required")
        current = self.cloud("clusters", "describe", record["name"])
        require(current["name"] == record["resource"] and current["networkConfig"]["network"] == self.state["network"],
                "alloydb-restored-cluster-identity-invalid")
        if record["uid"]:
            require(current["uid"] == record["uid"], "alloydb-restored-cluster-uid-drift")
        else:
            op = self.state["operations"][kind]
            require(op.get("result", {}).get("done") is True and not op["result"].get("error")
                    and epoch(current["createTime"]) >= epoch(op["requested_at"]), "alloydb-restore-ownership-unproven")
            record["uid"] = current["uid"]
            self.save()
        return current

    def provision_primary(self, kind):
        self.wait(kind)
        cluster = self.target_guard(kind)
        require(cluster["state"] == "READY", "alloydb-restored-cluster-not-ready")
        name = self.state["targets"][kind]["name"]
        resource = cluster["name"] + "/instances/primary"
        self.submit(kind + "-primary", resource, "instances", "create", "primary", "--cluster=" + name,
                    "--instance-type=PRIMARY", "--availability-type=REGIONAL", "--cpu-count=2", "--ssl-mode=ENCRYPTED_ONLY")

    def finish_restore(self, kind):
        if kind + "-primary" not in self.state["operations"]:
            self.provision_primary(kind)
        self.wait(kind + "-primary")
        cluster = self.target_guard(kind)
        name = self.state["targets"][kind]["name"]
        resource = cluster["name"] + "/instances/primary"
        primary = self.cloud("instances", "describe", "primary", "--cluster=" + name)
        address = primary["ipAddress"]
        require(primary["name"] == resource and primary["state"] == "READY" and
                primary["availabilityType"] == "REGIONAL" and
                address != self.state["managed_target"]["database"]["address"], "alloydb-restore-instance-invalid")
        self.state["targets"][kind]["primary_uid"] = primary["uid"]
        self.save()
        return self.snapshot(address)

    def cleanup(self):
        self.remove_resources()
        for kind, record in self.state["targets"].items():
            if record["deleted"]:
                continue
            if kind + "-delete" in self.state["operations"]:
                self.wait(kind + "-delete")
                require(not any(c["name"] == record["resource"] for c in self.cloud("clusters", "list")),
                        "alloydb-restore-deletion-unverified")
                record["deleted"] = True
                self.save()
                continue
            op = self.state["operations"].get(kind)
            require(op and op.get("name"), "alloydb-restore-submission-uncertain")
            self.wait(kind)
            self.target_guard(kind)
            if kind + "-delete-primary" in self.state["operations"]:
                self.wait(kind + "-delete-primary")
            instances = self.cloud("instances", "list", "--cluster=" + record["name"])
            require(len(instances) <= 1, "alloydb-unexpected-restore-instances")
            if instances:
                instance = instances[0]
                self.wait(kind + "-primary")
                if not record.get("primary_uid"):
                    # A completed, target-bound create operation also supplies
                    # the original UID if the following instance read was lost.
                    record["primary_uid"] = self.state["operations"][kind + "-primary"]["result"].get("response", {}).get("uid")
                require(instance["name"] == record["resource"] + "/instances/primary"
                        and record.get("primary_uid") and instance.get("uid") == record["primary_uid"],
                        "alloydb-unowned-or-recreated-instance")
                self.save()
                self.submit(kind + "-delete-primary", instance["name"], "instances", "delete", "primary", "--cluster=" + record["name"])
                self.wait(kind + "-delete-primary")
            self.target_guard(kind)
            self.submit(kind + "-delete", record["resource"], "clusters", "delete", record["name"])
            self.wait(kind + "-delete")
            require(not any(c["name"] == record["resource"] for c in self.cloud("clusters", "list")),
                    "alloydb-restore-deletion-unverified")
            record["deleted"] = True
            self.save()
        self.state["cleanup_complete"] = True
        self.save()

    def execute(self):
        result = {"schema_version": "1.0", "observation_type": TYPE, "run_id": self.runtime.run_id,
            "status": "failed", "environment": self.runtime.environment(), "images": self.runtime.images,
            "profile": self.profile, "acceptance_policy": recovery_acceptance_policy(),
            "credentials_persisted": False, "raw_database_rows_persisted": False,
            "production_ready": False, "alloydb_platform_qualified": False}
        self.observation = result
        try:
            address = self.discover()
            result.update(managed_target=self.state["managed_target"], source_cluster_uid=self.state["source_cluster_uid"])
            self.runtime.ready()
            self.snapshot(address)
            self.runtime.progress("ALLOYDB_RECOVERY=quiescing synthetic application writers")
            self.quiesce()
            before = self.snapshot(address)
            result["sequence_checkpoint"] = self.checkpoint_sequences(address, before)
            checkpoint = utc()
            result.update(checkpoint=before, checkpoint_captured_at=checkpoint, coverage=self.state["coverage"])
            name = "ly-alloy-backup-" + hashed(self.runtime.run_id)[:16]
            self.source_guard()
            self.submit("backup-create", self.region_path + "/backups/" + name, "backups", "create", name,
                        "--cluster=" + self.state["source"])
            self.wait("backup-create")
            backup = self.cloud("backups", "describe", name)
            require(backup["state"] == "READY" and backup["clusterName"] == self.cluster_path
                    and epoch(backup["createTime"]) >= epoch(checkpoint), "alloydb-backup-binding-invalid")
            self.state["backup"] = backup
            result["backup"] = {"metadata": backup, "metadata_sha256": hashed(backup), "retained": True,
                                "managed_backup_bytes_sha256": None}
            self.save()
            require(self.snapshot(address) == before, "alloydb-source-changed-during-checkpoint")
            # Allow recent WAL to reach continuous recovery; record a real
            # requested point, not a claimed provider 'latest recovery time'.
            self.runtime.progress("ALLOYDB_RECOVERY=waiting 35 seconds before selecting a recent PITR point")
            time.sleep(35)
            incident = datetime.now(timezone.utc)
            point = (incident - timedelta(seconds=30)).isoformat().replace("+00:00", "Z")
            require(epoch(point) > epoch(checkpoint), "alloydb-pitr-point-precedes-checkpoint")
            began = time.monotonic()
            self.start_restore("pitr", ["--source-cluster=" + self.state["source"], "--point-in-time=" + point])
            # Start provider provisioning before restoring application writers.
            # Both can progress concurrently, with one serialized local journal
            # and the same end-to-end recovery timer.
            self.provision_primary("pitr")
            self.restore_apps()
            restored = self.finish_restore("pitr")
            rto = math.ceil(time.monotonic() - began)
            result["pitr"] = {"incident_declared_at": incident.isoformat(), "point_in_time": point,
                "recovery_point_age_seconds": 30, "database_rto_seconds": rto, "restored_state": restored,
                "state_matches": restored == before, "rto_within_limit": rto <= 630, "rpo_within_limit": True}
            self.state["measured"] = result
            self.save()
            began = time.monotonic()
            self.start_restore("backup", ["--backup=" + backup["name"]])
            restored = self.finish_restore("backup")
            rto = math.ceil(time.monotonic() - began)
            result["backup_restore"] = {"database_rto_seconds": rto, "restored_state": restored,
                "state_matches": restored == before, "rto_within_limit": rto <= 600,
                "timing_scope": "fresh cluster and regional primary provisioning through exact read-only state validation"}
            result["status"] = "passed-isolated-alloydb-recovery" if all(
                result[k]["state_matches"] and result[k]["rto_within_limit"] for k in ("pitr", "backup_restore")) else "failed"
        except (Exception, KeyboardInterrupt) as exc:
            result["reason"] = str(exc) if isinstance(exc, JourneyFailure) else type(exc).__name__
        finally:
            errors = []
            for name, action in (("application-restoration", self.restore_apps), ("isolated-cleanup", self.cleanup)):
                try:
                    action()
                except (Exception, KeyboardInterrupt) as exc:
                    errors.append(name + ":" + (str(exc) if isinstance(exc, JourneyFailure) else type(exc).__name__))
            result["recovery"] = {"status": "restored" if not errors else "recovery-required", "errors": errors}
            if errors:
                result["status"] = "failed"
            result["operations"] = self.state["operations"]
            result["targets"] = self.state["targets"]
            self.state["measured"] = result
            self.save()
        return sign(result, self.key, self.signer)


def verify_recovery(value, key, profile, images, environment):
    verified(value, key)
    require(value.get("observation_type") == TYPE and value.get("status") == "passed-isolated-alloydb-recovery"
            and value.get("profile") == profile and value.get("images") == images
            and value.get("environment") == environment, "alloydb-recovery-context-or-status-invalid")
    validate_profile(profile)
    require(profile["provider"] == "alloydb-postgresql" and value.get("source_cluster_uid")
            and value.get("acceptance_policy") == recovery_acceptance_policy()
            and all(value.get(k) is False for k in ("credentials_persisted", "raw_database_rows_persisted",
                                                   "production_ready", "alloydb_platform_qualified")),
            "alloydb-recovery-scope-invalid")
    managed = value.get("managed_target", {})
    require(managed.get("content_sha256") == content_hash(managed)
            and managed.get("profile_sha256") == profile["content_sha256"]
            and managed.get("images_sha256") == hashed(images)
            and managed.get("environment") == environment
            and managed.get("database", {}).get("resource") == profile["resource"], "alloydb-recovery-managed-binding-invalid")
    checkpoint = value.get("checkpoint", {})
    require(checkpoint.get("databases") and checkpoint.get("state_sha256") == hashed(checkpoint["databases"]),
            "alloydb-recovery-checkpoint-invalid")
    sequence_checkpoint = value.get("sequence_checkpoint", {})
    require(sequence_checkpoint.get("status") == "passed"
            and sequence_checkpoint.get("before") == checkpoint and sequence_checkpoint.get("after") == checkpoint
            and sequence_checkpoint.get("query_sha256") == hashed(SEQUENCE_CHECKPOINT_SQL)
            and set(sequence_checkpoint.get("sequence_hashes", {})) == set(checkpoint["databases"])
            and all(len(rows) == checkpoint["databases"][database]["sequence_count"]
                    for database, rows in sequence_checkpoint["sequence_hashes"].items()),
            "alloydb-recovery-unchanged-sequence-checkpoint-required")
    backup = value.get("backup", {})
    require(backup.get("metadata_sha256") == hashed(backup.get("metadata"))
            and backup.get("metadata", {}).get("clusterName") == profile["resource"].rsplit("/instances/", 1)[0]
            and backup["metadata"].get("state") == "READY" and backup.get("retained") is True,
            "alloydb-recovery-backup-invalid")
    for kind, limit in (("pitr", 630), ("backup_restore", 600)):
        row = value.get(kind, {})
        require(row.get("restored_state") == checkpoint and row.get("state_matches") is True
                and type(row.get("database_rto_seconds")) is int and 0 < row["database_rto_seconds"] <= limit
                and row.get("rto_within_limit") is True, "alloydb-recovery-measured-limit-or-state-failed-" + kind)
    pitr = value["pitr"]
    require(pitr.get("rpo_within_limit") is True and 0 <= pitr.get("recovery_point_age_seconds", -1) <= 60
            and abs(epoch(pitr["incident_declared_at"]) - epoch(pitr["point_in_time"]) - pitr["recovery_point_age_seconds"]) < .01
            and epoch(pitr["point_in_time"]) > epoch(value["checkpoint_captured_at"]), "alloydb-recovery-rpo-invalid")
    require(value.get("recovery") == {"status": "restored", "errors": []}
            and set(value.get("targets", {})) == {"pitr", "backup"}
            and len({r.get("uid") for r in value["targets"].values()}) == 2
            and all(r.get("uid") and r.get("uid") != value["source_cluster_uid"] and r.get("primary_uid")
                    and r.get("absent_before") is True and r.get("deleted") is True
                    for r in value["targets"].values()), "alloydb-recovery-cleanup-or-isolation-invalid")
    for name in ("backup-create", "pitr", "pitr-primary", "pitr-delete-primary", "pitr-delete",
                 "backup", "backup-primary", "backup-delete-primary", "backup-delete"):
        operation = value.get("operations", {}).get(name, {})
        result = operation.get("result", {})
        region_path = profile["resource"].split("/clusters/", 1)[0]
        suffix = hashed(value["run_id"])[:16]
        if name == "backup-create":
            target = region_path + "/backups/ly-alloy-backup-" + suffix
            require(backup["metadata"].get("name") == target, "alloydb-recovery-backup-operation-binding-invalid")
        else:
            kind = name.split("-", 1)[0]
            target = region_path + "/clusters/ly-alloy-" + kind + "-" + suffix
            require(value["targets"][kind].get("resource") == target, "alloydb-recovery-owned-target-binding-invalid")
            if name.endswith("primary"):
                target += "/instances/primary"
        require(operation.get("name") and result.get("name") == operation["name"]
                and operation["name"].startswith(region_path + "/operations/") and operation.get("target") == target
                and result.get("done") is True and not result.get("error")
                and result.get("metadata", {}).get("target") == operation.get("target"),
                "alloydb-recovery-operation-incomplete-" + name)
    return value
