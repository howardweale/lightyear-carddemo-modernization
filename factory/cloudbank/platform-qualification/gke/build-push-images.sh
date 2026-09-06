#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

ms67_require_tools gcloud docker jq python cosign trivy sha256sum
ms67_require_environment
ms67_require_mutation_ack
[[ "${JAVA_BASE_IMAGE:-}" =~ @sha256:[0-9a-f]{64}$ ]] || {
  echo "JAVA_BASE_IMAGE must use an immutable sha256 digest" >&2; exit 2;
}
[[ -f "$OTEL_JAVA_AGENT_JAR" ]] || { echo "OTEL_JAVA_AGENT_JAR was not found" >&2; exit 2; }
[[ "$(sha256sum "$OTEL_JAVA_AGENT_JAR" | cut -d' ' -f1)" == "$OTEL_JAVA_AGENT_SHA256" ]] || {
  echo "OpenTelemetry Java agent digest does not match" >&2; exit 2;
}
[[ $# -eq 3 ]] || { echo "Usage: build-push-images.sh MATERIALIZED_TARGET MS64_RECEIPT OUTPUT_ROOT" >&2; exit 2; }
target="$(cd "$1" && pwd)"
ms64_receipt="$(cd "$(dirname "$2")" && pwd)/$(basename "$2")"
output_root="$3"
mkdir -p "$output_root"
[[ -z "$(find "$output_root" -mindepth 1 -maxdepth 1 -print -quit)" ]] || {
  echo "OUTPUT_ROOT must be fresh" >&2; exit 2;
}

retry_registry_push() {
  local attempt delay=5
  for attempt in 1 2 3 4 5; do
    if docker push "$1"; then
      return 0
    fi
    [[ "$attempt" -lt 5 ]] || return 1
    echo "Artifact Registry push attempt $attempt failed; retrying in ${delay}s" >&2
    sleep "$delay"
    delay=$((delay * 2))
  done
}

(cd "$target" && mvn -DskipTests -Djkube.skip=true -Ddependency-check.skip=true package)
ms64_sha="$(jq -er '.content_sha256 | select(test("^[0-9a-f]{64}$"))' "$ms64_receipt")"
registry="$GCP_REGION-docker.pkg.dev/$GCP_PROJECT_ID/$ARTIFACT_REPOSITORY"
cosign_key="gcpkms://projects/$GCP_PROJECT_ID/locations/$GCP_REGION/keyRings/cloudbank-ms67/cryptoKeys/image-signing"
rows='[]'
for service in "${ms67_services[@]}"; do
  jar="$(find "$target/$service/target" -maxdepth 1 -type f -name '*.jar' ! -name '*sources*' ! -name '*javadoc*' | head -n 1)"
  [[ -f "$jar" ]] || { echo "Executable JAR not found for $service" >&2; exit 2; }
  stage="$output_root/stage-$service"
  mkdir -p "$stage"
  cp "$jar" "$stage/application.jar"
  cp "$OTEL_JAVA_AGENT_JAR" "$stage/opentelemetry-javaagent.jar"
  cp "$ms67_gke_dir/Dockerfile.runtime" "$stage/Dockerfile"
  tag="$registry/$service:ms67-$(git -C "$ms67_project_root" rev-parse --short=12 HEAD)"
  docker build --build-arg BASE_IMAGE="$JAVA_BASE_IMAGE" --build-arg BUILD_GENERATION=baseline \
    --tag "$tag" "$stage"
  retry_registry_push "$tag"
  digest="$(gcloud artifacts docker images describe "$tag" --format='value(image_summary.digest)')"
  [[ "$digest" =~ ^sha256:[0-9a-f]{64}$ ]] || { echo "Missing registry digest for $service" >&2; exit 2; }
  reference="$registry/$service@$digest"
  jq -n --arg service "$service" --arg source "$(git -C "$ms67_project_root" rev-parse HEAD)" \
    --arg image "$reference" '{builder:{id:"lightyear-ms67-operator"},buildType:"https://lightyear.ai/cloudbank/ms67",invocation:{parameters:{service:$service}},materials:[{uri:"git+https://github.com/howardweale/lightyear-carddemo-modernization",digest:{sha1:$source}},{uri:$image,digest:{sha256:($image|split("@sha256:")[1])}}]}' \
    > "$output_root/provenance-$service.json"
  cosign sign --yes --key "$cosign_key" "$reference"
  cosign attest --yes --key "$cosign_key" --type slsaprovenance \
    --predicate "$output_root/provenance-$service.json" "$reference"
  cosign verify --key "$cosign_key" "$reference" >/dev/null
  cosign verify-attestation --key "$cosign_key" --type slsaprovenance "$reference" >/dev/null
  scan="$output_root/scan-$service.json"
  trivy image --quiet --format json --output "$scan" "$reference"
  critical="$(jq '[.Results[]?.Vulnerabilities[]? | select(.Severity == "CRITICAL")] | length' "$scan")"
  high="$(jq '[.Results[]?.Vulnerabilities[]? | select(.Severity == "HIGH")] | length' "$scan")"
  scan_sha="$(sha256sum "$scan" | cut -d' ' -f1)"
  jq -n --arg service "$service" --arg image "$reference" --arg scan_sha256 "$scan_sha" \
    --argjson critical "$critical" --argjson high "$high" \
    '{service:$service,image:$image,critical:$critical,high:$high,scan_sha256:$scan_sha256}' \
    > "$output_root/scan-summary-$service.json"
  [[ "$critical" -eq 0 && "$high" -eq 0 ]] || { echo "High or critical findings for $service" >&2; exit 1; }
  rm "$scan"
  rows="$(jq --arg service "$service" --arg reference "$reference" '. + [{service:$service,reference:$reference}]' <<<"$rows")"
done

MS64_SHA="$ms64_sha" IMAGE_ROWS="$rows" OUTPUT_PATH="$output_root/image-lock.json" \
PYTHONPATH="$ms67_project_root/src" python - <<'PY'
import json, os
from pathlib import Path
from lightyear_data.contracts import seal
payload = seal({
    "schema_version": "1.0",
    "lock_type": "lightyear-cloudbank-ms65-image-lock",
    "release": "0.65.0",
    "source_ms64_receipt_sha256": os.environ["MS64_SHA"],
    "images": json.loads(os.environ["IMAGE_ROWS"]),
})
Path(os.environ["OUTPUT_PATH"]).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
PY
rm -r "$output_root"/stage-*
echo "Created digest-only image lock: $output_root/image-lock.json"
