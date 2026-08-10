# LIGHTYEAR CardDemo Local Oracle

A source-faithful, locally executable oracle, differential harness, and Java/Spring Batch candidate
for the CardDemo `INTCALC` batch workload. It is the first engineering slice of a verified
modernization factory.

The oracle runs on Windows, macOS, or Linux with Python 3.11 or newer and has no runtime
dependencies outside the Python standard library. The candidate uses Java 17, Spring Boot 4.1,
Spring Batch 6, Maven Wrapper, and an in-memory H2 Batch metadata store.

## What it does

1. Reads CardDemo-compatible fixed-width ASCII datasets.
2. Decodes COBOL signed zoned decimals, including overpunched signs.
3. Executes the interest-calculation behavior defined by `CBACT04C`.
4. Produces updated account records and generated transaction records.
5. Writes canonical JSON plus a hashed evidence receipt.
6. Compares a modernization candidate's output to the oracle output.

The included `candidate-java` module is the first modernization candidate. It consumes and emits
the same fixed-width records as the oracle, including COBOL signed zoned decimals.

This is a **temporary local oracle derived from source**, not independent proof of z/OS behavior.
It does not emulate VSAM locking, JES, Language Environment behavior, or EBCDIC collation. Replace
or corroborate it with captured z/OS executions before making production equivalence claims.

## Windows setup

Open PowerShell in the extracted project directory. The quickest path requires no package
installation:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\test.ps1
```

Run the deterministic demonstration:

```powershell
.\oracle.ps1 demo --work-dir .\work\demo
```

Build and differentially verify the Java/Spring Batch candidate:

```powershell
.\verify.ps1
```

This runs both Python and Java unit tests, packages the executable Spring Boot JAR, executes the
oracle and candidate on a deterministic fixture, and fails if any business field differs.

Optional editable installation for developers:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
carddemo-oracle demo --work-dir .\work\demo
```

The command creates:

```text
work/demo/
├── input/
│   ├── acctdata.txt
│   ├── cardxref.txt
│   ├── discgrp.txt
│   └── tcatbal.txt
└── oracle-output/
    ├── acctdata.txt
    ├── transactions.txt
    ├── canonical.json
    └── receipt.json
```

## Run against the upstream CardDemo ASCII fixtures

Clone and pin CardDemo separately:

```powershell
git clone https://github.com/aws-samples/aws-mainframe-modernization-carddemo.git
Set-Location aws-mainframe-modernization-carddemo
git checkout 59cc6c2fd7ebd7ef7925cad552a01a4b8b6e4d5e
Set-Location ..\lightyear-carddemo-oracle
```

Then run:

```powershell
.\oracle.ps1 run `
  --input ..\aws-mainframe-modernization-carddemo\app\data\ASCII `
  --output .\work\carddemo-oracle `
  --processing-date 2022071800 `
  --timestamp 2022-07-18-00.00.00.000000
```

The supplied CardDemo fixture is useful as a broad compatibility check. The synthetic demo adds
targeted coverage for explicit disclosure rates, default-rate fallback, and the final-account edge
case.

## Compare a candidate implementation

Your Java, Python, Go, or agent-generated candidate should write CardDemo-compatible
`acctdata.txt` and `transactions.txt` files. Compare them with:

```powershell
.\oracle.ps1 compare `
  --expected .\work\demo\oracle-output `
  --actual .\work\candidate-output `
  --report .\work\comparison.json
```

The command returns exit code `0` when equivalent and `1` when differences exist. Timestamps are
normalized out of the comparison; financial fields, identifiers, account mutations, and all other
business fields are compared exactly.

## Java/Spring Batch candidate

The candidate is intentionally small and auditable:

1. `InterestCalculationTasklet` owns the file-oriented batch boundary.
2. `CardDemoRecordCodec` parses and renders the upstream fixed-width layouts.
3. `ZonedDecimal` implements COBOL overpunch decoding and encoding.
4. `InterestCalculationService` contains the business transformation without framework coupling.
5. The Python comparator acts as the executable acceptance contract.

Run the JAR directly after `candidate-java\mvnw.cmd package`:

```powershell
java -jar .\candidate-java\target\carddemo-spring-batch-candidate-0.1.0-SNAPSHOT.jar `
  --carddemo.input-dir=.\work\demo\input `
  --carddemo.output-dir=.\work\candidate-output `
  --carddemo.processing-date=2022071800 `
  --carddemo.timestamp=2022-07-18-00.00.00.000000 `
  --carddemo.final-account-policy=source-faithful
```

See `candidate-java/README.md` for the implementation design and standalone commands.

## Important discovered behavior

The source's final account is not rewritten in the normal loop. `CBACT04C` sets end-of-file inside
the final read after its outer `IF` has already been evaluated, so the associated `ELSE` does not
run. The default `source-faithful` mode preserves this source-derived behavior.

To compare with the likely intended behavior instead:

```powershell
.\oracle.ps1 demo --work-dir .\work\intended --final-account-policy intended
```

This difference is exactly why the modernization harness must reproduce observed behavior before
deciding whether a legacy behavior should be preserved or intentionally corrected.

## Next factory increment

Once a candidate can pass the visible cases:

1. Add private holdout fixtures under a separate access boundary.
2. Run mutation tests that deliberately alter the divisor, rounding, default-rate fallback, and
   final-account behavior.
3. Put an implementation agent behind the comparator.
4. Route structured differences back to a repair agent.
5. Issue a LIGHTYEAR decision receipt only after all visible and private scenarios pass.

The pinned workload specification is in `spec/carddemo-intcalc.json`.
