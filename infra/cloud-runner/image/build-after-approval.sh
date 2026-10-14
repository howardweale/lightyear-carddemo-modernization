#!/usr/bin/env bash
# Phase 2 operator command ONLY, on an approved builder, after explicit spend approval.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
: "${PHASE2_APPROVAL:?record the stand-up approval reference}"
: "${BASE_IMAGE_PROJECT:?}"
: "${BASE_IMAGE_NAME:?}"
: "${BASE_IMAGE_ID:?}"
: "${BUNDLE_PATH:?}"
: "${BUNDLE_MANIFEST_SHA256:?}"
[[ "$BASE_IMAGE_ID" =~ ^[1-9][0-9]*$ ]]
actual_id="$(gcloud compute images describe "$BASE_IMAGE_NAME" --project "$BASE_IMAGE_PROJECT" --format='value(id)')"
[[ "$actual_id" == "$BASE_IMAGE_ID" ]] || { echo "Base image ID differs"; exit 1; }
python3 ../../../tools/check_cloud_image_bundle.py --root "$BUNDLE_PATH" --manifest-sha256 "$BUNDLE_MANIFEST_SHA256"
# supplied .pkrvars.hcl contains other reviewed builder/image/commit parameters.
packer init .
packer validate -var-file=local.pkrvars.hcl \
  -var="base_image_project=$BASE_IMAGE_PROJECT" -var="base_image_name=$BASE_IMAGE_NAME" \
  -var="base_image_id=$BASE_IMAGE_ID" -var="bundle_path=$BUNDLE_PATH" \
  -var="bundle_manifest_sha256=$BUNDLE_MANIFEST_SHA256" .
packer build -var-file=local.pkrvars.hcl \
  -var="base_image_project=$BASE_IMAGE_PROJECT" -var="base_image_name=$BASE_IMAGE_NAME" \
  -var="base_image_id=$BASE_IMAGE_ID" -var="bundle_path=$BUNDLE_PATH" \
  -var="bundle_manifest_sha256=$BUNDLE_MANIFEST_SHA256" .
# Fetch the output image numeric ID and archive API metadata + Packer manifest.
# Do not register the image for sealed runs until Phase 3 memory proof is reviewed.
