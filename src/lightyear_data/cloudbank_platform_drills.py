"""Plan-aware recipes and public projections for the seven existing controllers.

The operator executes a recipe through the existing controller and supplies its
verified observation plus fresh public API readbacks. This module never executes
cloud commands, reads evidence keys, changes retained receipts, or signs anything.
"""
from __future__ import annotations

from .cloudbank_platform_plan import DRILLS, at, hashed, manifest_index, require
from .cloudbank_platform_receipt import binding, check_measurements

CONTROLLERS = {
    "NETWORK-ENFORCEMENT": "cloudbank_network_enforcement",
    "RUNTIME-IDENTITY": "cloudbank_runtime_identity",
    "SECRET-ROTATION": "cloudbank_secret_rotation",
    "SQL-HA": "cloudbank_sql_ha", "SQL-RECOVERY": "cloudbank_sql_recovery",
    "ALERT-DRILL": "cloudbank_alert_drill", "SUSTAINED-LOAD": "cloudbank_sustained_load",
}
PASS = dict(zip(DRILLS, (
    "passed-bounded-network-enforcement", "passed-eight-runtime-identities",
    "passed-secret-rotation-and-restoration", "passed-cloud-sql-ha-failover",
    "passed-isolated-database-recovery", "passed-synthetic-alert-and-recovery",
    "passed-bounded-sustained-business-load")))


def recipes(contract):
    result = {}
    for drill, expected in contract["expectations"].items():
        args = {"--"+key: value for key,value in contract["context"].items()}
        if drill in {"SQL-HA", "SQL-RECOVERY"}:
            args["--source-instance"] = expected["instance"]
        if drill == "SECRET-ROTATION":
            require("creditscore" in expected["external_secrets"], "existing-rotation-scenario-unavailable")
            args["--provider-secret"] = expected["external_secrets"]["creditscore"]["secret_id"]
        result[drill] = {"controller": "tools/"+CONTROLLERS[drill]+".py", "action": "run",
                         "derived_arguments": args, "expectations": expected,
                         "bindings": binding(contract), "status": "NOT RUN"}
    return result


def cli_arguments(contract, drill, extra):
    """Generate controller arguments without allowing context or action overrides.

    Other existing admissions, signed input packets, private evidence location and
    recovery guards remain the controller's responsibility. No automatic retry.
    """
    recipe = recipes(contract)[drill]
    forbidden = set(recipe["derived_arguments"]) | {"run", "recover", "verify", "preflight"}
    require(isinstance(extra, list) and all(isinstance(x, str) for x in extra), "argument-list-required")
    require(not any(x.split("=", 1)[0] in forbidden for x in extra), "derived-context-override-refused")
    return [recipe["action"], *[item for pair in recipe["derived_arguments"].items() for item in pair], *extra]


def backup_projection(settings):
    row = settings["backupConfiguration"]
    return {"enabled": row["enabled"], "start_time": row["startTime"],
            "point_in_time_recovery_enabled": row["pointInTimeRecoveryEnabled"],
            "transaction_log_retention_days": row["transactionLogRetentionDays"],
            "backup_retention_settings": [{"retained_backups": row["backupRetentionSettings"]["retainedBackups"],
                                            "retention_unit": row["backupRetentionSettings"]["retentionUnit"]}]}


