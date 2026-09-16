# Runtime verifier qualification kit

This kit tests a new, bounded account-transfer observation comparator against real
local processes with different implementations and deliberately faulty variants.
It is the work we can complete before receiving partner code or runtime access.

It reuses the CloudBank MS66 business-scenario concepts (transfer, rejection,
concurrency, restart), and existing content-sealing/I/O utilities. It does **not**
run the CloudBank applications, extend their signed receipts, or prove that the
existing CloudBank or CardDemo gates detect these faults. Connecting a production
gate to this same challenge interface is a separate integration task.

## Run the public campaign

Requires Python 3.11+ with its standard library; no cloud, model, Java, Docker,
network or partner credentials are needed. From the repository root:

```bash
PYTHONPATH=src python3 -m lightyear_qualification run --output work/verifier-qualification/run-001
PYTHONPATH=src python3 -m unittest tests.test_verifier_qualification -v
```

PowerShell:

```powershell
$env:PYTHONPATH = "src"
python -m lightyear_qualification run --output work/verifier-qualification/run-001
python -m unittest tests.test_verifier_qualification -v
```

Use a new output path for each run. The command refuses to overwrite evidence.
Exit codes: 0 = declared development expectations met, 1 = detected mismatch or
failed qualification, 2 = invalid input/incomplete evaluation. A development
campaign **passes because all intentional faulty targets fail comparison**.

The output directory contains a readable `report.md`, the complete `report.json`,
the exact `public-cases.json`, and `freeze.json`. The report retains raw requests,
stdout/stderr, exit codes, direct fault witnesses, normalized differences, and
observations collected by a new process after an injected crash. Content hashes
bind the code, contract and development corpus. They are not signatures or proof
that an external observer is honest. No customer data belongs in this public kit.

## Executable scope

See [contract.json](contract.json) for the explicit money, ownership, calendar,
idempotency, atomicity and observation rules. Sixteen hand-authored scenarios
contain exact expected account and transaction state after each step. Neither
implementation generates the expected answers.

| Program | Arithmetic | State/transaction implementation | Wire format |
|---|---|---|---|
| `sqlite_target.py` | Integer cents; integer ties-to-even conversion | SQLite `BEGIN IMMEDIATE` | Integer cents, identity-sorted collections |
| `journal_target.py` | Decimal with explicit half-even quantization | Replayed event journal; atomic file replacement | Decimal strings, different ordering |

Each request launches a new process. Concurrent requests use multiple workers
inside one process. SQLite serializes transactions; the journal uses a process
lock. The crash hook kills the process before commit, then the harness launches a
new observer and retries. These tests cover process interruption and persisted
state across process restarts, **not** host power failure or distributed races.

The SQL program has eight explicit, executable fault modes: wrong recipient,
incorrect rounding, duplicate application, partial commit, lost replay registry,
wrong business date, bypassed ownership, and stale concurrent update. A separate
raw-state assertion confirms each fault actually manifested. It does not call
the comparator or normalizer. A correct amount that does not trigger the rounding
fault is run as a no-trigger control and excluded from detection counts.

| Fault outcome | Meaning |
|---|---|
| `detected` | Raw fault witness confirmed; comparator found a business mismatch |
| `blocked-indeterminate` | Fault confirmed; comparison could not decide |
| `missed` | Fault confirmed; comparator passed the faulty behavior |
| `not-exercised` | No confirming witness, including target/setup failures |

Decision rate is reported separately from detection. Coverage retains every case
and required step, including those blocked during initialization. It is coverage
of the **declared corpus**, not a code-path, estate-wide or customer-workload metric.
The development criterion requires every correct example to pass, every one of
the eight seeded faults to be witnessed and detected, and all normalization and
admission challenges to pass. This threshold is not a statistical generalization.

## Adapter interface and conformance

The evaluator invokes an argv list directly (no shell), appending a fresh per-case
state directory. It writes one JSON request on stdin:

```json
{"protocol":"transfer-request-v1","command":{"kind":"observe"}}
```

Commands and exact public examples are in `public-cases.json`. An adapter supports
`initialize`, `transfer`, `observe`, and `concurrent`; initialization is fresh for
each scenario. It returns one JSON object on stdout with exactly `encoding`,
`accounts`, `operations`, and `outcomes`. The two sample programs demonstrate both
supported encodings. Exit 75 is reserved for the explicit crash-injection hook;
any other unexpected process failure, malformed output, or 15-second timeout
leaves the evaluation indeterminate. Per-command captured stdout is limited to
one megabyte for admission. Do not write logs to stdout.

Complete account identity and command outcome sets are required. Unknown formats,
duplicate identities/JSON keys, missing fields, extra fields, non-finite numbers,
boolean cents, sub-cent observations and unsupported identifiers cannot pass.
The only normalizations are exact decimal representation and identity-keyed
collection order. IDs, owners, business dates and amounts remain significant.
The protocol has no field for an adapter-authored verdict.

Adapters run **as trusted local programs, not in a security sandbox**. The harness
does not pass API/cloud credential environment variables, but a local executable
still has the operating-system user's filesystem access. This mode is intended
for synthetic, reviewed fixtures. A partner integration needs an approved runtime
boundary and independently collected observations. An adapter fabricating complete
but false observations cannot be exposed by JSON validation alone.

## Freeze before external review

```bash
PYTHONPATH=src python3 -m lightyear_qualification freeze --output work/qualification-freeze.json
```

Give the reviewer the [review protocol](review-protocol.md). They prepare new cases
without modifying the frozen verifier or inspecting/tuning against its outcomes.
The external case file has the same explicit structure as `public-cases.json`.
Do not call the committed public examples a hidden set. Both sample programs and
their tests were authored in the same development session: structurally different
implementations are not independent authorship or independent validation.

An adapter descriptor binds its directly invoked artifact:

```json
{
  "id": "reviewed-adapter",
  "argv": ["/absolute/path/to/python", "/absolute/path/to/adapter.py"],
  "artifact": "/absolute/path/to/adapter.py",
  "artifact_sha256": "REPLACE_WITH_FILE_SHA256"
}
```

Use absolute paths because execution occurs in a temporary state directory.
For this single-file fixture interface the bound file must appear in argv.
Transitive libraries, remote systems and container identities require additional
partner evidence; the single-file hash does not authenticate that broader runtime.

```bash
PYTHONPATH=src python3 -m lightyear_qualification evaluate \
  --adapter /absolute/path/to/adapter.json \
  --cases /absolute/path/to/reviewer-cases.json \
  --freeze work/qualification-freeze.json \
  --output work/reviewer-evaluation.json
```

Changes to frozen source, policy or public corpus stop evaluation. External
results retain adapter, corpus and freeze identities. They explicitly leave
review independence unattested and partner qualification false. An all-pass result
for ordinary examples does not establish fault-detection quality. Reviewer faults
need independently confirmed execution witnesses and the four-way accounting
above before anyone claims blind qualification.

## Partner arrival

Use the [partner intake pack](partner-intake.md) to bind source behavior, build and
runtime identities, observation access and required business scope. Extend only
reviewed adapters and contracts, then repeat the frozen challenge process. Do not
broaden normalizations to raise the decision rate. Report every unresolved critical
behavior rather than hiding it behind aggregate coverage.
