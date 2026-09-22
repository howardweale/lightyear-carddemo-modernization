# Oracle native execution admission gate

MS #51 turns the completed 500-behavior, 2,000-case bounded catalog into a strict native-evidence
contract for Oracle Database 19c and Oracle AI Database 26ai. The manifest requires 4,000 native
case executions: every case on both database lanes.

| Evidence scope | Recorded result |
| --- | --- |
| Separate native Oracle 26ai ↔ AlloyDB campaign | **260/260 matching pairs** — [published execution evidence](../../docs/receipts/oracle26ai-alloydb-types260-20260917/README.md) |
| This committed MS51 readiness snapshot | **`native_executed_case_count: 0`** under its per-case harness-hash contract |

This snapshot does not aggregate the paired campaign's receipts. Its zero is not a
project-wide native execution total or a requirement to finish all 4,000 executions
before reporting partial progress. See [the count-scope guide](../../docs/oracle-native-evidence.md).

The first native family, `types/number`, now has 40 materialized case/version harnesses
(20 cases on each version). These files have been locally checked and mock-tested;
this committed MS51 readiness snapshot retains zero native executions. See the [pilot runbook and evidence audit](../../docs/oracle-evidence-roadmap.md)
for environment prerequisites, commands, reporting scope, and remaining work.

```bash
PYTHONPATH=src python3 -m lightyear_data build-oracle-native-execution-gate --project-root .
PYTHONPATH=src python3 -m lightyear_data verify-oracle-native-execution-gate --project-root .
./data-modernization.sh oracle-native-gate
```

An external native receipt can be admitted only with a runtime verification key:

```bash
export LIGHTYEAR_ORACLE_NATIVE_EVIDENCE_KEY='provided-at-runtime'
PYTHONPATH=src python3 -m lightyear_data verify-oracle-native-receipt \
  --project-root . --receipt /approved/evidence/oracle-native.receipt.json
```

The contract requires external-wallet authentication, exact database and session identity, one
unique result per catalog case, exact bounded-expectation and SQL-harness hashes, diagnostic codes,
timestamps, runner identity, content addressing, and an HMAC signature. Usernames, passwords,
wallets, raw SQL output, and verification keys must not be committed.

The original MS51 milestone established admission rather than native execution. The current
readiness snapshot includes the first 40 harnesses; it does not execute an Oracle database.
The zero counts and false qualification flags in this snapshot describe only its
own evidence. Separate native paired results and CloudBank qualification receipts
retain their own verified scope; this gate does not revoke or aggregate them.