def configuration(drill, raw, contract):
    """Project observed API fields, never copy expected values into an observation.

    raw: public `gcloud container clusters describe`, `gcloud sql instances
    describe`, Kubernetes List and selected IAM binding readbacks. They are
    collected by the human operator, not supplied by Terraform as observations.
    """
    context, expected = contract["context"], contract["expectations"][drill]
    require(raw["context"] == context, "readback-context-mismatch")
    cluster = raw["cluster"]
    require(cluster["name"] == context["cluster"] and cluster["location"] == context["region"],
            "readback-cluster-mismatch")
    index = manifest_index(raw["kubernetes"])
    ns = context["namespace"]
    if drill == "NETWORK-ENFORCEMENT":
        policies = {"/".join(key[1:]): row["spec"] for key,row in index.items() if key[0] == "NetworkPolicy"}
        return {"policies": policies, "dataplane": cluster["networkConfig"]["datapathProvider"]}
    if drill == "RUNTIME-IDENTITY":
        identities = {}
        for key, row in index.items():
            if key[0] == "Deployment" and key[1] == ns and key[2] in expected["identities"]:
                pod = at(row, "spec/template/spec")
                containers = pod["containers"]
                require(len(containers) == 1, "readback-single-container-required")
                security = {**pod.get("securityContext", {}), **containers[0].get("securityContext", {})}
                identities[key[2]] = {k:security[k] for k in ("runAsUser", "runAsGroup")}
        return {"identities": identities, "workload_pool": cluster["workloadIdentityConfig"]["workloadPool"]}
    if drill == "SECRET-ROTATION":
        external = {}
        for service in expected["external_secrets"]:
            es = index[("ExternalSecret", ns, "cloudbank-"+service)]["spec"]
            require(len(es["dataFrom"]) == 1, "readback-secret-source-count")
            external[service] = {"secret_id": es["dataFrom"][0]["extract"]["key"],
                                 "refreshInterval": es["refreshInterval"], "secretStoreRef": es["secretStoreRef"]}
        members = raw["secret_reader_bindings"]
        require(set(members) == {v["secret_id"] for v in external.values()}
                and all(set(v) == {"role", "member"} and v["role"] == "roles/secretmanager.secretAccessor"
                        for v in members.values()), "readback-secret-iam-coverage")
        require(len({v["member"] for v in members.values()}) == 1, "readback-reader-drift")
        return {"external_secrets": external, "reader": next(iter(members.values()))["member"]}
    if drill in {"SQL-HA", "SQL-RECOVERY"}:
        sql = raw["sql"]
        require(sql["project"] == context["project"] and sql["region"] == context["region"], "readback-sql-context")
        if drill == "SQL-HA":
            return {"instance": sql["name"], "availability": sql["settings"]["availabilityType"],
                    "private": sql["settings"]["ipConfiguration"]["ipv4Enabled"] is False}
        return {"instance": sql["name"], "backup": backup_projection(sql["settings"])}
    if drill == "ALERT-DRILL":
        return {"prometheus": at(cluster, "monitoringConfig/managedPrometheusConfig/enabled"),
                "logging": sorted(cluster["loggingConfig"]["componentConfig"]["enableComponents"]),
                "roles": sorted(raw["telemetry_roles"])}
    if drill == "SUSTAINED-LOAD":
        return {"services": sorted(key[2] for key in index if key[0] == "Deployment" and key[1] == ns)}
    raise ValueError("unknown-drill")


