# CloudBank native Account/Transfer transaction wave

MS #60 starts the generated Account and Transfer applications together and exercises their real
HTTP boundary against native PostgreSQL. The source checkout remains unchanged; the integrated
profile exists only inside the isolated generated workspace.

## Verify contracts and pinned source

```bash
./cloudbank-native-wave.sh verify
./cloudbank-native-wave.sh verify-source /path/to/cloudbank-upstream
```

## Run the integrated wave

Use the same `LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY` used for MS #59 and provide its passing
signed receipt:

```bash
./cloudbank-native-wave.sh run \
  /path/to/cloudbank-upstream \
  work/cloudbank-transaction-core/cloudbank-transaction-core.receipt.json \
  work/cloudbank-native-wave \
  howard-macbook

./cloudbank-native-wave.sh verify-receipt \
  work/cloudbank-native-wave/cloudbank-native-transaction-wave.receipt.json
```

The run can take several minutes. Progress messages identify packaging, service startup, behavioral
checks, and restarts. It starts one ephemeral PostgreSQL container and two real Spring Boot JARs on
loopback-only random ports. Credentials are generated per run and never written to evidence.

## Native gates

- Account and Transfer both become healthy and communicate through HTTP.
- Transfer requires an authenticated synthetic caller; Account requires the internal token and
  verifies the caller owns the source account.
- Invalid amounts, incorrect owners, insufficient funds, and incorrect internal tokens fail without
  changing balances or journals.
- Successful and concurrent opposite transfers conserve total value and use stable lock ordering.
- Duplicate commands replay without a second debit, including after separate Transfer and Account
  process restarts.
- Both executable JARs contain zero Oracle and zero MicroTx runtime libraries.

## Evidence boundary

A passing signed receipt closes the bounded target-side native Account/Transfer HTTP wave and its
local LRA-replacement gate. The authentication profile is synthetic development-only Basic auth,
not production OAuth/OIDC. This milestone does not execute the original transaction wave on Oracle,
migrate Checks/AQ messaging, qualify the remaining five deployable services, access production data,
or prove whole-application equivalence, migration completion, or production readiness.
