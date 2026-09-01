#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$project_dir/python-runtime.sh"
lightyear_resolve_python
export PYTHONPATH="$project_dir/src"
action="${1:-verify}"
legacy_root="${2:-${CARDDEMO_UPSTREAM_ROOT:-$project_dir/../carddemo-upstream}}"

case "$action" in
  build)
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_data build --legacy-root "$legacy_root" --output-root "$project_dir"
    ;;
  verify)
    output="$project_dir/work/data-modernization-verify"
    rm -rf "$output"
    mkdir -p "$output"
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_data build --legacy-root "$legacy_root" --output-root "$output"
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_data validate --project-root "$output"
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_data verify-offline --project-root "$output"
    for relative in \
      canonical/authfrds.model.json source/authfrds.dcl-contract.json \
      source/authfrds.embedded-sql.json mappings/authfrds-postgresql.json \
      mappings/authfrds-oracle.json fixtures/authfrds.fixtures.json \
      postgres/authfrds.sql oracle/authfrds.sql receipts/authfrds.offline.receipt.json \
      receipts/authfrds.oracle-offline.receipt.json receipts/authfrds.target-plan.json; do
      cmp "$project_dir/data-modernization/$relative" "$output/data-modernization/$relative"
    done
    for relative in \
      semantic-core/database-semantic-core.json \
      semantic-core/authfrds.canonical-schema.json \
      semantic-core/authfrds.profile-contract.json \
      semantic-core/authfrds.schema-transformation-plan.json \
      semantic-core/authfrds.compatibility-ledger.json \
      semantic-core/authfrds.adapter-conformance.receipt.json; do
      cmp "$project_dir/data-modernization/$relative" "$output/data-modernization/$relative"
    done
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_data verify-semantic-core --project-root "$output"
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_data verify-oracle-postgresql-proof --project-root "$project_dir"
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_data verify-stored-logic-qualification --project-root "$project_dir"
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_data verify-db2-semantic-adapter --project-root "$project_dir"
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_data verify-oracle-source-qualification --project-root "$project_dir"
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_data verify-oracle-dialect-corpus --project-root "$project_dir"
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_data verify-oracle-semantic-coverage --project-root "$project_dir"
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_data verify-oracle-core-sql-coverage --project-root "$project_dir"
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_data verify-oracle-plsql-coverage --project-root "$project_dir"
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_data verify-sap-ase-source-adapter --project-root "$project_dir"
    echo "AUTHFRDS database semantic core, adapters, ledger, fixtures, and receipts are deterministic."
    ;;
  semantic-core)
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_data verify-semantic-core --project-root "$project_dir"
    ;;
  oracle-postgresql-proof)
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_data verify-oracle-postgresql-proof --project-root "$project_dir"
    ;;
  stored-logic)
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_data verify-stored-logic-qualification --project-root "$project_dir"
    ;;
  db2-semantic)
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_data verify-db2-semantic-adapter --project-root "$project_dir"
    ;;
  oracle-source)
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_data verify-oracle-source-qualification --project-root "$project_dir"
    ;;
  oracle-dialect)
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_data verify-oracle-dialect-corpus --project-root "$project_dir"
    ;;
  oracle-coverage)
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_data verify-oracle-semantic-coverage --project-root "$project_dir"
    ;;
  oracle-core-sql)
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_data verify-oracle-core-sql-coverage --project-root "$project_dir"
    ;;
  oracle-plsql)
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_data verify-oracle-plsql-coverage --project-root "$project_dir"
    ;;
  ase-source)
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_data verify-sap-ase-source-adapter --project-root "$project_dir"
    ;;
  live|live-postgres)
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_data verify-docker --target postgresql --project-root "$project_dir"
    ;;
  live-oracle)
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_data verify-docker --target oracle --project-root "$project_dir"
    ;;
  live-all)
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_data verify-docker --target all --project-root "$project_dir"
    ;;
  sign)
    : "${FACTORYDARK_DATA_EQUIVALENCE_KEY:?Set FACTORYDARK_DATA_EQUIVALENCE_KEY}"
    receipt="$project_dir/work/data-modernization/live-multi-target.receipt.json"
    output="$project_dir/work/data-modernization/live-multi-target.signed.receipt.json"
    if [[ ! -f "$receipt" ]]; then
      receipt="$project_dir/work/data-modernization/live-postgresql.receipt.json"
      output="$project_dir/work/data-modernization/live-postgresql.signed.receipt.json"
    fi
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_data sign --receipt "$receipt" --output "$output"
    ;;
  *) echo "Usage: ./data-modernization.sh [build|verify|semantic-core|oracle-postgresql-proof|stored-logic|db2-semantic|oracle-source|oracle-dialect|oracle-coverage|oracle-core-sql|oracle-plsql|ase-source|live-postgres|live-oracle|live-all|sign] [optional-carddemo-upstream-root]" >&2; exit 2 ;;
esac
