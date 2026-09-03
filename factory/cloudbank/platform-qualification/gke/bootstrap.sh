#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

ms67_require_tools gcloud kubectl helm jq openssl
ms67_require_environment
ms67_require_mutation_ack
gcloud auth list --filter=status:ACTIVE --format='value(account)' | grep -q . || {
  echo "No active gcloud account" >&2; exit 2;
}
ms67_require_non_production_project

gcloud config set project "$GCP_PROJECT_ID" >/dev/null
gcloud services enable \
  artifactregistry.googleapis.com cloudbuild.googleapis.com cloudkms.googleapis.com \
  compute.googleapis.com container.googleapis.com dns.googleapis.com iam.googleapis.com \
  iamcredentials.googleapis.com serviceusage.googleapis.com \
  logging.googleapis.com monitoring.googleapis.com secretmanager.googleapis.com \
  servicenetworking.googleapis.com sqladmin.googleapis.com cloudtrace.googleapis.com

gcloud compute networks describe "$GCP_NETWORK_NAME" >/dev/null 2>&1 || \
  gcloud compute networks create "$GCP_NETWORK_NAME" --subnet-mode=custom
gcloud compute networks subnets describe "$GCP_SUBNET_NAME" --region "$GCP_REGION" >/dev/null 2>&1 || \
  gcloud compute networks subnets create "$GCP_SUBNET_NAME" --region "$GCP_REGION" \
    --network "$GCP_NETWORK_NAME" --range 10.67.0.0/20 \
    --secondary-range cloudbank-pods=10.68.0.0/16,cloudbank-services=10.69.0.0/20 \
    --enable-private-ip-google-access
gcloud compute routers describe cloudbank-ms67 --region "$GCP_REGION" >/dev/null 2>&1 || \
  gcloud compute routers create cloudbank-ms67 --region "$GCP_REGION" --network "$GCP_NETWORK_NAME"
gcloud compute routers nats describe cloudbank-ms67 --router cloudbank-ms67 --region "$GCP_REGION" >/dev/null 2>&1 || \
  gcloud compute routers nats create cloudbank-ms67 --router cloudbank-ms67 --region "$GCP_REGION" \
    --auto-allocate-nat-external-ips --nat-all-subnet-ip-ranges

gcloud compute addresses describe cloudbank-ms67-sql --global >/dev/null 2>&1 || \
  gcloud compute addresses create cloudbank-ms67-sql --global --purpose VPC_PEERING \
    --prefix-length 16 --network "$GCP_NETWORK_NAME"
gcloud services vpc-peerings connect --service servicenetworking.googleapis.com \
  --ranges cloudbank-ms67-sql --network "$GCP_NETWORK_NAME" >/dev/null
gcloud dns managed-zones describe cloudbank-googleapis >/dev/null 2>&1 || \
  gcloud dns managed-zones create cloudbank-googleapis --dns-name googleapis.com. \
    --visibility private --networks "$GCP_NETWORK_NAME" \
    --description "Restricted Google APIs for MS67 telemetry"
if ! gcloud dns record-sets describe restricted.googleapis.com. --zone cloudbank-googleapis --type A >/dev/null 2>&1; then
  gcloud dns record-sets create restricted.googleapis.com. --zone cloudbank-googleapis --type A \
    --ttl 300 --rrdatas 199.36.153.8,199.36.153.9,199.36.153.10,199.36.153.11
  gcloud dns record-sets create '*.googleapis.com.' --zone cloudbank-googleapis --type CNAME \
    --ttl 300 --rrdatas restricted.googleapis.com.
fi

if ! gcloud container clusters describe "$GKE_CLUSTER_NAME" --region "$GCP_REGION" >/dev/null 2>&1; then
  gcloud container clusters create "$GKE_CLUSTER_NAME" --region "$GCP_REGION" \
    --release-channel regular --network "$GCP_NETWORK_NAME" --subnetwork "$GCP_SUBNET_NAME" \
    --cluster-secondary-range-name cloudbank-pods --services-secondary-range-name cloudbank-services \
    --enable-ip-alias --enable-private-nodes --enable-dns-access --no-enable-ip-access \
    --enable-dataplane-v2 --enable-shielded-nodes --workload-pool "$GCP_PROJECT_ID.svc.id.goog" \
    --enable-managed-prometheus --logging=SYSTEM,WORKLOAD --monitoring=SYSTEM \
    --machine-type e2-standard-4 --disk-type pd-balanced --disk-size 50 --num-nodes 1 \
    --enable-autoscaling --min-nodes 1 --max-nodes 2 --labels environment=non-production,milestone=ms67
fi
gcloud container clusters get-credentials "$GKE_CLUSTER_NAME" --region "$GCP_REGION" --dns-endpoint

gcloud artifacts repositories describe "$ARTIFACT_REPOSITORY" --location "$GCP_REGION" >/dev/null 2>&1 || \
  gcloud artifacts repositories create "$ARTIFACT_REPOSITORY" --location "$GCP_REGION" \
    --repository-format docker --description "Ephemeral CloudBank MS67 evidence images"
gcloud auth configure-docker "$GCP_REGION-docker.pkg.dev" --quiet

