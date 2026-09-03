#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

ms67_require_tools gcloud
ms67_require_environment
ms67_require_non_production_project
[[ "${LIGHTYEAR_MS67_DESTROY_ACK:-}" == "DESTROY-CLOUDBANK-MS67-NON-PRODUCTION" ]] || {
  echo "Set LIGHTYEAR_MS67_DESTROY_ACK=DESTROY-CLOUDBANK-MS67-NON-PRODUCTION" >&2
  exit 2
}
gcloud config set project "$GCP_PROJECT_ID" >/dev/null
echo "Destroying only named MS67 resources in project $GCP_PROJECT_ID"

gcloud container clusters describe "$GKE_CLUSTER_NAME" --region "$GCP_REGION" >/dev/null 2>&1 && \
  gcloud container clusters delete "$GKE_CLUSTER_NAME" --region "$GCP_REGION" --quiet || true
gcloud sql instances describe "$CLOUD_SQL_INSTANCE" >/dev/null 2>&1 && {
  gcloud sql instances patch "$CLOUD_SQL_INSTANCE" --no-deletion-protection --quiet
  gcloud sql instances delete "$CLOUD_SQL_INSTANCE" --quiet
} || true
gcloud artifacts repositories describe "$ARTIFACT_REPOSITORY" --location "$GCP_REGION" >/dev/null 2>&1 && \
  gcloud artifacts repositories delete "$ARTIFACT_REPOSITORY" --location "$GCP_REGION" --quiet || true
for service in "${ms67_services[@]}"; do
  gcloud secrets describe "cloudbank-${service}-external" >/dev/null 2>&1 && \
    gcloud secrets delete "cloudbank-${service}-external" --quiet || true
done
gcloud dns managed-zones describe "$DNS_ZONE_NAME" >/dev/null 2>&1 && {
  gcloud dns record-sets transaction start --zone "$DNS_ZONE_NAME"
  while read -r name type ttl data; do
    [[ "$type" =~ ^(NS|SOA)$ ]] && continue
    gcloud dns record-sets transaction remove --zone "$DNS_ZONE_NAME" \
      --name "$name" --type "$type" --ttl "$ttl" "$data"
  done < <(gcloud dns record-sets list --zone "$DNS_ZONE_NAME" --format='value(name,type,ttl,rrdatas)')
  gcloud dns record-sets transaction execute --zone "$DNS_ZONE_NAME"
  gcloud dns managed-zones delete "$DNS_ZONE_NAME" --quiet
} || true
gcloud compute addresses describe cloudbank-ms67-ingress --region "$GCP_REGION" >/dev/null 2>&1 && \
  gcloud compute addresses delete cloudbank-ms67-ingress --region "$GCP_REGION" --quiet || true
gcloud compute routers nats describe cloudbank-ms67 --router cloudbank-ms67 --region "$GCP_REGION" >/dev/null 2>&1 && \
  gcloud compute routers nats delete cloudbank-ms67 --router cloudbank-ms67 --region "$GCP_REGION" --quiet || true
gcloud compute routers describe cloudbank-ms67 --region "$GCP_REGION" >/dev/null 2>&1 && \
  gcloud compute routers delete cloudbank-ms67 --region "$GCP_REGION" --quiet || true

echo "Chargeable GKE, Cloud SQL, image, secret, DNS, address, and NAT resources were removed."
echo "The VPC peering, subnet, network, reserved service range, and disabled KMS key are retained"
echo "because Google Cloud may reject immediate deletion while service networking finishes cleanup."
