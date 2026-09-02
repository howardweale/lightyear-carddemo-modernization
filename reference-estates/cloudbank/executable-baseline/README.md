# CloudBank executable source baseline

Milestone 54 converts the pinned CloudBank reference estate from a static inventory into a fail-closed execution contract. It does not claim that this repository's development environment ran CloudBank.

The baseline requires the complete pinned `cloudbank-v5` source tree at commit `4f41b16d00c45503f691836fee8138010c969e86`; it does not vendor that upstream source. The first build reproduces the seven-service set in the pinned upstream image-build script with Java 21 and Maven 3.6 or newer. The bounded Oracle proof then runs the seven existing `azn-server` Oracle Testcontainers integration tests against `gvenzl/oracle-free:23.26.1-slim-faststart`.

The pinned repository's sample and bootstrap rows are sufficient for this controlled source proof. Real customer or production data is neither present nor implied. It requires a separately authorized extract, profiling receipt, privacy controls, and reconciliation contract.

## Operator flow

Verify the static contract and an exact upstream checkout:

```bash
./cloudbank-executable-baseline.sh verify
./cloudbank-executable-baseline.sh verify-source ../cloudbank-upstream
```

On an authorized Java 21/Maven runtime, set `LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY` and build:

```bash
./cloudbank-executable-baseline.sh source-build \
  ../cloudbank-upstream work/cloudbank-source-build.receipt.json operator-id
```

On an authorized Docker runtime, inspect the pulled Oracle image to obtain its immutable SHA-256 image ID, then run the bounded native suite:

```bash
./cloudbank-executable-baseline.sh oracle-runtime \
  ../cloudbank-upstream \
  work/cloudbank-source-build.receipt.json \
  IMAGE_ID_SHA256 \
  work/cloudbank-oracle-runtime.receipt.json \
  operator-id
```

Receipts persist hashes and aggregate test results, not stdout, stderr, database passwords, tokens, or signing keys. Unsigned, source-drifted, toolchain-drifted, incomplete, skipped, failed, or overclaiming receipts are rejected.

PostgreSQL target selection and mapping remain false. They begin after an Oracle source-runtime receipt is admitted and after the first customer-service workcell is selected.
