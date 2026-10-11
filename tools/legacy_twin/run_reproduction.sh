#!/usr/bin/env bash
# Operator-run only: existing Git and Docker; no install/provisioning/config changes.
set -euo pipefail
commit=${1:?exact reviewed commit required}
label=${2:-howard-mac}
[[ "$commit" =~ ^[0-9a-f]{40}$ ]] || { echo 'Expected a full commit SHA' >&2; exit 2; }
[[ $(git rev-parse HEAD) == "$commit" ]] || { echo 'Checkout is not the reviewed commit' >&2; exit 2; }
git diff --quiet
git diff --cached --quiet
command -v docker >/dev/null
base=ubuntu@sha256:f610ab94648195aa356059f5b41d6085c9d4d903c072430cdd1af7bdb646106b
out="work/operator-twin-${commit:0:12}"
[[ ! -e "$out" ]] || { echo 'Output already exists; preserve it and do not reuse' >&2; exit 2; }
mkdir -p "$out"
image="twin-repro-${commit:0:12}"
docker build --platform linux/amd64 -f tools/legacy_twin/reproducible.Containerfile -t "$image" . 2>&1 | tee "$out/toolchain-build.log"
docker image inspect "$image" --format '{{.Id}}' > "$out/toolchain-image-id.txt"
docker run --rm --network none --platform linux/amd64 \
  --mount type=bind,src="$PWD",dst=/source,readonly \
  --mount type=bind,src="$PWD/$out",dst=/output \
  --env PYTHONPATH=/source/src:/source --env PYTHONDONTWRITEBYTECODE=1 \
  --workdir /source "$image" \
  python3 -B -m tools.legacy_twin.reproducible_build build \
  --output /output/build --machine-id "$label" --host-kind operator-machine \
  --commit "$commit" --base-image "$base" 2>&1 | tee "$out/build.log"
printf '\nReturn this aggregate receipt to Howard’s Codex chat: %s/build/reproduction.json\n' "$out"
printf 'Preserve local logs and binaries. No z/OS equivalence or second-machine comparison is claimed until both receipts are checked.\n'
