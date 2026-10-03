# Monday: Maintec CardDemo folder intake

This runbook is for the October 5 delivery. It operates in a **separate clone**
and never opens a B05 snapshot, runs Docker, calls a model, or submits a z/OS job.
The public rehearsal exercises local Java only. Its after-images were generated
by the local Python reference and are not native z/OS observations.

Maintec's original files and decoded values are hidden answers. Keep them, all
candidate inputs/outputs, logs, observations and approval bundles below
`work/mainframe/arrivals/`. Do not paste any of them into a prompt. CLI summaries
and Tower requests expose hashes, counts, field names and verdicts, never record
values. Arrival directories are ignored by Git; never use `git add -f` on them.

## Prepare once, before delivery

Use the isolated checkout, not the workspace running B05. These are PowerShell
commands; from a different checkout substitute its absolute path in the first line.

```powershell
Set-Location 'C:\Users\howar\OneDrive\Documents\ChatGPT\lightyear-carddemo-modernization\work\carddemo-zos-intake'
$env:PYTHONPATH = 'src;.'
$env:PYTHONUTF8 = '1'
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[control-tower]'
mvn -o -B -f candidate-java/pom.xml package
```

The clone prepared for this task already has its own environment and built JAR.
Offline Maven uses the local dependency cache; a clean machine must first resolve
the POM's dependencies. No candidate Java or judge predicates were changed.

Create an intake signing identity **once**. Do not overwrite an existing key. The
rehearsal key is separate from the live campaign and Control Tower authorities.
Provision a production intake key separately and retain/trust its public key out
of band. Read-only attributes and signatures detect change; they are not WORM
storage or independent attestation.

```powershell
.\.venv\Scripts\python.exe -m lightyear_mainframe init-intake-key work/mainframe/authority/maintec.pem
$IntakeKey = 'work/mainframe/authority/maintec.pem'
$IntakePublicKey = 'work/mainframe/authority/maintec.public.pem'
$Jar = 'candidate-java/target/carddemo-spring-batch-candidate-0.1.0-SNAPSHOT.jar'
```

Use the already-created `rehearsal.pem`/`rehearsal.public.pem` instead when repeating
the public rehearsal. One command runs the complete public chain:

```powershell
.\.venv\Scripts\python.exe -m lightyear_mainframe rehearse-intake --key work/mainframe/authority/rehearsal.pem --jar $Jar
```

Good: three runs, zero intake findings, one **draft** processing-timestamp proposal,
an `equivalent` local Java verdict, offline replay `verified`, and `arrival_ignored:
true`. This says nothing about Maintec's results. Every rehearsal gets a new arrival;
earlier records are preserved. The [bridge exceptions](bridge-fixture-exceptions.md)
explain why the pinned EBCDIC and ASCII public fixtures are not byte-identical.

## Delivery contract

Keep Maintec's supplied folder untouched. A run is named, for example,
`INTCALC-run1-2026-10-05`. Recognized files are:

| Contents | Convention |
| --- | --- |
| Submitted JCL/procedures | `*.jcl`, `*.prc` |
| Complete readable job output | `job-output.txt`, `jes.txt`, `sysout.txt`, or `job.log` |
| Return codes | `return-codes.txt`, `rc.txt`, or `return-codes.json` |
| Dataset images | files below `before/` and `after/` |
| Compiler listing | `compiler.lst` or another `*.lst` |
| Coverage | filename containing `coverage` (retained, not parsed) |
| Notes | `note.txt`, `notes.txt`, or `run-note.txt` |
| Explicit transfer metadata | `run.json`, schema below |

Unknown files are copied and reported. Without metadata, intake still freezes the
delivery and produces gaps; it does not guess which downloaded dataset goes with
which DD. Ask Maintec for the missing metadata or a corrected delivery. Never edit
an existing `original/`. If metadata is added locally, retain the original arrival,
make a new delivery folder with a note attributing the addition, and intake it as a
new arrival. No normalization or alternate HLQ is silently accepted.

