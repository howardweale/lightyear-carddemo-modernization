# T-SQL procedure verification — M0

**Native comparison and offline replay completed; M0 qualification has not passed.**

See [the measured coverage results](coverage-results.md),
[coverage and mapping contract](coverage-and-mappings.md), and
[the original October 7 results](native-results.md). Operator review, not
independent attestation. Zero model calls. All native execution used Howard's
approved dedicated Google Cloud VM; none used local Windows Docker.

## Current implementation

| Component | Implemented and checked | Remaining qualification boundary |
|---|---|---|
| Intake | Explicit pairing, source hashes, missing/reused/unpaired-file refusal, UTF-8 checks, private inventory and hash-only summary | Customer inventory not received |
| Parser | ScriptDom SQL Server 160 .NET bridge; all 42 authored source procedures parsed on Ubuntu x86_64 | Syntax is not behavioral equivalence |
| Inventory | Parameters, OUT values, result hints, dependencies, transactions, dynamic SQL, nondeterminism and unsupported features | Catalog/type/dependency closure needs qualification |
| Native adapters | SQL Server 2022 Developer and PostgreSQL 16.15; actual TDS RPC and PostgreSQL calls | Public corpus calling conventions only; customer profiles not admitted |
| Reset | CHECKSUM-verified SQL Server golden backup restored into fresh databases; PostgreSQL fresh template clones | Reset-only benchmark still needed |
| Capture | All ordinary user tables and trigger targets, raw types, rows, PKs, identity/sequence values, result sets, OUT/RETURN, errors, messages, TDS tokens, exit transaction state, visible temp objects | Full nested PG row-count and internal transaction-event streams remain incomplete |
| Replay | Ed25519 signatures, exact closure, source/setup/image/plan bindings, recomputed table deltas and comparisons | Recorder evidence is operator review, not independent attestation |
| Ledger | 107 ASE entries retained as review obligations, plus 25 SQL Server trap families | Borrowed behaviors and policy mappings are not automatically admitted |
| Corpus | 42 authored procedures and correct/wrong twin hypotheses, 252 hash-bound SQL assets; three return-contract twins corrected prospectively | All original outcomes preserved; matching observations alone do not establish equivalence |
| Coverage | Native SQL Server XE / ScriptDom and PostgreSQL plpgsql_check collectors; seven native controls on both engines; offline replay | Procedural scope only; conservative PostgreSQL handler proof; uncovered paths remain gated |
| Mappings | Explicit asset-bound public profiles for all 42 procedures and 25 families | Customer policies and Tower certificate release remain unapproved |

The original unmeasured run and subsequent measured runs are separate evidence.
The latest report records all outcomes, native coverage gates, independent replay
and actual owned-resource cleanup. Earlier failed development attempts remain
preserved. No result is replaced by a later run.

## Code and tests

- `src/lightyear_data/tsql_procedures/native.py`: GO-aware SQL Server batches,
  concrete native engine backend, backup/template resets, calls and captures.
- `adapters.py`: explicit VM connector boundary; profile-only adapters refuse
  execution. Missing measured coverage remains `None` and fails closed.
- `coverage.py` / `coverage_qualification.py`: native evidence reduction, gates
  and replay of the bound collector controls.
- `policy.py`: explicit public-fixture mappings and compatibility classification.
- `capture.py`: read-only DB-API captures and same-engine table deltas.
- `native_evidence.py`: native comparison, run-local recorder signatures and
  database-free pair replay. The original conservative `replay.py` format remains
  supported separately; it does not promote old mock evidence to native proof.
- `tools/run_tsql_native.py`: approved Linux host guard, hash verification before
  execution, digest-pinned images, fresh owner labels, private credentials outside
  evidence, capture preservation, signed reports and exact owned cleanup.
- `tools/replay_tsql_native.py`: independent terminal-file and pair verification.
- `tools/tsql_scriptdom/`: trusted .NET parser bridge.

Run the offline suite from the repository root:

