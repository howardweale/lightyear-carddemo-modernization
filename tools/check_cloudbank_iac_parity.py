"""Static, fail-closed bootstrap/cloud-resource parity; never runs shell or Terraform."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
MODULE = "infra/cloudbank-platform/gcp"
GKE = "factory/cloudbank/platform-qualification/gke"
# Every imperative cloud mutation has a Terraform resource family. Kubernetes
# and Helm setup are intentionally retained at the documented rollout boundary.
COMMANDS = {
    "compute networks create": "google_compute_network",
    "compute networks subnets create": "google_compute_subnetwork",
    "compute routers create": "google_compute_router",
    "compute routers nats create": "google_compute_router_nat",
    "services vpc-peerings connect": "google_service_networking_connection",
    "dns managed-zones create": "google_dns_managed_zone",
    "dns record-sets create": "google_dns_record_set",
    "container clusters create": "google_container_cluster",
    "artifacts repositories create": "google_artifact_registry_repository",
    "sql instances create": "google_sql_database_instance",
    "kms keyrings create": "google_kms_key_ring",
    "kms keys create": "google_kms_crypto_key",
    "secrets create": "google_secret_manager_secret",
    "secrets add-iam-policy-binding": "google_secret_manager_secret_iam_member",
    "projects add-iam-policy-binding": "google_project_iam_member",
    "kms keys add-iam-policy-binding": "google_kms_crypto_key_iam_member",
    "services enable": "google_project_service",
}


def mutations(text):
    joined = text.replace("\\\n", " ")
    result = {}
    for command in re.findall(r"\bgcloud\s+([^\n]*?)(?=\bgcloud\s+|\n|$)", joined):
        if not re.search(r"\b(create|connect|enable|add-iam-policy-binding|delete|update)\b", command):
            continue
        if command.startswith("compute addresses create"):
            kind = "google_compute_global_address" if "--global" in command else "google_compute_address"
        else:
            matches = [value for prefix, value in COMMANDS.items() if command.startswith(prefix + " ")]
            if len(matches) != 1:
                raise ValueError("unmapped-bootstrap-mutation")
            kind = matches[0]
        result[kind] = result.get(kind, 0) + 1
    return result


def check(root=ROOT):
    bootstrap = (root / GKE / "bootstrap.sh").read_bytes()
    common = (root / GKE / "common.sh").read_bytes()
    module = json.loads((root / MODULE / "main.tf.json").read_text())
    local, resources = module["locals"], module["resource"]
    for name, raw in (("bootstrap", bootstrap), ("common", common)):
        if hashlib.sha256(raw).hexdigest() != local[name + "_sha256"]:
            raise ValueError(name + "-changed-reconcile-parity-first")
    wanted = mutations(bootstrap.decode())
    actual = {kind: len(rows) for kind, rows in resources.items() if kind != "terraform_data"}
    if wanted != actual:
        raise ValueError("bootstrap-resource-set-mismatch")
    services = re.search(rb"ms67_services=\(([^)]+)\)", common)[1].decode().split()
    if local["services"] != services:
        raise ValueError("service-instance-set-mismatch")
    api_block = bootstrap.decode().split("gcloud services enable", 1)[1].split("\n\n", 1)[0]
    if local["apis"] != re.findall(r"[a-z]+\.googleapis\.com", api_block):
        raise ValueError("api-instance-set-mismatch")
    roles = re.search(rb"for role in ([^;]+); do", bootstrap)[1].decode().split()
    if local["telemetry_roles"] != roles:
        raise ValueError("telemetry-role-instance-set-mismatch")
    for name in ("versions.tf", ".terraform.lock.hcl"):
        if (root / MODULE / name).read_bytes() != (root / "infra/cloud-runner/gcp" / name).read_bytes():
            raise ValueError("cloud-runner-pin-drift")
    if any(k in resources for k in ("google_secret_manager_secret_version", "google_service_account_key")):
        raise ValueError("secret-material-forbidden")
    return {"cloud_resource_blocks": sum(actual.values()), "services": len(services),
            "live_drills": "NOT RUN", "parity": "static-cloud-resource-set-and-source-binding"}


if __name__ == "__main__":
    print(json.dumps(check(), sort_keys=True))