Each run's `run.json` describes **every** binary dataset. Example of one entry
(expand for every before/after file; the rehearsal run.json files are complete
examples):

```json
{
  "schema": "zos-delivery-run/1",
  "job": "INTCALC",
  "system_datetime": "2026-10-05T10:00:00Z",
  "processing_date": "2022071800",
  "candidate_timestamp": "2022-07-18-00.00.00.000000",
  "starting_state_id": "operator-supplied-restoration-id",
  "datasets": [
    {
      "file": "before/ACCTFILE.bin",
      "phase": "before",
      "step": "STEP15",
      "dd": "ACCTFILE",
      "dsn": "AWS.M2.CARDDEMO.ACCTDATA.VSAM.KSDS",
      "recfm": "F",
      "lrecl": 300,
      "blksize": 0,
      "codec": "cp037"
    }
  ]
}
```

These date values are examples, not defaults for Monday. Processing date must agree
with Maintec's submitted `PARM` or explicit note. The Java candidate also requires a
timestamp; it must be explicitly supplied by the operator from Maintec's clock
record, **never derived from hidden after-images**. If it is unavailable, the bridge
refuses. A different actual execution timestamp can produce an honest divergent
verdict until an applicable normalization is reviewed.

Notes can state `PROCESSING_DATE=...`, `CANDIDATE_TIMESTAMP=...`, and
`SYSTEM_DATETIME=...` on separate lines. Conflicts with metadata are findings.
The system datetime should include its timezone. No missing JES date, compiler
option, or program name is inferred from these notes.

Use the actual transfer DCB. Missing RECFM/LRECL/BLKSIZE can be derived only from
the submitted JCL's explicit DCB, marked `derived-from-submitted-JCL`. VSAM exports
need their sequential-transfer format stated because the VSAM DD has no such DCB.
Omitted code pages are recorded as **assumed cp037 in every dataset observation**;
cp500 and cp1140 are supported when declared. Unknown pages are refused.

F/FB fixed records and unblocked V records with strict RDWs are supported. For V,
LRECL includes the four-byte RDW and the payload must match the bound layout.
FA/FBA text supports a separate preserved ASA byte; LRECL includes it. HTML remains
fixed-line text, including trailing blanks. VB/VBA/VS/VBS, BDWs and spanned records
are deliberately refused: request an **unblocked binary RDW** export or a fixed
sequential binary export with confirmed DCB. No guessed deblocking or text repair.

The binding table covers application datasets for all four jobs, including the
daily record plus validation trailer in POSTTRAN rejects. Card records are in the
dataset catalogue even though these four jobs do not read CARDFILE directly.
JCL dataset names, programs, steps and explicit DCBs are compared with the pinned
public members. Different HLQs require a separately reviewed binding revision, not
an intake override. TRANREPT's public JCL repeats a step name and uses a procedure;
request expanded submitted JCL/procedure details when it differs. This is bounded
JCL inspection, not a general JCL interpreter.

## Monday commands, in order

### 1. Freeze and inspect gaps

Set `$Delivery` to the received folder. `intake` creates a new arrival every time.
Its stdout is a safe summary; keep the JSON return in a local shell variable.

```powershell
$Delivery = 'C:\Users\howar\Downloads\Maintec-CardDemo'
$Intake = .\.venv\Scripts\python.exe -m lightyear_mainframe intake $Delivery --key $IntakeKey --source-description 'Maintec delivery received 2026-10-05' | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw 'Intake refused; inspect local configuration.' }
$Arrival = Join-Path 'work/mainframe/arrivals' $Intake.arrival_id
Get-Content (Join-Path $Arrival 'gaps.md')
```

Good: `ready-for-review` and zero findings. This is **not acceptance**. The signed
arrival manifest includes every filename, byte count and SHA-256. Each subsequent
command verifies original bytes, the trusted signature and run-index bindings.

