# CardDemo Spring Batch candidate

v0.18 also includes `CicsVsamAccountViewService`, a bounded read-only service seam for CICS
transaction `CAVW`. It preserves the legacy lookup order across the CardXref alternate-index path,
account master, and customer master while exposing an explicit read trace and zero-mutation result.
It is verified locally but does not claim to emulate CICS task semantics or VSAM locking/recovery.

This module is a Java 17, Spring Boot 4.1, Spring Batch 6 candidate implementation of CardDemo's
`CBACT04C` interest-calculation workload. It deliberately remains behind the repository's Python
oracle and comparator: passing the differential test is the acceptance contract.

## Design

- A tasklet models the legacy batch unit of work and its all-or-nothing file publication boundary.
- Fixed-width codecs preserve the CardDemo 50, 300, and 350-byte ASCII layouts.
- Signed zoned-decimal codecs preserve COBOL overpunch semantics.
- `BigDecimal` with scale 2 and `RoundingMode.DOWN` reproduces COBOL truncation.
- An in-memory H2 database stores Spring Batch metadata for each local invocation.
- `source-faithful` is the default final-account policy; `intended` is available for an explicit
  behavior-change experiment.

## Build

Windows PowerShell:

```powershell
.\mvnw.cmd test package
```

macOS or Linux:

```bash
./mvnw test package
```

The bounded mixed PL/I service also has a dependency-free, reproducible attestation build:

```bash
../pli-build-attestation.sh verify
```

That path compiles only the attested service seam, emits a deterministic JAR and JUnit-compatible
report, and binds them to an SBOM and signed provenance. The Maven build remains the full Spring
Boot candidate verification path.

The full repository verification scripts build the candidate, create deterministic inputs, run the
oracle and candidate, and compare their business outputs:

```powershell
..\verify.ps1
```

```bash
../verify.sh
```

## Run directly

```powershell
java -jar .\target\carddemo-spring-batch-candidate-0.1.0-SNAPSHOT.jar `
  --carddemo.input-dir=C:\path\to\input `
  --carddemo.output-dir=C:\path\to\output `
  --carddemo.processing-date=2022071800 `
  --carddemo.timestamp=2022-07-18-00.00.00.000000 `
  --carddemo.final-account-policy=source-faithful
```

Required inputs are `acctdata.txt`, `cardxref.txt`, `discgrp.txt`, and `tcatbal.txt`. Outputs are
`acctdata.txt`, `transactions.txt`, and `candidate-receipt.json`.
