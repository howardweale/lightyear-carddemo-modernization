"""Isolated Cloud SQL recovery drill; never a full MS65/MS67 admission receipt.

The source is quiesced for a bounded checkpoint. PITR and explicit backup restore
are checked independently against all configured application databases. Managed
backup metadata is identified honestly: its hash is not a backup-body checksum.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
from datetime import datetime, timezone
import ipaddress
import json
import math
from pathlib import Path
import re
import subprocess
import time
from urllib.parse import urlsplit

from .cloudbank_journeys import JourneyFailure, SERVICES, hashed, require
from .cloudbank_journeys_gke import GkeRuntime
from .contracts import content_hash, sign, verify_signature

STATE_TYPE = "lightyear-cloudbank-sql-recovery-state"
OBSERVATION_TYPE = "lightyear-cloudbank-isolated-sql-recovery"
NAME = re.compile(r"[a-z][a-z0-9-]{0,62}")


def utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def epoch(value: str) -> float:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(parsed.tzinfo is not None, "timestamp-timezone-required")
    return parsed.timestamp()


def recovery_point_age(incident: str, point: str, checkpoint: str) -> int:
    age = epoch(incident) - epoch(point)
    require(epoch(point) >= epoch(checkpoint) and 0 <= age <= 60,
            "pitr-recovery-point-age-exceeds-60-seconds-or-precedes-checkpoint")
    return math.ceil(age)


def select_recovery_point(checkpoint, query, observe, *, timeout=600, clock=None, now=None, pause=None):
    """Select one observed point after slow preparation, within a bounded wait.

    The accepted API response and its observation time are used by the clone
    request directly. Never replace an accepted point with an unchecked second
    read. Runtime clocks stay in memory; only UTC timestamps/durations are saved.
    """
    clock, now, pause = clock or time.monotonic, now or utc, pause or time.sleep
    began = clock()
    checkpoint_epoch = epoch(checkpoint)
    attempt = 0
    while True:
        attempt += 1
        requested_at, requested_clock = now(), clock()
        try:
            point = query()
            point_epoch = epoch(point)
        except (ValueError, TypeError, AttributeError, KeyError):
            observe({"attempt": attempt, "status": "failed", "reason": "invalid-recovery-time-response",
                     "query_started_at": requested_at, "observed_at": now()})
            raise JourneyFailure("pitr-recovery-time-response-invalid") from None
        except JourneyFailure as exc:
            observe({"attempt": attempt, "status": "failed", "reason": str(exc),
                     "query_started_at": requested_at, "observed_at": now()})
            raise
        selected_clock, incident = clock(), now()
        age = epoch(incident) - point_epoch
        reason = ("point-precedes-checkpoint" if point_epoch < checkpoint_epoch else
                  "point-in-future" if age < 0 else "point-too-old" if age > 60 else "accepted")
        elapsed = selected_clock - began
        expired = elapsed >= timeout
        observe({"attempt": attempt, "status": "timed-out" if expired else "accepted" if reason == "accepted" else "waiting",
                 "reason": reason, "checkpoint_captured_at": checkpoint, "latest_recovery_time": point,
                 "query_started_at": requested_at, "observed_at": incident,
                 "recovery_point_age_seconds": round(age, 6),
                 "point_after_checkpoint_seconds": round(point_epoch - checkpoint_epoch, 6),
                 "query_duration_seconds": round(selected_clock - requested_clock, 6),
                 "wait_elapsed_seconds": round(elapsed, 6), "maximum_age_seconds": 60})
        require(not expired, "pitr-recovery-window-timeout")
        if reason == "accepted":
            return point, incident, recovery_point_age(incident, point, checkpoint), selected_clock
        pause(min(10, timeout - elapsed))


def write_signed(path: Path, value: dict, key: str, signer: str):
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        temporary.chmod(0o600)
        json.dump(sign(value, key, signer), handle, indent=2, sort_keys=True)
        handle.write("\n")
    temporary.replace(path)


def verified(value: dict, key: str):
    require(isinstance(value, dict) and value.get("content_sha256") == content_hash(value)
            and verify_signature(value, key), "evidence-content-or-signature-invalid")
    return value


def invoke(argv, *, data=None, timeout=90, sensitive=False):
    """No shell. Secret/SQL output and errors never reach logs or exception text."""
    try:
        result = subprocess.run(argv, input=data, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise JourneyFailure("command-unavailable-or-timeout-inspect-saved-intent") from None
    if result.returncode:
        # API error codes help diagnose auth, quota and operation conflicts without
        # serializing arbitrary server messages, credentials or database content.
        codes = sorted(set(re.findall(r"\b(?:PERMISSION_DENIED|NOT_FOUND|ALREADY_EXISTS|"
            r"RESOURCE_EXHAUSTED|UNAUTHENTICATED|INVALID_ARGUMENT|OPERATION_IN_PROGRESS)\b", result.stderr)))
        no_account = "active account" in result.stderr.lower()
        hint = "active-account-required" if no_account else "-".join(codes).lower().replace("_", "-") or "exit-" + str(result.returncode)
        raise JourneyFailure("operator-command-failed-" + ("database-or-secret-access" if sensitive else hint[:70]))
    require(len(result.stdout) <= 8 * 1024 * 1024, "bounded-command-output-exceeded")
    return result.stdout


# Every returned cell is a count, a public schema identifier, or a digest; no row
# values leave PostgreSQL. Sorting row digests preserves duplicate multiplicity.
# row_security=off fails on filtering policies instead of hashing a partial view.
SNAPSHOT_SQL = r"""
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL timezone = 'UTC';
SET LOCAL datestyle = 'ISO, YMD';
SET LOCAL extra_float_digits = 3;
SET LOCAL row_security = off;
SET LOCAL statement_timeout = '60s';
SELECT json_build_object('unsupported', count(*)) FROM pg_class c
JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'
AND (c.relkind='f' OR (c.relkind IN ('r','m','p') AND c.relpersistence <> 'p'));
SELECT format($q$SELECT json_build_object('relation', %L, 'rows', count(*),
'sha256', encode(sha256(convert_to(coalesce(string_agg(h, '' ORDER BY h), ''), 'UTF8')), 'hex'))
FROM (SELECT encode(sha256(convert_to(to_jsonb(t)::text, 'UTF8')), 'hex') h FROM %I.%I t) v$q$,
n.nspname || '.' || c.relname, n.nspname, c.relname)
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema' AND c.relkind IN ('r','m','p')
ORDER BY n.nspname, c.relname
\gexec
SELECT format($q$SELECT json_build_object('sequence', %L,
'sha256', encode(sha256(convert_to(json_build_array(last_value,is_called)::text,'UTF8')),'hex'))
FROM %I.%I$q$, n.nspname || '.' || c.relname, n.nspname, c.relname)
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema' AND c.relkind='S'
ORDER BY n.nspname, c.relname
\gexec
SELECT json_build_object('schema_sha256', encode(sha256(convert_to(coalesce(jsonb_agg(x
ORDER BY x::text)::text,'[]'),'UTF8')),'hex')) FROM (
SELECT jsonb_build_array(n.nspname,c.relname,c.relkind,a.attnum,a.attname,
format_type(a.atttypid,a.atttypmod),a.attnotnull,pg_get_expr(d.adbin,d.adrelid)) x
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_attribute a ON a.attrelid=c.oid
LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum
WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema' AND c.relkind IN ('r','m','p','S')
AND a.attnum > 0 AND NOT a.attisdropped
) schema_columns;
COMMIT;
"""


def normalize_snapshot(raw: str) -> dict:
    records = [json.loads(line) for line in raw.splitlines() if line.strip()]
    require(records and records[0] == {"unsupported": 0}, "foreign-or-unlogged-tables-not-supported")
    records = records[1:]
    relations = [row for row in records if "relation" in row]
    require(0 < len(relations) <= 1000 and len(records) <= 2001, "bounded-nonempty-database-required")
    require(len({row["relation"] for row in relations}) == len(relations), "duplicate-relation-observation")
    require(len([r for r in records if set(r) == {"schema_sha256"}]) == 1, "schema-observation-required")
    for row in records:
        require(set(row) in ({"relation", "rows", "sha256"}, {"sequence", "sha256"}, {"schema_sha256"}),
                "database-observation-shape-invalid")
        require(re.fullmatch(r"[0-9a-f]{64}", row.get("sha256", row.get("schema_sha256", ""))) is not None,
                "database-observation-digest-invalid")
        if "rows" in row:
            require(type(row["rows"]) is int and row["rows"] >= 0, "database-row-count-invalid")
    return {"state_sha256": hashed(records), "table_count": len(relations),
            "sequence_count": sum("sequence" in row for row in records),
            "row_count": sum(row["rows"] for row in relations)}


def source_profile(instance: dict, project: str, region: str, name: str, *, require_backups=True) -> dict:
    require(instance.get("name") == name and instance.get("project") == project
            and instance.get("region") == region and instance.get("state") == "RUNNABLE"
            and instance.get("databaseVersion") == "POSTGRES_16", "source-instance-identity-or-state-invalid")
    settings = instance.get("settings", {})
    network = settings.get("ipConfiguration", {})
    backup = settings.get("backupConfiguration", {})
    require(network.get("ipv4Enabled") is False and bool(network.get("privateNetwork"))
            and not network.get("authorizedNetworks"), "private-only-cloud-sql-required")
    if require_backups:
        require(backup.get("enabled") is True and backup.get("pointInTimeRecoveryEnabled") is True,
                "standard-backups-and-pitr-required")
    ips = [row["ipAddress"] for row in instance.get("ipAddresses", []) if row.get("type") == "PRIVATE"]
    require(len(ips) == 1 and ipaddress.ip_address(ips[0]).is_private, "private-sql-address-required")
    require(bool(instance.get("createTime")), "sql-creation-identity-required")
    return {"name": name, "project": project, "region": region, "create_time": instance["createTime"],
            "private_network": network["privateNetwork"], "private_ip": ips[0]}


class SqlRecovery:
    def __init__(self, runtime: GkeRuntime, source: str, key: str, signer: str, *, state=None):
        require(NAME.fullmatch(source) is not None, "source-instance-name-invalid")
        self.runtime, self.key, self.signer = runtime, key, signer
        self.state = state or {"state_type": STATE_TYPE, "run_id": runtime.run_id,
            "source": source, "target": "ly-sql-restore-" + hashed(runtime.run_id)[:20],
            "project": runtime.project, "region": runtime.region, "context": runtime.context,
            "namespace": runtime.namespace, "images": runtime.images, "probe_image": runtime.probe_image,
            "resources": [], "operations": {}, "target_create_time": None, "target_absent_before": False}
        require(self.state["source"] == source and self.state["target"] == "ly-sql-restore-" + hashed(runtime.run_id)[:20]
                and self.state["target"] != source, "isolated-target-identity-required")
        self.databases: dict[str, str] = {}
        self.probes: dict[str, dict] = {}
        self.probe_policy: dict | None = None
        self.probe_host: str | None = None
        self.observation: dict | None = None

    @contextmanager
    def phase(self, name):
        """Persist bounded phase timings, including the phase of a failed command."""
        began = time.monotonic()
        row = {"phase": name, "status": "running", "started_at": utc()}
        def record():
            if self.observation is not None:
                write_signed(self.runtime.output / "database-recovery.json", self.observation, self.key, self.signer)
        if self.observation is not None:
            rows = self.observation.setdefault("phases", [])
            rows.append(row)
            del rows[:-100]
        record()
        try:
            yield
            row["status"] = "completed"
        except (Exception, KeyboardInterrupt) as exc:
            row.update(status="failed", reason=str(exc) if isinstance(exc, JourneyFailure) else
                       "operator-interrupted" if isinstance(exc, KeyboardInterrupt) else "input-or-runtime-error")
            if self.observation is not None:
                self.observation.setdefault("failure_stage", name)
            raise
        finally:
            row.update(finished_at=utc(), elapsed_seconds=round(time.monotonic() - began, 6))
            record()

    def save(self):
        write_signed(self.runtime.output / "sql-recovery-state.json", self.state, self.key, self.signer)

    def cloud(self, *args, timeout=90):
        raw = invoke(["gcloud", "sql", *args, "--project", self.runtime.project,
                      "--format=json", "--quiet"], timeout=timeout)
        return json.loads(raw) if raw.strip() else None

    def instance(self, name):
        return self.cloud("instances", "describe", name)

    def target_guard(self):
        require(self.state["target"] != self.state["source"] and self.state.get("target_create_time"),
                "owned-restore-target-required")
        current = self.instance(self.state["target"])
        require(current.get("createTime") == self.state["target_create_time"]
                and current.get("project") == self.runtime.project, "restore-target-identity-drift")
        return current

    def claim_target(self):
        clone = self.state["operations"]["pitr"]
        operation = self.wait_operation(clone["name"], self.state["target"])
        target = self.instance(self.state["target"])
        require(operation.get("operationType") == "CLONE" and operation.get("endTime")
                and epoch(clone["requested_at"]) <= epoch(target["createTime"]) <= epoch(operation["endTime"]),
                "clone-creation-ownership-not-proven")
        self.state["target_create_time"] = target["createTime"]
        self.save()
        return target

    def source_guard(self):
        profile = self.state["source_profile"]
        require(source_profile(self.instance(self.state["source"]), self.runtime.project,
            self.runtime.region, self.state["source"]) == profile, "source-instance-identity-drift")

    def wait_operation(self, name, target, timeout=1800):
        deadline = time.monotonic() + timeout
        while True:
            operation = self.cloud("operations", "describe", name)
            require(operation.get("targetId") == target and operation.get("targetProject") == self.runtime.project,
                    "cloud-sql-operation-target-mismatch")
            for intent in self.state["operations"].values():
                if intent.get("name") == name:
                    intent["observation"] = {k: operation[k] for k in
                        ("status", "operationType", "insertTime", "startTime", "endTime") if k in operation}
                    intent["observation"]["has_error"] = bool(operation.get("error"))
                    self.save()
                    break
            if operation.get("status") == "DONE":
                require(not operation.get("error"), "cloud-sql-operation-failed-inspect-saved-operation")
                return operation
            require(time.monotonic() < deadline, "cloud-sql-operation-timeout-inspect-saved-operation")
            time.sleep(10)

    def operation(self, phase: str, target: str, *args):
        require(phase not in self.state["operations"], "operation-intent-already-exists-use-recover")
        self.state["operations"][phase] = {"target": target, "requested_at": utc(), "name": None}
        self.save()
        result = self.cloud(*args, "--async")
        require(isinstance(result, dict) and bool(result.get("name")), "cloud-sql-operation-id-missing")
        self.state["operations"][phase]["name"] = result["name"]
        self.save()
        return result["name"]

    def discover(self):
        profile = source_profile(self.instance(self.state["source"]), self.runtime.project,
                                 self.runtime.region, self.state["source"])
        self.state["source_profile"] = profile
        existing = self.cloud("instances", "list")
        require(not any(row.get("name") == self.state["target"] for row in existing), "restore-target-already-exists")
        self.state["target_absent_before"] = True
        self.save()
        # Read only the JDBC URL in memory. Credentials are supplied to the pod
        # by Kubernetes secretKeyRef; they never enter command arguments/files.
        services_with_database = []
        for service in SERVICES:
            secret_name = "cloudbank-" + service + "-external"
            secret = self.runtime.get("secret", secret_name)
            encoded = secret.get("data", {}).get("SPRING_DATASOURCE_URL")
            if not encoded:
                continue
            jdbc = base64.b64decode(encoded, validate=True).decode()
            require(jdbc.startswith("jdbc:postgresql://"), "postgresql-datasource-required-" + service)
            parsed = urlsplit(jdbc.removeprefix("jdbc:"))
            require(parsed.hostname == profile["private_ip"] and (parsed.port or 5432) == 5432
                    and parsed.username is None and parsed.password is None and not parsed.query and not parsed.fragment
                    and re.fullmatch(r"/[A-Za-z0-9_-]+", parsed.path), "datasource-source-binding-invalid-" + service)
            require(all(k in secret["data"] for k in ("SPRING_DATASOURCE_USERNAME", "SPRING_DATASOURCE_PASSWORD")),
                    "database-credentials-missing-" + service)
            self.databases.setdefault(parsed.path[1:], secret_name)
            services_with_database.append(service)
        require(bool(self.databases), "application-databases-required")
        self.state["coverage"] = {"services_with_datasource": services_with_database,
            "database_count": len(self.databases), "database_names_sha256": hashed(sorted(self.databases)),
            "scope": "all persistent tables and sequences in configured application databases; no roles, grants, large objects or application failover"}
        self.save()
        return profile

    def create_resource(self, manifest):
        kind, name = manifest["kind"].lower(), manifest["metadata"]["name"]
        record = {"kind": kind, "name": name, "uid": None}
        self.state["resources"].append(record)
        self.save()
        created = json.loads(self.runtime.kubectl("create", "-f", "-", "-o", "json", data=json.dumps(manifest)))
        record["uid"] = created["metadata"]["uid"]
        self.save()
        return record

    def remove_resources(self):
        for record in list(reversed(self.state["resources"])):
            raw = self.runtime.kubectl("get", record["kind"], record["name"], "--ignore-not-found", "-o", "json")
            if raw.strip():
                current = json.loads(raw)
                require(current["metadata"].get("labels", {}).get("lightyear.run") == self.runtime.run_id
                        and (record["uid"] is None or record["uid"] == current["metadata"]["uid"]), "probe-resource-identity-drift")
                self.runtime.kubectl("delete", record["kind"], record["name"], "--wait=true", "--timeout=60s", timeout=75)
            self.state["resources"].remove(record)
            self.save()

    def probe_labels(self):
        return {"lightyear.run": self.runtime.run_id, "app.kubernetes.io/name": "sql-recovery-probe"}

    def probe_policy_spec(self, host):
        return {"podSelector": {"matchLabels": self.probe_labels()},
                "policyTypes": ["Ingress", "Egress"], "ingress": [],
                "egress": [] if host is None else [{"to": [{"ipBlock": {"cidr": host + "/32"}}],
                    "ports": [{"protocol": "TCP", "port": 5432}]}]}

    def owned_resource(self, record):
        current = self.runtime.get(record["kind"], record["name"])
        require(record.get("uid") and current["metadata"]["uid"] == record["uid"]
                and all(current["metadata"].get("labels", {}).get(k) == v for k, v in self.probe_labels().items()),
                "probe-resource-identity-drift")
        return current

    def prepare_probes(self):
        """Prepare the read-only client pool during source preflight, before RTO starts."""
        if self.probe_policy is not None:
            require(set(self.probes) == set(self.databases), "incomplete-probe-pool-use-recover")
            return
        require(bool(self.databases), "application-databases-required")
        prefix = "ly-sql-probe-" + hashed(self.runtime.run_id)[:12]
        labels = self.probe_labels()
        with self.phase("probe-pool-preparation"):
            self.probe_policy = self.create_resource({"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy",
                "metadata": {"name": prefix, "labels": labels}, "spec": self.probe_policy_spec(None)})
            for index, (database, secret) in enumerate(sorted(self.databases.items())):
                name = prefix + "-" + str(index)
                env = [{"name": "PGDATABASE", "value": database},
                       {"name": "PGPORT", "value": "5432"}, {"name": "PGCONNECT_TIMEOUT", "value": "10"},
                       {"name": "PGSSLMODE", "value": "require"},
                       {"name": "PGOPTIONS", "value": "-c default_transaction_read_only=on -c statement_timeout=60000"}]
                for field, key in (("PGUSER", "SPRING_DATASOURCE_USERNAME"), ("PGPASSWORD", "SPRING_DATASOURCE_PASSWORD")):
                    env.append({"name": field, "valueFrom": {"secretKeyRef": {"name": secret, "key": key}}})
                created = self.create_resource({"apiVersion": "v1", "kind": "Pod", "metadata": {"name": name, "labels": labels},
                    "spec": {"serviceAccountName": "testrunner", "automountServiceAccountToken": False,
                        "restartPolicy": "Never", "activeDeadlineSeconds": 7200, "terminationGracePeriodSeconds": 1,
                        "securityContext": {"runAsNonRoot": True, "runAsUser": 70, "runAsGroup": 70,
                            "seccompProfile": {"type": "RuntimeDefault"}}, "containers": [{"name": "probe",
                            "image": self.runtime.probe_image, "command": ["sleep", "7200"], "env": env,
                            "securityContext": {"allowPrivilegeEscalation": False, "readOnlyRootFilesystem": True,
                                "capabilities": {"drop": ["ALL"]}},
                            "resources": {"requests": {"cpu": "50m", "memory": "32Mi"},
                                "limits": {"cpu": "250m", "memory": "128Mi"}}}]}})
                self.probes[database] = {**created, "env": env}
            for record in self.probes.values():
                self.runtime.kubectl("wait", "--for=condition=Ready", "pod/" + record["name"], "--timeout=180s", timeout=200)
                self.owned_resource(record)

    def connect_probes(self, host):
        policy = self.owned_resource(self.probe_policy)
        expected, actual = self.probe_policy_spec(self.probe_host), policy.get("spec", {})
        require(actual.get("podSelector") == expected["podSelector"]
                and set(actual.get("policyTypes", [])) == {"Ingress", "Egress"}
                and not actual.get("ingress") and actual.get("egress", []) == expected["egress"],
                "probe-network-policy-drift")
        if host == self.probe_host:
            return
        metadata = policy["metadata"]
        require(bool(metadata.get("resourceVersion")), "probe-policy-resource-version-required")
        replacement = {"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy",
            "metadata": {k: metadata[k] for k in ("name", "uid", "resourceVersion", "labels")},
            "spec": self.probe_policy_spec(host)}
        updated = json.loads(self.runtime.kubectl("replace", "-f", "-", "-o", "json", data=json.dumps(replacement)))
        require(updated["metadata"]["uid"] == self.probe_policy["uid"], "probe-resource-identity-drift")
        self.probe_host = host

    def snapshot(self, host: str):
        require(ipaddress.ip_address(host).is_private, "private-probe-host-required")
        self.prepare_probes()
        observations = {}
        with self.phase("snapshot-network-binding"):
            self.connect_probes(host)
        with self.phase("snapshot-data-validation"):
            for database, record in sorted(self.probes.items()):
                pod = self.owned_resource(record)
                containers = pod.get("spec", {}).get("containers", [])
                require(len(containers) == 1 and containers[0].get("name") == "probe"
                        and containers[0].get("image") == self.runtime.probe_image
                        and containers[0].get("env") == record["env"]
                        and pod.get("status", {}).get("phase") == "Running"
                        and any(c.get("type") == "Ready" and c.get("status") == "True"
                                for c in pod.get("status", {}).get("conditions", [])), "probe-not-ready-or-configuration-drift")
                # Policy changes can take time to reach the node. Only retry this
                # read-only transaction; cloud mutations are never resubmitted.
                for attempt in range(3):
                    try:
                        raw = invoke(["kubectl", "--context", self.runtime.context, "-n", self.runtime.namespace,
                            "exec", "-i", record["name"], "--", "env", "PGHOST=" + host,
                            "psql", "-X", "-qAt", "--no-password", "--set=ON_ERROR_STOP=1"],
                            data=SNAPSHOT_SQL, timeout=180, sensitive=True)
                        break
                    except JourneyFailure as exc:
                        if attempt == 2 or str(exc) != "operator-command-failed-database-or-secret-access":
                            raise
                        time.sleep(attempt + 1)
                observations[hashed(database)] = normalize_snapshot(raw)
        return {"state_sha256": hashed(observations), "databases": observations}

    def quiesce(self):
        for service in reversed(SERVICES):
            self.runtime.stop(service)
        # The journey adapter deliberately leaves Checks terminating for its
        # crash test. This drill waits for all Checks writers to exit cleanly.
        deadline = time.monotonic() + 180
        while any(self.runtime.pods(service) for service in SERVICES):
            require(time.monotonic() < deadline, "application-quiescence-timeout")
            time.sleep(2)

    def restore_apps(self):
        recovery = self.runtime.close()
        if self.observation is not None:
            checks = self.observation.setdefault("application_restoration_checks", [])
            checks.append(recovery)
            del checks[:-3]
        require(recovery["status"] == "restored", "application-restoration-failed-use-recover")
        self.runtime.ready()

    def cleanup(self):
        self.remove_resources()
        clone = self.state["operations"].get("pitr")
        if clone and not self.state.get("target_deleted"):
            require(clone.get("name"), "clone-submission-uncertain-manual-operation-inspection-required")
            self.wait_operation(clone["name"], self.state["target"])
            if not self.state.get("target_create_time"):
                self.claim_target()
            if "delete" in self.state["operations"]:
                deletion = self.state["operations"]["delete"]
                require(deletion.get("name"), "delete-submission-uncertain-inspect-operation")
                self.wait_operation(deletion["name"], self.state["target"])
            else:
                # Never delete while a submitted restore is still running.
                restore = self.state["operations"].get("backup-restore")
                if restore:
                    require(restore.get("name"), "restore-submission-uncertain-inspect-operation")
                    self.wait_operation(restore["name"], self.state["target"])
                current = self.target_guard()
                require(not current.get("settings", {}).get("deletionProtectionEnabled"),
                        "restore-target-protected-retained-for-operator-cleanup")
                operation = self.operation("delete", self.state["target"], "instances", "delete", self.state["target"])
                self.wait_operation(operation, self.state["target"])
            self.state["target_deleted"] = True
            self.save()

    def execute(self):
        progress = self.runtime.progress
        result = {"observation_type": OBSERVATION_TYPE, "run_id": self.runtime.run_id, "status": "failed",
                  "bindings": {"environment": self.state.get("environment"),
                      "journeys_content_sha256": self.state.get("journeys_content_sha256"),
                      "images_sha256": hashed(self.runtime.images)},
                  "ms65_complete": False, "ms66_complete": False, "ms67_complete": False,
                  "credentials_persisted": False, "raw_database_rows_persisted": False,
                  "timing_scope": "database provisioning through read-only state validation; application failover not exercised",
                  "workload_scope": "quiesced synthetic checkpoint; continuous-write RPO not demonstrated"}
        self.observation = result
        try:
            progress("Validating Cloud SQL identity and application database coverage")
            with self.phase("source-preflight"):
                profile = self.discover()
                self.runtime.ready()
                # Prepare clients and validate coverage before taking services down.
                self.snapshot(profile["private_ip"])
            progress("Quiescing eight applications and hashing the stable database checkpoint")
            with self.phase("source-checkpoint"):
                self.quiesce()
                before = self.snapshot(profile["private_ip"])
            stable_after = utc()
            result.update(source=self.state["source"], target=self.state["target"], coverage=self.state["coverage"],
                          checkpoint=before, checkpoint_captured_at=stable_after)
            progress("Creating an on-demand backup of the source")
            with self.phase("backup-submit"):
                self.source_guard()
                backup_op = self.operation("backup", self.state["source"], "backups", "create",
                    "--instance", self.state["source"], "--description", self.runtime.run_id)
            with self.phase("backup-completion"):
                self.wait_operation(backup_op, self.state["source"])
                backups = self.cloud("backups", "list", "--instance", self.state["source"])
            matching = [b for b in backups if b.get("description") == self.runtime.run_id and b.get("status") == "SUCCESSFUL"]
            require(len(matching) == 1, "unique-successful-backup-required")
            backup = matching[0]
            backup_record = {k: backup[k] for k in ("id", "instance", "startTime", "endTime", "status", "type")}
            require(backup_record["instance"] == self.state["source"] and backup_record["type"] == "ON_DEMAND"
                    and epoch(backup_record["startTime"]) >= epoch(stable_after), "backup-checkpoint-binding-invalid")
            result["backup"] = {**backup_record, "metadata_sha256": hashed(backup_record),
                                "managed_backup_bytes_sha256": None, "retained": True}
            progress("Rechecking stable source state before selecting the recovery timestamp")
            with self.phase("source-stability-recheck"):
                require(self.snapshot(profile["private_ip"]) == before, "source-changed-during-checkpoint-window")
            progress("Waiting for a recent recoverable timestamp after the checkpoint")

            def record_point(observation):
                preflight = result.setdefault("pitr_preflight", {"recent_observations": []})
                preflight.update(attempt_count=observation["attempt"], status=observation["status"])
                preflight["recent_observations"] = (preflight["recent_observations"] + [observation])[-5:]
                write_signed(self.runtime.output / "database-recovery.json", result, self.key, self.signer)

            with self.phase("recovery-point-selection"):
                latest, incident, rpo, started = select_recovery_point(stable_after,
                    lambda: self.cloud("instances", "get-latest-recovery-time", self.state["source"])["latestRecoveryTime"],
                    record_point)
            progress("PITR cloning to the isolated validation instance")
            # Revalidate source identity immediately before mutation. Its latency
            # is part of RTO, which starts at the accepted point's observation.
            with self.phase("pitr-submit"):
                self.source_guard()
                self.operation("pitr", self.state["target"], "instances", "clone", self.state["source"],
                               self.state["target"], "--point-in-time", latest)
            with self.phase("application-restoration-after-clone-submit"):
                self.restore_apps()
            with self.phase("pitr-clone-completion"):
                target = self.claim_target()
            with self.phase("pitr-validation"):
                target_profile = source_profile(target, self.runtime.project, self.runtime.region, self.state["target"], require_backups=False)
                require(target_profile["private_network"] == profile["private_network"]
                        and target_profile["private_ip"] != profile["private_ip"], "isolated-network-identity-invalid")
                recovered = self.snapshot(target_profile["private_ip"])
            pitr_rto = math.ceil(time.monotonic() - started)
            result["pitr"] = {"incident_declared_at": incident, "point_in_time": latest, "recovery_point_age_seconds": rpo,
                "database_rto_seconds": pitr_rto, "restored_state": recovered,
                "state_matches": recovered == before, "rpo_within_limit": 0 <= rpo <= 60,
                "rto_within_limit": pitr_rto <= 600}
            write_signed(self.runtime.output / "database-recovery.json", result, self.key, self.signer)
            progress("Restoring the explicit backup into the same isolated instance")
            with self.phase("backup-restore-target-check"):
                self.target_guard()
            started = time.monotonic()
            with self.phase("backup-restore-submit"):
                restore_op = self.operation("backup-restore", self.state["target"], "backups", "restore", str(backup["id"]),
                    "--backup-instance", self.state["source"], "--restore-instance", self.state["target"])
            with self.phase("backup-restore-completion"):
                self.wait_operation(restore_op, self.state["target"])
            with self.phase("backup-restore-validation"):
                target_profile = source_profile(self.target_guard(), self.runtime.project, self.runtime.region,
                                                self.state["target"], require_backups=False)
                require(target_profile["private_network"] == profile["private_network"]
                        and target_profile["private_ip"] != profile["private_ip"], "restored-network-identity-invalid")
                recovered = self.snapshot(target_profile["private_ip"])
            backup_rto = math.ceil(time.monotonic() - started)
            result["backup_restore"] = {"restored_state": recovered, "state_matches": recovered == before,
                "database_rto_seconds": backup_rto, "rto_within_limit": backup_rto <= 600,
                "timing_scope": "restore into an existing isolated instance through database state validation"}
            passed = (result["pitr"]["state_matches"] and result["pitr"]["rto_within_limit"]
                      and result["backup_restore"]["state_matches"] and result["backup_restore"]["rto_within_limit"])
            result["status"] = "passed-isolated-database-recovery" if passed else "failed"
        except (Exception, KeyboardInterrupt) as exc:
            result.update(status="failed", reason=str(exc) if isinstance(exc, JourneyFailure) else
                          "operator-interrupted" if isinstance(exc, KeyboardInterrupt) else "recovery-input-or-runtime-error")
        finally:
            errors = []
            for label, action in (("application-restoration", self.restore_apps), ("isolated-resource-cleanup", self.cleanup)):
                try:
                    progress(label)
                    with self.phase("cleanup-" + label):
                        action()
                except (Exception, KeyboardInterrupt) as exc:
                    errors.append({"stage": label, "reason": str(exc) if isinstance(exc, JourneyFailure)
                                   else "cleanup-interrupted-or-runtime-error"})
            result["recovery"] = {"status": "failed" if errors else "restored", "errors": errors,
                "remaining_stopped_services": sorted(self.runtime.stopped),
                "validation_instance_deleted": self.state.get("target_deleted", False),
                "validation_instance_state": "deleted" if self.state.get("target_deleted") else
                    "not-requested" if "pitr" not in self.state["operations"] else
                    "submission-uncertain" if not self.state["operations"]["pitr"].get("name") else
                    "created" if self.state.get("target_create_time") else "creation-requested"}
            if errors:
                result["status"] = "failed"
            result["finished_at"] = utc()
            write_signed(self.runtime.output / "database-recovery.json", result, self.key, self.signer)
        return result
