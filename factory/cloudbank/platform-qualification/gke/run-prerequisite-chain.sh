#!/usr/bin/env bash
set -euo pipefail

[[ $# -eq 5 ]] || {
  echo "Usage: run-prerequisite-chain.sh PROJECT_ROOT SOURCE_ROOT WORK_ROOT EXPORT_ROOT SIGNER" >&2
  exit 2
}

project_root="$(cd "$1" && pwd)"
source_root="$2"
work_root="$3"
export_root="$4"
signer="$5"

[[ -n "${LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY:-}" ]] || {
  echo "LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY is required" >&2
  exit 2
}
[[ -n "$signer" ]] || { echo "SIGNER is required" >&2; exit 2; }
for path in "$source_root" "$work_root" "$export_root"; do
  [[ ! -e "$path" ]] || { echo "Path must be fresh: $path" >&2; exit 2; }
done

required_tools=(docker git jq java mvn openssl python3 sha256sum)
for tool in "${required_tools[@]}"; do
  command -v "$tool" >/dev/null || { echo "Required tool is missing: $tool" >&2; exit 2; }
done
docker info >/dev/null

pinned_commit="4f41b16d00c45503f691836fee8138010c969e86"
pinned_root_tree="6aa92e89c783f123c4da8d7ae18108004a4f4a99"
pinned_subtree_tree="bd918386209f284a1ed31802555740eb34b75348"

git clone --filter=blob:none --no-checkout \
  https://github.com/oracle/microservices-backend.git "$source_root"
git -C "$source_root" sparse-checkout init --cone
git -C "$source_root" sparse-checkout set cloudbank-v5
git -C "$source_root" fetch --depth=1 origin "$pinned_commit"
git -C "$source_root" checkout --detach "$pinned_commit"

[[ "$(git -C "$source_root" rev-parse HEAD)" == "$pinned_commit" ]]
[[ "$(git -C "$source_root" rev-parse 'HEAD^{tree}')" == "$pinned_root_tree" ]]
[[ "$(git -C "$source_root" rev-parse 'HEAD:cloudbank-v5')" == "$pinned_subtree_tree" ]]

cd "$project_root"
./cloudbank-edge-ai.sh verify-source "$source_root"

oracle_image="gvenzl/oracle-free:23.26.1-slim-faststart"
postgres_image="postgres:16-alpine"
docker pull "$oracle_image"
docker pull "$postgres_image"
oracle_image_id="$(docker image inspect --format '{{.Id}}' "$oracle_image" | sed 's/^sha256://')"
postgres_image_id="$(docker image inspect --format '{{.Id}}' "$postgres_image" | sed 's/^sha256://')"
[[ "$oracle_image_id" =~ ^[0-9a-f]{64}$ ]]
[[ "$postgres_image_id" =~ ^[0-9a-f]{64}$ ]]

mkdir -p \
  "$work_root/ms54" "$work_root/ms55" "$work_root/ms56" "$work_root/ms57" \
  "$work_root/ms58" "$work_root/ms59" "$work_root/ms60" "$work_root/ms61" \
  "$work_root/ms62" "$work_root/ms63" "$work_root/ms64"

ms54_build="$work_root/ms54/cloudbank-source-build.receipt.json"
ms54_oracle="$work_root/ms54/cloudbank-oracle-runtime.receipt.json"
ms55="$work_root/ms55/cloudbank-customer-postgresql.receipt.json"
ms56="$work_root/ms56/cloudbank-customer-dark-factory.receipt.json"
ms57="$work_root/ms57/cloudbank-customer-production-qualification.receipt.json"
ms58="$work_root/ms58/cloudbank-transaction-wave.receipt.json"
ms59="$work_root/ms59/cloudbank-transaction-core.receipt.json"
ms60="$work_root/ms60/cloudbank-native-transaction-wave.receipt.json"
ms61="$work_root/ms61/cloudbank-oracle-postgresql-equivalence.receipt.json"
ms62="$work_root/ms62/cloudbank-production-oauth.receipt.json"
ms63="$work_root/ms63/cloudbank-checks-messaging.receipt.json"
ms64="$work_root/ms64/cloudbank-edge-ai.receipt.json"

echo "Running signed MS #54 source build"
./cloudbank-executable-baseline.sh source-build "$source_root" "$ms54_build" "$signer"
./cloudbank-executable-baseline.sh verify-receipt "$ms54_build"

echo "Running signed MS #54 Oracle runtime"
./cloudbank-executable-baseline.sh oracle-runtime \
  "$source_root" "$ms54_build" "$oracle_image_id" "$ms54_oracle" "$signer"
./cloudbank-executable-baseline.sh verify-receipt "$ms54_oracle"

echo "Running signed MS #55 PostgreSQL mapping"
./cloudbank-customer-postgresql.sh native-postgresql \
  "$source_root" "$ms54_oracle" "$postgres_image_id" "$ms55" "$signer"
./cloudbank-customer-postgresql.sh verify-receipt "$ms55"

echo "Running signed MS #56 dark-factory workcell"
./cloudbank-dark-factory.sh run \
  "$source_root" "$ms54_oracle" "$ms55" "$work_root/ms56" "$signer"
./cloudbank-dark-factory.sh verify-receipt "$ms56"

echo "Running signed MS #57 production-shaped customer qualification"
./cloudbank-production-qualification.sh run \
  "$source_root" "$ms56" "$work_root/ms57" "$signer"
./cloudbank-production-qualification.sh verify-receipt "$ms57"

echo "Running signed MS #58 transaction-wave admission"
./cloudbank-transaction-wave.sh admit \
  "$source_root" "$ms57" "$ms58" "$signer"
./cloudbank-transaction-wave.sh verify-receipt "$ms58"

echo "Running signed MS #59 PostgreSQL transaction core"
./cloudbank-transaction-core.sh run \
  "$source_root" "$ms58" "$work_root/ms59" "$signer"
./cloudbank-transaction-core.sh verify-receipt "$ms59"

echo "Running signed MS #60 native Account/Transfer wave"
./cloudbank-native-wave.sh run \
  "$source_root" "$ms59" "$work_root/ms60" "$signer"
./cloudbank-native-wave.sh verify-receipt "$ms60"

echo "Running signed MS #61 Oracle/PostgreSQL equivalence"
./cloudbank-oracle-equivalence.sh run \
  "$source_root" "$ms57" "$ms60" "$work_root/ms61" "$signer"
./cloudbank-oracle-equivalence.sh verify-receipt "$ms61"

echo "Running signed MS #62 production OAuth"
./cloudbank-production-oauth.sh run \
  "$source_root" "$ms61" "$work_root/ms62" "$signer"
./cloudbank-production-oauth.sh verify-receipt "$ms62"

echo "Running signed MS #63 durable Checks messaging"
./cloudbank-checks-messaging.sh run \
  "$source_root" "$ms62" "$work_root/ms63" "$signer"
./cloudbank-checks-messaging.sh verify-receipt "$ms63"

echo "Running signed MS #64 complete eight-service target"
./cloudbank-edge-ai.sh run \
  "$source_root" "$ms63" "$ms57" "$work_root/ms64" "$signer"
./cloudbank-edge-ai.sh verify-receipt "$ms64"

mkdir -p "$export_root"
install -m 0600 "$ms54_build" "$export_root/ms54-source-build.receipt.json"
install -m 0600 "$ms54_oracle" "$export_root/ms54-oracle-runtime.receipt.json"
install -m 0600 "$ms55" "$export_root/ms55-postgresql.receipt.json"
install -m 0600 "$ms56" "$export_root/ms56-dark-factory.receipt.json"
install -m 0600 "$ms57" "$export_root/ms57-production-qualification.receipt.json"
install -m 0600 "$ms58" "$export_root/ms58-transaction-wave.receipt.json"
install -m 0600 "$ms59" "$export_root/ms59-transaction-core.receipt.json"
install -m 0600 "$ms60" "$export_root/ms60-native-wave.receipt.json"
install -m 0600 "$ms61" "$export_root/ms61-equivalence.receipt.json"
install -m 0600 "$ms62" "$export_root/ms62-oauth.receipt.json"
install -m 0600 "$ms63" "$export_root/ms63-checks.receipt.json"
install -m 0600 "$ms64" "$export_root/ms64-edge-ai.receipt.json"

PROJECT_ROOT="$project_root" EXPORT_ROOT="$export_root" SIGNER="$signer" \
PYTHONPATH="$project_root/src" python3 - <<'PY'
import json
import os
from pathlib import Path

from lightyear_data.contracts import content_hash, sign, verify_signature

root = Path(os.environ["EXPORT_ROOT"])
entries = []
for path in sorted(root.glob("ms*.receipt.json")):
    receipt = json.loads(path.read_text(encoding="utf-8"))
    if receipt.get("content_sha256") != content_hash(receipt):
        raise SystemExit(f"Receipt content hash is invalid: {path.name}")
    if not verify_signature(receipt, os.environ["LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY"]):
        raise SystemExit(f"Receipt signature is invalid: {path.name}")
    entries.append({
        "file": path.name,
        "receipt_type": receipt.get("receipt_type"),
        "release": receipt.get("release"),
        "status": receipt.get("status"),
        "content_sha256": receipt["content_sha256"],
    })

if len(entries) != 12:
    raise SystemExit(f"Expected 12 prerequisite receipts, found {len(entries)}")

manifest = sign({
    "schema_version": "1.0",
    "receipt_type": "lightyear-cloudbank-ms54-ms64-execution-chain",
    "release": "0.67.0",
    "signer": os.environ["SIGNER"],
    "source_commit": "4f41b16d00c45503f691836fee8138010c969e86",
    "receipt_count": len(entries),
    "receipts": entries,
    "raw_output_persisted": False,
    "credentials_persisted": False,
    "production_data_observed": False,
    "status": "passed",
}, os.environ["LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY"], os.environ["SIGNER"])
(root / "ms54-ms64-chain.receipt.json").write_text(
    json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
PY

(cd "$export_root" && sha256sum ./*.json > SHA256SUMS)
echo "MS54_MS64_RECEIPT_COUNT=12"
echo "MS54_MS64_EXECUTION_CHAIN=PASSED"