gcloud sql instances describe "$CLOUD_SQL_INSTANCE" >/dev/null 2>&1 || \
  gcloud sql instances create "$CLOUD_SQL_INSTANCE" --database-version POSTGRES_16 \
    --region "$GCP_REGION" --tier db-custom-2-7680 --availability-type REGIONAL \
    --network "projects/$GCP_PROJECT_ID/global/networks/$GCP_NETWORK_NAME" --no-assign-ip \
    --storage-type SSD --storage-size 20 --storage-auto-increase \
    --backup-start-time 02:00 --enable-point-in-time-recovery \
    --retained-backups-count 7 --retained-transaction-log-days 7 \
    --database-flags cloudsql.iam_authentication=on

gcloud compute addresses describe cloudbank-ms67-ingress --region "$GCP_REGION" >/dev/null 2>&1 || \
  gcloud compute addresses create cloudbank-ms67-ingress --region "$GCP_REGION"
gcloud dns managed-zones describe "$DNS_ZONE_NAME" >/dev/null 2>&1 || \
  gcloud dns managed-zones create "$DNS_ZONE_NAME" --dns-name "$DELEGATED_DNS_NAME." \
    --description "Delegated MS67 non-production qualification zone"
ingress_ip="$(gcloud compute addresses describe cloudbank-ms67-ingress --region "$GCP_REGION" --format='value(address)')"
if ! gcloud dns record-sets describe "$TLS_HOSTNAME." --zone "$DNS_ZONE_NAME" --type A >/dev/null 2>&1; then
  gcloud dns record-sets create "$TLS_HOSTNAME." --zone "$DNS_ZONE_NAME" --type A --ttl 60 --rrdatas "$ingress_ip"
fi

gcloud kms keyrings describe cloudbank-ms67 --location "$GCP_REGION" >/dev/null 2>&1 || \
  gcloud kms keyrings create cloudbank-ms67 --location "$GCP_REGION"
gcloud kms keys describe image-signing --keyring cloudbank-ms67 --location "$GCP_REGION" >/dev/null 2>&1 || \
  gcloud kms keys create image-signing --keyring cloudbank-ms67 --location "$GCP_REGION" \
    --purpose asymmetric-signing --default-algorithm ec-sign-p256-sha256 --protection-level software

for service in "${ms67_services[@]}"; do
  secret="cloudbank-${service}-external"
  gcloud secrets describe "$secret" >/dev/null 2>&1 || \
    gcloud secrets create "$secret" --replication-policy user-managed --locations "$GCP_REGION" \
      --labels environment=non-production,milestone=ms67
done

kubectl create namespace "$GKE_NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -
kubectl label namespace "$GKE_NAMESPACE" \
  pod-security.kubernetes.io/enforce=restricted pod-security.kubernetes.io/enforce-version=latest \
  environment=non-production --overwrite
helm repo add external-secrets https://charts.external-secrets.io >/dev/null
helm repo add jetstack https://charts.jetstack.io >/dev/null
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx >/dev/null
helm repo update >/dev/null
helm upgrade --install external-secrets external-secrets/external-secrets \
  --version "$EXTERNAL_SECRETS_CHART_VERSION" \
  --namespace external-secrets --create-namespace --wait --timeout 10m
helm upgrade --install cert-manager jetstack/cert-manager \
  --version "$CERT_MANAGER_CHART_VERSION" --namespace cert-manager --create-namespace \
  --set crds.enabled=true --wait --timeout 10m
helm upgrade --install ingress-nginx ingress-nginx/ingress-nginx \
  --version "$INGRESS_NGINX_CHART_VERSION" --namespace ingress-nginx --create-namespace \
  --set controller.service.loadBalancerIP="$ingress_ip" \
  --set controller.service.annotations.cloud\.google\.com/l4-rbs=enabled \
  --wait --timeout 15m

project_number="$(gcloud projects describe "$GCP_PROJECT_ID" --format='value(projectNumber)')"
principal="principal://iam.googleapis.com/projects/${project_number}/locations/global/workloadIdentityPools/${GCP_PROJECT_ID}.svc.id.goog/subject/ns/${GKE_NAMESPACE}/sa/cloudbank-secret-reader"
kubectl -n "$GKE_NAMESPACE" create serviceaccount cloudbank-secret-reader --dry-run=client -o yaml | kubectl apply -f -
for service in "${ms67_services[@]}"; do
  gcloud secrets add-iam-policy-binding "cloudbank-${service}-external" \
    --role roles/secretmanager.secretAccessor --member "$principal" >/dev/null
done

otel_principal="principal://iam.googleapis.com/projects/${project_number}/locations/global/workloadIdentityPools/${GCP_PROJECT_ID}.svc.id.goog/subject/ns/observability/sa/otel-collector"
for role in roles/monitoring.metricWriter roles/logging.logWriter roles/cloudtrace.agent; do
  gcloud projects add-iam-policy-binding "$GCP_PROJECT_ID" --role "$role" --member "$otel_principal" >/dev/null
done
active_account="$(gcloud auth list --filter=status:ACTIVE --format='value(account)' | head -n 1)"
gcloud kms keys add-iam-policy-binding image-signing --keyring cloudbank-ms67 \
  --location "$GCP_REGION" --role roles/cloudkms.signerVerifier --member "user:$active_account" >/dev/null

echo "Platform bootstrap is complete. Add the following NS records at the parent DNS zone:"
gcloud dns managed-zones describe "$DNS_ZONE_NAME" --format='value(nameServers)'
echo "Ingress address: $ingress_ip"
echo "No secret versions were created. Add them through Secret Manager before deployment."