Send Maintec the short gap list, for example: missing job output; missing before
image for a named DD; LRECL disagreement; CR/LF/text conversion; wrong job binding;
non-zero RC/abend; or the VB resend instruction. Do not send decoded records.
The tool never emails or uploads anything. A readable gap list is local in the
arrival. If the folder cannot be parsed at all, the CLI reports only a safe refusal,
not an exception containing hidden values.

A new `intake-acceptance` request is placed under
`work/control-tower/requests/carddemo-zos/`. The Console reviewer with
`qualification-approver` decides accepted/rejected. Its bound safe mirror is under
`work/mainframe/review/`; no delivery values are in it. Observation tools can run
before that decision, but they never claim that intake has been accepted.

### 2. Identify runs, decode and read the job log

Intake assigns opaque local IDs `run-001`, `run-002`, etc., in sorted folder order.
Read each local `runs/run-NNN/run.json` to map it to the sender's folder; **do not
assume Maintec sends only the three rehearsal runs**. The following example uses
the two INTCALC runs after that mapping has been checked locally:

```powershell
$Run1 = Join-Path $Arrival 'runs/run-001'
$Run2 = Join-Path $Arrival 'runs/run-002'
.\.venv\Scripts\python.exe -m lightyear_mainframe decode-run $Run1 --public-key $IntakePublicKey
.\.venv\Scripts\python.exe -m lightyear_mainframe observe-run $Run1 --public-key $IntakePublicKey
.\.venv\Scripts\python.exe -m lightyear_mainframe decode-run $Run2 --public-key $IntakePublicKey
```

Good: expected dataset counts, no findings, and declared/assumed code-page labels.
`decoded.json` retains original bytes and exact decoded fields; it stays private.
`observation.json` retains SYSOUT/JES lines, recognized steps/RCs/abends, identity
banners and NUMPROC/TRUNC/ARITH options. Standard IEF142I/IEF450I completions and
explicit `STEP STEP15 PGM=CBACT04C RC=0000` records are recognized. `START_UTC=` and
`END_UTC=` full timestamps are recognized. Unsupported or incomplete JES timestamp
formats remain missing; the original lines are still retained. Return-code JSON is
retained as supplied; use recognized text completions for a parsed step result.

### 3. Compare repeatability and inspect job deltas

```powershell
.\.venv\Scripts\python.exe -m lightyear_mainframe compare-runs $Run1 $Run2 --public-key $IntakePublicKey
.\.venv\Scripts\python.exe -m lightyear_mainframe delta $Run1 --public-key $IntakePublicKey
```

Determinism requires matching before-image hashes and processing parameters;
runtime/compiler fingerprints and missing observations are checked. Comparisons
are keyed by copybook fields; duplicate keys make comparison indeterminate. Print
lines are position-sensitive. Deltas count added, deleted and changed records and
changed fields. Neither output includes record keys or values.

Only a changed, declared processing timestamp matching the exact timestamp pattern
can produce a draft normalization. Any other finding blocks all proposals until
investigated. Every draft includes a named owner placeholder, review date, exact run
hashes and a planted non-timestamp change that remains detectable. No draft is
applied automatically.

### 4. Prepare inputs and run the existing Java INTCALC candidate

```powershell
.\.venv\Scripts\python.exe -m lightyear_mainframe prepare-intcalc-inputs $Run1 --public-key $IntakePublicKey --key $IntakeKey
.\.venv\Scripts\python.exe -m lightyear_mainframe run-intcalc $Run1 --jar $Jar --public-key $IntakePublicKey --key $IntakeKey
.\.venv\Scripts\python.exe -m lightyear_mainframe verdict-intcalc $Run1 --public-key $IntakePublicKey --key $IntakeKey
.\.venv\Scripts\python.exe -m lightyear_mainframe replay-intcalc $Run1 --public-key $IntakePublicKey
```

