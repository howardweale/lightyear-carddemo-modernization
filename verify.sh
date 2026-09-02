#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
verification_dir="$project_dir/work/java-candidate-verify"
candidate_jar="$project_dir/candidate-java/target/carddemo-spring-batch-candidate-0.1.0-SNAPSHOT.jar"

source "$project_dir/python-runtime.sh"
lightyear_resolve_python
export PYTHONPATH="$project_dir/src"

default_maven_home="${MAVEN_USER_HOME:-${HOME}/.m2}"
if { [[ -e "$default_maven_home" ]] && [[ ! -w "$default_maven_home" ]]; } || \
   { [[ ! -e "$default_maven_home" ]] && [[ ! -w "$(dirname "$default_maven_home")" ]]; }; then
  export MAVEN_USER_HOME="$project_dir/work/.m2"
  export MAVEN_OPTS="${MAVEN_OPTS:-} -Dmaven.repo.local=$project_dir/work/.m2/repository"
fi

"$LIGHTYEAR_PYTHON_BIN" -m lightyear_common prerequisites --project-root "$project_dir"
"$LIGHTYEAR_PYTHON_BIN" -m lightyear_common receipt-claims --project-root "$project_dir"
"$LIGHTYEAR_PYTHON_BIN" -m lightyear_common scripts --project-root "$project_dir"
"$LIGHTYEAR_PYTHON_BIN" -m unittest discover -s "$project_dir/tests" -v
"$LIGHTYEAR_PYTHON_BIN" -m carddemo_oracle validate-normalizations \
  --ledger "$project_dir/spec/comparison-normalizations.json"
"$project_dir/model-workcell.sh" validate
"$project_dir/hardened-execution.sh" verify
"$project_dir/data-modernization.sh" verify
"$project_dir/migration-rehearsal.sh" verify
"$project_dir/knowledge-graph.sh" verify
"$project_dir/extension-foundation.sh" verify
"$project_dir/mainframe-access.sh" verify
"$project_dir/zosmf-adapter.sh" verify
"$project_dir/collection-appliance.sh" verify
"$project_dir/cobol-qualification.sh" verify
"$project_dir/pli-qualification.sh" verify
"$project_dir/jcl-qualification.sh" verify
"$project_dir/pli-conformance.sh" verify
"$project_dir/pli-modernization.sh" verify
"$project_dir/pli-build-attestation.sh" verify
"$project_dir/cloudbank-reference-estate.sh" verify
"$project_dir/cloudbank-executable-baseline.sh" verify
"$project_dir/cloudbank-customer-postgresql.sh" verify
"$project_dir/cloudbank-dark-factory.sh" verify
"$project_dir/cloudbank-production-qualification.sh" verify
"$project_dir/composite-estate.sh" verify
"$project_dir/runtime-evidence.sh" verify
"$project_dir/semantic-memory.sh" validate
"$project_dir/portfolio-factory.sh" verify
"$project_dir/factory-qualification.sh" verify
"$project_dir/durable-factory.sh" verify
"$project_dir/live-control-tower.sh" verify
"$project_dir/cics-vsam-readiness.sh" verify
"$project_dir/asm-readiness.sh" verify
"$project_dir/ims-readiness.sh" verify
"$project_dir/audit-control-tower.sh" verify
"$project_dir/source-only-pilot.sh" verify
"$project_dir/integrated-pilot-qualification.sh" verify

(
  cd "$project_dir/candidate-java"
  ./mvnw test package
)

"$LIGHTYEAR_PYTHON_BIN" -m carddemo_oracle demo --work-dir "$verification_dir"

java -jar "$candidate_jar" \
  --carddemo.input-dir="$verification_dir/input" \
  --carddemo.output-dir="$verification_dir/candidate-output" \
  --carddemo.processing-date=2022071800 \
  --carddemo.timestamp=2022-07-18-00.00.00.000000 \
  --carddemo.final-account-policy=source-faithful

"$LIGHTYEAR_PYTHON_BIN" -m carddemo_oracle compare \
  --expected "$verification_dir/oracle-output" \
  --actual "$verification_dir/candidate-output" \
  --report "$verification_dir/comparison.json"
