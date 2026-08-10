#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
verification_dir="$project_dir/work/java-candidate-verify"
candidate_jar="$project_dir/candidate-java/target/carddemo-spring-batch-candidate-0.1.0-SNAPSHOT.jar"

export PYTHONPATH="$project_dir/src"

python3 -m unittest discover -s "$project_dir/tests" -v

(
  cd "$project_dir/candidate-java"
  ./mvnw test package
)

python3 -m carddemo_oracle demo --work-dir "$verification_dir"

java -jar "$candidate_jar" \
  --carddemo.input-dir="$verification_dir/input" \
  --carddemo.output-dir="$verification_dir/candidate-output" \
  --carddemo.processing-date=2022071800 \
  --carddemo.timestamp=2022-07-18-00.00.00.000000 \
  --carddemo.final-account-policy=source-faithful

python3 -m carddemo_oracle compare \
  --expected "$verification_dir/oracle-output" \
  --actual "$verification_dir/candidate-output" \
  --report "$verification_dir/comparison.json"