The bridge takes only bound **before-images**, retaining overpunch and padding and
adding LF record separators. Its signed manifest maps each ASCII input to the
source dataset and copybook hashes. No inferred code-page repair or ASCII padding
is permitted. The candidate is the unchanged source-faithful INTCALC JAR. Execution
is bounded to five minutes, writes logs locally, records JAR/Java/input/output/log
hashes, and refuses to overwrite a prior attempt.

The signed verdict is `equivalent`, `divergent`, or `indeterminate`. It compares every decoded field exactly, including padding and filler, except for an
**explicitly approved**, applicable timestamp rule from verified Tower decisions
or the signed rule register. The old comparison ledger is neither loaded nor applied. Canonical records retain untrimmed text;
normalization happens only in comparison. Diagnostics contain field paths and
counts, never values. A non-zero execution, missing output, invalid key or expired
Tower approval cannot yield equivalence. Do not reinterpret a divergent result.

Offline replay verifies original bytes and signatures, recomputes the comparison,
and requires the same implementation hashes and recorded approval time. It does
not execute Java or contact any service. Retain this exact source checkout/commit
with the archive. An offline approval proof establishes validity at its recorded
journal head, not whether a later decision now exists.

POSTTRAN, CREASTMT and TRANREPT stop after intake/decoding/determinism/delta: no Java
candidate exists for them here.

### 5. Review through the CardDemo Tower v2 workspace

Follow [CardDemo Tower setup and request flow](carddemo-zos-tower.md). This is a
separate `carddemo-zos` authority and journal in the intake clone. Do not reuse a
campaign Console. Intake and comparison write `tower-request/1` files under
`work/control-tower/requests/carddemo-zos/`. A divergent INTCALC verdict also
writes a difference-disposition request. The Workspace tab is a read-only arrival
view; all routes, streams, MCP tools and exports use `carddemo-zos-no-values/1`.

An authenticated `zos-intake` agent proposes the exact timestamp rule through
`propose_rule`; Howard then decides in the Console. The file's proposer label alone
is insufficient. Notes are retained only as hash commitments. Review sensitive
record values in the private local files, never in Console notes.

The `rules` route returns a signed `zos-rule-register/1` with the applicable rules
and their decision proofs. Alternatively use an explicit decision bundle:

```json
{"schema":"zos-approved-rules/1","rules":[{"rule":"exact zos-tower-rule/1 object","proof":"tower-decision-proof/1 object"}]}
```

The quoted descriptions stand for objects. Neither format contains or accepts a
parallel ledger. Obtain the trusted public key and current journal head out of
band. Supply the register or bundle on the **first** verdict invocation:

```powershell
.\.venv\Scripts\python.exe -m lightyear_mainframe verdict-intcalc $Run1 --public-key $IntakePublicKey --key $IntakeKey --normalizations (Join-Path $Arrival 'approved-normalizations.json') --tower-public-key $TowerPublicKey --tower-head $TrustedTowerHead
.\.venv\Scripts\python.exe -m lightyear_mainframe replay-intcalc $Run1 --public-key $IntakePublicKey --tower-public-key $TowerPublicKey
```

Changed rules, stale heads, wrong roles/scopes, expired or superseded decisions,
missing signatures or a field no longer matching the approved pattern are
refused. Existing verdicts remain immutable. Offline replay proves validity at
the archived head and approval time. Operator review is not independent human
attestation. A difference disposition never changes a verdict or approves a rule.

## Before sharing any result

```powershell
git check-ignore -- (Join-Path $Arrival 'manifest.json')
git status --short -- work/mainframe/arrivals
git diff --cached --name-only
```

Good: the arrival path is ignored, its status output is empty, and no arrival data
is staged. Publish only specifically reviewed hashes, counts and verdict summaries.
Never publish original files, decoded records, logs, candidate input/output values,
archives, keys or raw approval evidence that has not been checked for disclosure.

An intake exit code of zero means the tool completed; the JSON `findings` count
and `status` still require review. A tool refusal returns 2. A divergent verdict is
a successful measurement result, not a command crash. No command submits work to
Maintec or changes B04/B05.
