#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$project_dir/python-runtime.sh"
lightyear_resolve_python
legacy_commit="59cc6c2fd7ebd7ef7925cad552a01a4b8b6e4d5e"
action="${1:-verify}"
legacy_root="${2:-${CARDDEMO_UPSTREAM_ROOT:-}}"

if [[ -z "$legacy_root" && -d "$project_dir/../carddemo-upstream/app" ]]; then
  legacy_root="$project_dir/../carddemo-upstream"
fi

if [[ -z "$legacy_root" ]]; then
  legacy_root="$project_dir/work/carddemo-upstream"
  if [[ ! -d "$legacy_root/.git" ]]; then
    git -c core.autocrlf=false -c core.eol=lf clone --filter=blob:none --no-checkout \
      https://github.com/aws-samples/aws-mainframe-modernization-carddemo.git \
      "$legacy_root"
  fi
  git -C "$legacy_root" config --local core.autocrlf false
  git -C "$legacy_root" config --local core.eol lf
  git -C "$legacy_root" -c core.autocrlf=false -c core.eol=lf \
    checkout --detach --force "$legacy_commit"
fi

export PYTHONPATH="$project_dir/src"

if [[ "$action" == "build" ]]; then
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_knowledge_graph build \
    --legacy-root "$legacy_root" \
    --modern-root "$project_dir" \
    --semantic-inputs "$project_dir/knowledge/semantic-inputs.json" \
    --manifest "$project_dir/knowledge/mappings/carddemo-intcalc.json" \
    --manifest "$project_dir/knowledge/mappings/carddemo-cics-vsam-account-view.json" \
    --manifest "$project_dir/knowledge/mappings/carddemo-asm-date-format.json" \
    --manifest "$project_dir/knowledge/mappings/carddemo-ims-expired-authorization-purge.json" \
    --manifest "$project_dir/knowledge/mappings/carddemo-db2-authfrds.json" \
    --ontology "$project_dir/knowledge/ontology/relationships.json" \
    --output "$project_dir/knowledge/graph.snapshot.json.gz" \
    --receipt "$project_dir/knowledge/graph.receipt.json" \
    --evidence-pack "$project_dir/knowledge/evidence/source.pack.json.gz" \
    --evidence-receipt "$project_dir/knowledge/evidence/source.receipt.json" \
    --legacy-commit "$legacy_commit" \
    --modern-commit repository-content
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_knowledge_graph capabilities \
    --graph "$project_dir/knowledge/graph.snapshot.json.gz" \
    --cics-vsam-receipt "$project_dir/readiness/cics-vsam/readiness-receipt.json" \
    --asm-receipt "$project_dir/readiness/asm-date/readiness-receipt.json" \
    --ims-receipt "$project_dir/readiness/ims-expiry/readiness-receipt.json" \
    --pli-fragment "$project_dir/extensions/pli/pli.fragment.json" \
    --extension-catalog "$project_dir/extensions/catalog.json" \
    --pli-development-receipt "$project_dir/extensions/pli/modernization/development.receipt.json" \
    --postgres-data-receipt "$project_dir/data-modernization/receipts/authfrds.offline.receipt.json" \
    --oracle-data-receipt "$project_dir/data-modernization/receipts/authfrds.oracle-offline.receipt.json" \
    --data-rehearsal-receipt "$project_dir/data-modernization/rehearsal/receipt.json" \
    --campaign-receipt "$project_dir/extensions/adapters/campaign/campaign.receipt.json" \
    --output "$project_dir/knowledge/capabilities/mainframe-readiness.json"
elif [[ "$action" == "verify" ]]; then
  generated="$project_dir/work/knowledge-graph-verify"
  mkdir -p "$generated"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_knowledge_graph build \
    --legacy-root "$legacy_root" \
    --modern-root "$project_dir" \
    --semantic-inputs "$project_dir/knowledge/semantic-inputs.json" \
    --manifest "$project_dir/knowledge/mappings/carddemo-intcalc.json" \
    --manifest "$project_dir/knowledge/mappings/carddemo-cics-vsam-account-view.json" \
    --manifest "$project_dir/knowledge/mappings/carddemo-asm-date-format.json" \
    --manifest "$project_dir/knowledge/mappings/carddemo-ims-expired-authorization-purge.json" \
    --manifest "$project_dir/knowledge/mappings/carddemo-db2-authfrds.json" \
    --ontology "$project_dir/knowledge/ontology/relationships.json" \
    --output "$generated/graph.snapshot.json.gz" \
    --receipt "$generated/graph.receipt.json" \
    --evidence-pack "$generated/source.pack.json.gz" \
    --evidence-receipt "$generated/source.receipt.json" \
    --legacy-commit "$legacy_commit" \
    --modern-commit repository-content
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_knowledge_graph capabilities \
    --graph "$generated/graph.snapshot.json.gz" \
    --cics-vsam-receipt "$project_dir/readiness/cics-vsam/readiness-receipt.json" \
    --asm-receipt "$project_dir/readiness/asm-date/readiness-receipt.json" \
    --ims-receipt "$project_dir/readiness/ims-expiry/readiness-receipt.json" \
    --pli-fragment "$project_dir/extensions/pli/pli.fragment.json" \
    --extension-catalog "$project_dir/extensions/catalog.json" \
    --pli-development-receipt "$project_dir/extensions/pli/modernization/development.receipt.json" \
    --postgres-data-receipt "$project_dir/data-modernization/receipts/authfrds.offline.receipt.json" \
    --oracle-data-receipt "$project_dir/data-modernization/receipts/authfrds.oracle-offline.receipt.json" \
    --data-rehearsal-receipt "$project_dir/data-modernization/rehearsal/receipt.json" \
    --campaign-receipt "$project_dir/extensions/adapters/campaign/campaign.receipt.json" \
    --output "$generated/mainframe-readiness.json"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_knowledge_graph validate --graph "$generated/graph.snapshot.json.gz"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_knowledge_graph validate-evidence \
    --graph "$generated/graph.snapshot.json.gz" \
    --evidence-pack "$generated/source.pack.json.gz"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_knowledge_graph gaps --graph "$generated/graph.snapshot.json.gz"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_knowledge_graph compare-snapshots \
    --expected "$project_dir/knowledge/graph.snapshot.json.gz" \
    --actual "$generated/graph.snapshot.json.gz"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_knowledge_graph compare-evidence-packs \
    --expected "$project_dir/knowledge/evidence/source.pack.json.gz" \
    --actual "$generated/source.pack.json.gz"
  cmp "$project_dir/knowledge/graph.receipt.json" "$generated/graph.receipt.json"
  cmp "$project_dir/knowledge/evidence/source.receipt.json" "$generated/source.receipt.json"
  cmp "$project_dir/knowledge/capabilities/mainframe-readiness.json" "$generated/mainframe-readiness.json"
  echo "Knowledge graph snapshot is deterministic, current, and policy-complete."
else
  echo "Usage: ./knowledge-graph.sh [build|verify] [optional-carddemo-upstream-root]" >&2
  exit 2
fi