```powershell
$env:PYTHONPATH = 'src'
python -B -m unittest discover -s tests -p 'test_tsql*.py'
```

The latest increment passed **73 scoped offline tests**. The original VM bundle
passed its eight native-boundary tests before execution. Live transport smoke covered
multiple results, OUT parameters and return status, with correct and wrong twins.

## Native runner use

This command starts Docker. It belongs **only on the explicitly approved
x86_64 Linux VM**, never the B06 Windows machine. Use a new output directory on
**every** attempt. Preserve failed directories. Do not use generic Docker cleanup.

The VM used `python-tds==1.16.1`, `psycopg[binary]==3.2.10` and
`cryptography==46.0.3`. The runner contains the exact tested image digests. It
refuses an unexpected host, a mismatched source byte or an existing output path.

```sh
export PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1
~/tsql-native-venv/bin/python -B tools/run_tsql_native.py \
  --root . \
  --expected-host ly-tsql-m0.us-central1-a.c.lightyear-ms67-nonproduction.internal \
  --output /home/howard_weale_gmail_com/tsql-native-NEW-ATTEMPT
```

That minimal command produces unqualified coverage and cannot issue an equivalent
verdict. Measured runs additionally require `--coverage-bridge`, `--pg-image`,
`--coverage-controls-evidence`, `--coverage-controls-report-sha256` and
`--coverage-controls-key-sha256`, bound to the seven-control qualification.
The exact successful plan is retained with the evidence; never reuse an output.

Add `--ids integer-division output-parameter multiple-result-sets` for the six
transport comparisons. Public fixtures only: this runner is not a confidential
customer deployment or an approval to transfer customer code.

Databases are reached through an internal Docker bridge from the VM host. No
database ports are published. SQL Server's refcursor counterpart uses the
explicitly declared PostgreSQL BEGIN/CALL/FETCH/FETCH/COMMIT transaction; no
outer rollback is used to reset cases.

## Independent replay

Copy only the evidence directory, never its `-private` sibling. Obtain the report
content hash and recorder public-key hash through the trusted run handoff, then:

```sh
PYTHONPATH=src python -B tools/replay_tsql_native.py /path/to/evidence \
  --report-sha256 EXPECTED_REPORT_CONTENT_HASH \
  --key-sha256 EXPECTED_PUBLIC_KEY_HASH \
  --output /new/path/outside-evidence/audit.json
```

Replay does not import database drivers or invoke subprocesses/Docker. It verifies
signatures and exact file closure, recomputes deltas and comparisons, and checks
source/setup/image/plan/progress bindings. Its cleanup result verifies the signed
receipt; actual Docker absence is a separate read-only host inventory check.

## Policy and acceptance

Trap 25 (unordered TOP) and trap 18 (ambiguous UPDATE FROM) stay policy-gated even
when repeated observations coincide. Public-fixture error/notice, identity/sequence
and schema/type rules are explicit in the [mapping register](public-policy-register.json).
Customer use requires separately admitted rules. The native comparison
preserves values; it does not trim, numerically parse strings or ignore return
status to make a reference pass.

Matching outputs remain `insufficient-evidence` when coverage is missing or fails
its gates. The three return-status discrepancies have been corrected and tested
with fresh native evidence. No release certificate or complete M0 success
has been issued. Concurrency, security context and performance equivalence remain
not assessed. The whole-run duration is not a reset-only benchmark.

Tower policy/certificate integration is pending. The proposed policy kind is
`procedure-equivalence-policy`, scoped to a rule and affected inventory. No Tower
authority, approval or release decision was created during this native run.
Run-local evidence keys are recorder keys only.

See [VM setup](linux-vm-setup.md) and [the earlier preparation report](vm-preparation-report.md)
for historical preparation. Their pre-native status is superseded by the native
results and [measured coverage increment](coverage-results.md). Raw captures, native logs, credentials and
keys remain outside repository documentation. Public reports contain counts,
classifications and hashes. No publication or PR was performed in this increment.
