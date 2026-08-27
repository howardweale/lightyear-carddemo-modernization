#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$project_dir/python-runtime.sh"
lightyear_resolve_python
export PYTHONPATH="$project_dir/extensions/runtime:$project_dir/src"

action="${1:-verify}"
canonical="$project_dir/extensions/pli/attestation"
generated="$project_dir/work/pli-build-attestation-$action"

build_outputs() {
  local output_root="$1"
  local source_commit="$2"
  rm -rf "$output_root"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_extensions build-pli-attestation \
    --project-root "$project_dir" \
    --output-root "$output_root" \
    --source-commit "$source_commit"
}

case "$action" in
  build)
    source_commit="$(git -C "$project_dir" rev-parse HEAD)"
    build_outputs "$generated" "$source_commit"
    mkdir -p "$canonical"
    for filename in \
      pli-auth-risk-candidate.jar \
      TEST-MixedPliAuthorizationAttestation.xml \
      dependencies.json sbom.cdx.json build.attestation.json build.receipt.json; do
      rm -f "$canonical/$filename"
    done
    cp "$generated/"* "$canonical/"
    ;;
  ci-build)
    source_commit="${GITHUB_SHA:-$(git -C "$project_dir" rev-parse HEAD)}"
    build_outputs "$generated" "$source_commit"
    ;;
  verify)
    source_commit="$($LIGHTYEAR_PYTHON_BIN -c 'import json,sys; print(json.load(open(sys.argv[1]))["source_commit"])' "$canonical/build.receipt.json")"
    build_outputs "$generated" "$source_commit"
    "$LIGHTYEAR_PYTHON_BIN" -m unittest extensions.tests.test_pli_build_attestation -v
    for expected in "$canonical/"*; do
      cmp "$expected" "$generated/$(basename "$expected")"
    done
    ;;
  *)
    echo "Usage: ./pli-build-attestation.sh [build|verify|ci-build]" >&2
    exit 2
    ;;
esac

artifact_root="$canonical"
if [[ "$action" == "ci-build" ]]; then
  artifact_root="$generated"
fi
"$LIGHTYEAR_PYTHON_BIN" -m lightyear_extensions validate-pli-attestation \
  --project-root "$project_dir" \
  --artifact-root "$artifact_root"
echo "PL/I candidate JAR, JUnit-compatible results, SBOM, provenance, and development signature are bound; live z/OS equivalence remains blocked."