def measurements(drill, old, expected, context):
    """A deliberately small projection; legacy verification is an additional gate."""
    require(old.get("status") == PASS[drill], "legacy-drill-not-complete")
    if drill == "NETWORK-ENFORCEMENT":
        rows = []
        for name, spec in expected["policies"].items():
            if spec.get("podSelector") != {}:
                continue
            namespace = name.split('/')[0]
            for direction in ("Ingress", "Egress"):
                if direction not in spec.get("policyTypes", []) or spec.get(direction.lower(), []):
                    continue
                # Existing reference-estate probes support the application default
                # namespace and the model egress boundary. Unknown scopes fail.
                if namespace == context["namespace"]:
                    ident = "default-"+direction.lower()+"-denied"
                else:
                    require(direction == "Egress", "unsupported-declared-denial-probe")
                    ident = "model-cross-namespace-egress-denied"
                checks = [r for r in old["checks"] if r["id"] == ident]
                require({r["phase"] for r in checks} == {"denied-first", "denied-second"}
                        and len(checks) == 2, "declared-negative-probes-missing")
                controls = [r for r in old["checks"] if r["id"] == "control-sink-route"]
                rows.append({"namespace": namespace, "direction": direction,
                             "negative_checks": [{k:r[k] for k in ("outcome", "elapsed_ms")} for r in checks],
                             "positive_before": any(r["phase"] == "positive-before" and r["outcome"] == "nonce-matched" for r in controls),
                             "positive_after": any(r["phase"] == "positive-after" and r["outcome"] == "nonce-matched" for r in controls)})
        return {"declared_denials": rows}
    if drill == "RUNTIME-IDENTITY":
        return {"services": {name: {k:row[k] for k in ("startup_uids", "startup_gids", "ready_replicas", "http_readiness")}
                             for name,row in old["services"].items()}}
    if drill == "SECRET-ROTATION":
        return {"service": old["service"],
                "recovery": {k:old["recovery"][k] for k in ("temporary_version_disabled", "original_values_restored", "preexisting_versions_unchanged")},
                "observations": {k:old["observations"][k] for k in ("baseline", "rotated", "restored")}}
    if drill == "SQL-HA":
        before, after = old["preflight"]["source_profile"], old["promoted_profile"]
        return {"before": {k:before[k] for k in ("primary_zone", "standby_zone")},
                "after": {k:after[k] for k in ("primary_zone", "standby_zone")},
                "endpoint_unchanged": all(before[k] == after[k] for k in ("name", "project", "region", "private_ip", "connection_name")),
                "same_processes": old["preflight"]["processes"] == old["after"]["processes"],
                "state_matches": old["after"]["acknowledged_state_matches"],
                "recovery_restored": old["recovery"]["status"] == "restored"}
    if drill == "SQL-RECOVERY":
        return {"source_instance": old["source"],
                "pitr": {k:old["pitr"][k] for k in ("state_matches", "database_rto_seconds", "recovery_point_age_seconds")},
                "backup_restore": {k:old["backup_restore"][k] for k in ("state_matches", "database_rto_seconds")},
                "validation_instance_deleted": old["recovery"]["validation_instance_deleted"],
                "recovery_restored": old["recovery"]["status"] == "restored"}
    if drill == "ALERT-DRILL":
        opened, closed = old["observations"]["opened"], old["observations"]["closed"]
        return {"states": [opened["state"], closed["state"]],
                "same_alert": opened["alert_identity_sha256"] == closed["alert_identity_sha256"],
                "policy_absent": old["recovery"]["policy_absent"], "metric_descriptor_absent": old["recovery"]["metric_descriptor_absent"]}
    if drill == "SUSTAINED-LOAD":
        summary = old["summary"]
        return {"requests": summary["requests"], "duration_seconds": summary["measured_duration_ms"] / 1000,
                "concurrency": summary["vus_max"], "p95_ms": summary["p95_ms"], "errors": summary["errors"],
                "services": sorted(old["live"]["after"])}
    raise ValueError("unknown-drill")


def prepare_observation(contract, drill, old, readback, validation, *, run_id, evidence_class, started_at, finished_at):
    """Prepare public bytes for HUMAN review/signing; no verified/live claim yet.

    validation is the operator's result from the unchanged legacy verifier. It is
    bound to the exact old receipt and approved verifier digest; its authenticity
    is established only when the designated observer signs this whole projection.
    """
    require(validation["receipt_sha256"] == hashed(old) and validation["verdict"] == "PASS",
            "bound-legacy-verifier-result-required")
    require(validation["recipe_sha256"] == hashed(recipes(contract)[drill])
            and validation["controller_run_id"] == old["run_id"], "legacy-recipe-or-run-binding-mismatch")
    environment = old.get("environment", old.get("bindings", {}).get("environment", {}))
    require(all(environment.get(k) == v for k,v in contract["context"].items()), "legacy-environment-mismatch")
    require(readback["started_at"] == started_at and readback["finished_at"] == finished_at,
            "readback-window-mismatch")
    expected = contract["expectations"][drill]
    result = {"schema": "cloudbank-platform-observation/1", "drill": drill, "run_id": run_id,
              "bindings": binding(contract), "context": contract["context"], "evidence_class": evidence_class,
              "started_at": started_at, "finished_at": finished_at, "legacy_verified": True,
              "legacy_receipt_sha256": hashed(old), "legacy_verifier_sha256": validation["verifier_sha256"],
              "configuration": configuration(drill, readback, contract),
              "measurements": measurements(drill, old, expected, contract["context"])}
    if drill == "SECRET-ROTATION":
        result["measurements"]["provider_secret"] = result["configuration"]["external_secrets"][old["service"]]["secret_id"]
    check_measurements(drill, expected, result)
    return result
