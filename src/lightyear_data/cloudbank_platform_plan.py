"""Public, offline plan-derived expectations. No cloud, credentials or execution."""
from __future__ import annotations

import hashlib
import json
import re

DRILLS = ("NETWORK-ENFORCEMENT", "RUNTIME-IDENTITY", "SECRET-ROTATION", "SQL-HA",
          "SQL-RECOVERY", "ALERT-DRILL", "SUSTAINED-LOAD")
HEX = r"[0-9a-f]{64}"


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def hashed(value):
    return digest(canonical(value))


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate-json-key")
        result[key] = value
    return result


def decode(raw):
    require(len(raw) <= 16 * 1024 * 1024, "public-input-too-large")
    return json.loads(raw, object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("non-finite-json")))


def at(value, path):
    for part in path.split("/"):
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def one(resources, address):
    require(address in resources, "missing-plan-resource:" + address)
    return resources[address]


def resources(module):
    result = {}
    for row in module.get("resources", []):
        require(row["address"] not in result and row["mode"] == "managed", "duplicate-or-data-resource")
        result[row["address"]] = row["values"]
    for child in module.get("child_modules", []):
        other = resources(child)
        require(not set(result) & set(other), "duplicate-module-resource")
        result.update(other)
    return result


def manifest_index(bundle):
    require(bundle.get("kind") == "List" and isinstance(bundle.get("items"), list), "rendered-list-required")
    result = {}
    for row in bundle["items"]:
        require(row.get("kind") != "Secret", "secret-values-forbidden")
        meta = row["metadata"]
        key = (row["kind"], meta.get("namespace", ""), meta["name"])
        require(key not in result, "duplicate-rendered-object")
        result[key] = row
    return result


