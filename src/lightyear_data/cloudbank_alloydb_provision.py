"""Create the bounded MS71 private AlloyDB target with credentials kept in Secret Manager."""
from __future__ import annotations

import json
from pathlib import Path
import secrets
import tempfile

from .cloudbank_journeys import require
from .cloudbank_managed_target import PROVIDERS, LABEL, validate_profile


def provision(profile, *, network, admin_secret, cpu_count, command):
    validate_profile(profile)
    require(profile["provider"] == PROVIDERS[1], "ms71-alloydb-profile-required")
    require(LABEL.fullmatch(network) and LABEL.fullmatch(admin_secret) and cpu_count in (2, 4),
            "ms71-provision-input-invalid")
    project, region = profile["project"], profile["region"]
    base = ["gcloud", "--quiet", "--project=" + project]
    label = command(base + ["projects", "describe", project, "--format=value(labels.environment)"]).strip()
    require(label in {"non-production", "nonprod", "test", "sandbox"}, "ms71-nonproduction-project-required")
    cluster_resource = profile["resource"].split("/instances/")[0]
    cluster_name = cluster_resource.split("/")[-1]
    clusters = json.loads(command(base + ["alloydb", "clusters", "list", "--region=" + region,
        "--format=json(name,state,databaseVersion,networkConfig)"]))
    existing = [c for c in clusters if c["name"] == cluster_resource]
    require(len(existing) <= 1, "ms71-ambiguous-cluster")
    if not existing:
        secret_names = command(base + ["secrets", "list", "--filter=name:" + admin_secret,
            "--format=value(name)"]).splitlines()
        if not any(n.split("/")[-1] == admin_secret for n in secret_names):
            command(base + ["secrets", "create", admin_secret, "--replication-policy=automatic",
                           "--labels=environment=non-production,milestone=ms71"])
            command(base + ["secrets", "versions", "add", admin_secret, "--data-file=-"], data=json.dumps({
                "username": "postgres", "password": secrets.token_urlsafe(36), "resource": cluster_resource}))
        credentials = json.loads(command(base + ["secrets", "versions", "access", "latest", "--secret=" + admin_secret]))
        require(credentials.get("resource") == cluster_resource and credentials.get("username") == "postgres"
                and isinstance(credentials.get("password"), str) and len(credentials["password"]) >= 32,
                "ms71-admin-secret-binding-invalid")
        # Password never enters the process argument list or an output artifact.
        with tempfile.TemporaryDirectory(prefix="ms71-private-flags-") as directory:
            flags = Path(directory) / "flags.json"
            flags.write_text(json.dumps({"--password": credentials["password"]}), encoding="utf-8")
            flags.chmod(0o600)
            command(base + ["alloydb", "clusters", "create", cluster_name, "--region=" + region,
                "--network=projects/" + project + "/global/networks/" + network,
                "--database-version=" + profile["database_version"], "--flags-file=" + str(flags), "--async"])
        return {"status": "cluster-provisioning", "resource": cluster_resource, "MS71_COMPLETE": False}
    cluster = existing[0]
    project_number = command(base + ["projects", "describe", project, "--format=value(projectNumber)"]).strip()
    observed_network = cluster.get("networkConfig", {}).get("network", "").removeprefix(
        "https://www.googleapis.com/compute/v1/")
    require(cluster.get("databaseVersion") == profile["database_version"] and observed_network in {
        f"projects/{identity}/global/networks/{network}" for identity in (project, project_number)},
            "ms71-existing-cluster-configuration-drift")
    if cluster.get("state") != "READY":
        require(cluster.get("state") == "CREATING", "ms71-cluster-not-ready")
        return {"status": "cluster-provisioning", "resource": cluster_resource, "MS71_COMPLETE": False}
    instances = json.loads(command(base + ["alloydb", "instances", "list", "--cluster=" + cluster_name,
        "--region=" + region, "--format=json(name,state,instanceType,machineConfig,networkConfig)"]))
    current = [i for i in instances if i["name"] == profile["resource"]]
    if not current:
        require(not instances, "ms71-existing-instance-review-required")
        command(base + ["alloydb", "instances", "create", profile["resource"].split("/")[-1],
            "--cluster=" + cluster_name, "--region=" + region, "--instance-type=PRIMARY",
            "--cpu-count=" + str(cpu_count), "--availability-type=REGIONAL", "--ssl-mode=ENCRYPTED_ONLY",
            "--async"])
        return {"status": "primary-provisioning", "resource": profile["resource"], "MS71_COMPLETE": False}
    require(len(current) == 1 and current[0].get("instanceType") == "PRIMARY"
            and current[0].get("machineConfig", {}).get("cpuCount") == cpu_count,
            "ms71-existing-primary-configuration-drift")
    state = current[0].get("state")
    require(state in {"READY", "CREATING"}, "ms71-primary-not-ready")
    return {"status": "primary-ready" if state == "READY" else "primary-provisioning",
            "resource": profile["resource"], "MS71_COMPLETE": False}