def compile_plan(plan_bytes, rollout_bytes, *, commit, plan_sha256, rollout_sha256, policy_sha256):
    """Expected digests/commit come from the caller's separately approved packet.

    A Terraform plan is not provenance by itself. The caller must authenticate the
    packet; this function enforces its bindings and recomputes declarations.
    """
    require(re.fullmatch(r"[0-9a-f]{40}", commit or ""), "exact-iac-commit-required")
    require(all(re.fullmatch(HEX, x or "") for x in (plan_sha256, rollout_sha256, policy_sha256)),
            "exact-approved-digests-required")
    require(digest(plan_bytes) == plan_sha256 and digest(rollout_bytes) == rollout_sha256, "input-digest-mismatch")
    plan, bundle = decode(plan_bytes), decode(rollout_bytes)
    require(plan.get("format_version") in {"1.2"} and plan.get("terraform_version") == "1.13.3",
            "unsupported-plan-version")
    require(plan.get("errored") is False and plan.get("complete") is True, "incomplete-or-errored-plan")
    require(not plan.get("deferred_changes"), "deferred-plan-refused")
    for change in plan.get("resource_changes", []):
        actions = change["change"]["actions"]
        require(actions in (["create"], ["update"], ["no-op"]), "destructive-or-unknown-plan-action")
    values = plan["planned_values"]
    output = values["outputs"]["platform_infrastructure"]
    require(output.get("sensitive") is False, "sensitive-platform-output")
    declared = output["value"]
    require(declared["schema"] == "cloudbank-iac-infrastructure/1", "unsupported-infrastructure-output")
    require(declared["rollout"]["rendered_sha256"] == rollout_sha256, "rollout-not-bound-in-plan")
    require(declared["qualification_contract_sha256"] == policy_sha256, "qualification-policy-drift")
    policy = declared["qualification_contract"]
    # The source file's raw digest is packet-bound; its semantic seal also binds
    # the actual policy object carried through Terraform's output encoding.
    require(policy.get("content_sha256") == hashed({k:v for k,v in policy.items() if k != "content_sha256"}),
            "qualification-policy-content-mismatch")
    r = resources(values["root_module"])
    cluster = one(r, "google_container_cluster.estate")
    sql = one(r, "google_sql_database_instance.postgres")
    context = {"project": declared["project"], "region": cluster["location"],
               "cluster": cluster["name"], "namespace": declared["namespace"]}
    require(all(isinstance(v, str) and re.fullmatch(r"[a-zA-Z0-9_.-]+", v) for v in context.values()),
            "resolved-context-required")
    require(all(declared[k] == context[k] for k in context), "output-resource-context-mismatch")
    require(cluster["datapath_provider"] == "ADVANCED_DATAPATH"
            and at(cluster, "private_cluster_config/0/enable_private_nodes") is True
            and len(set(cluster["node_locations"])) == 3, "reference-estate-topology-required")
    controls = policy["controls"]
    services = policy["services"]
    require(isinstance(services, list) and len(services) == len(set(services)) and services, "service-set-invalid")
    secrets = {name: one(r, 'google_secret_manager_secret.service["'+name+'"]')["secret_id"] for name in services}
    require(secrets == declared["secrets"], "secret-output-resource-mismatch")
    require(sql["name"] == declared["sql"]["instance"] and sql["region"] == context["region"], "sql-output-resource-mismatch")
    settings = sql["settings"][0]
    backup = settings["backup_configuration"][0]
    require(settings["availability_type"] == "REGIONAL" and settings["ip_configuration"][0]["ipv4_enabled"] is False
            and backup["enabled"] is True and backup["point_in_time_recovery_enabled"] is True,
            "ha-private-pitr-required")
    index = manifest_index(bundle)
    ns = context["namespace"]
    identities, external = {}, {}
    for service in services:
        deployment = index[("Deployment", ns, service)]
        pod = at(deployment, "spec/template/spec")
        containers = pod["containers"]
        require(len(containers) == 1 and containers[0]["name"] == service, "single-service-container-required")
        security = {**pod.get("securityContext", {}), **containers[0].get("securityContext", {})}
        require(type(security.get("runAsUser")) is int and security["runAsUser"] > 0
                and type(security.get("runAsGroup")) is int and security["runAsGroup"] > 0
                and security.get("runAsNonRoot") is True, "explicit-nonroot-identity-required")
        require(deployment["spec"]["replicas"] == 2, "existing-two-replica-drill-contract-required")
        identities[service] = {k: security[k] for k in ("runAsUser", "runAsGroup")}
        es = index[("ExternalSecret", ns, "cloudbank-"+service)]["spec"]
        require(es["dataFrom"] == [{"extract": {"key": secrets[service]}}], "secret-provider-binding-mismatch")
        external[service] = {"secret_id": secrets[service], "refreshInterval": es["refreshInterval"],
                             "secretStoreRef": es["secretStoreRef"]}
    policies = {"/".join(key[1:]): row["spec"] for key,row in index.items() if key[0] == "NetworkPolicy"}
    require(policies and any(p.get("podSelector") == {} and p.get("ingress", []) == []
                            and p.get("egress", []) == [] and set(p.get("policyTypes", [])) == {"Ingress", "Egress"}
                            for p in policies.values()), "default-deny-baseline-required")
    require(controls["external_secrets"]["rotation_observed"] is True
            and controls["observability"]["alert_fire_and_recovery"] is True, "required-drills-missing")
    require(at(cluster, "monitoring_config/0/managed_prometheus/0/enabled") is True, "declared-monitoring-required")
    expectations = {
        "NETWORK-ENFORCEMENT": {"policies": policies, "dataplane": cluster["datapath_provider"]},
        "RUNTIME-IDENTITY": {"identities": identities, "workload_pool": at(cluster, "workload_identity_config/0/workload_pool")},
        "SECRET-ROTATION": {"external_secrets": external, "reader": declared["secret_reader"]},
        "SQL-HA": {"instance": sql["name"], "availability": settings["availability_type"], "private": True},
        "SQL-RECOVERY": {"instance": sql["name"], "backup": {k:backup[k] for k in ("enabled", "start_time", "point_in_time_recovery_enabled", "transaction_log_retention_days", "backup_retention_settings")}, "limits": controls["backup_restore"]},
        "ALERT-DRILL": {"prometheus": True, "logging": sorted(at(cluster, "logging_config/0/enable_components")),
                        "roles": sorted(declared["telemetry_roles"]), "fire_and_recovery": controls["observability"]["alert_fire_and_recovery"]},
        "SUSTAINED-LOAD": {"services": sorted(services), "limits": controls["load"]},
    }
    return {"schema": "cloudbank-platform-expectations/1", "iac_commit": commit, "plan_sha256": plan_sha256,
            "rollout_sha256": rollout_sha256, "policy_sha256": policy_sha256,
            "context": context, "expectations": expectations}
