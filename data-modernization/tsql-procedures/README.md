# T-SQL procedure verification — M0

**Public trap-corpus qualification passed; customer admission remains gated.**
The [PR269 review results](review-results.md) record 108 fresh native comparisons,
43 procedures / 26 trap families, independent offline replay and actual owned
resource cleanup. All 43 wrong-twin variants were rejected; 41 correct variants
met aggregate coverage/equivalence gates and two require policy decisions.
Operator review, not independent attestation. Zero model calls.

This is a public-fixture implementation milestone, not customer certification.
Earlier [unmeasured results](native-results.md), [coverage results](coverage-results.md)
and failed attempts remain preserved. No B06 or Windows containers were used.

## Current contracts

| Area | Implemented behavior | Boundary |
| --- | --- | --- |
| Invocation | ScriptDom-bound procedure schema/name; typed named TDS RPC arguments; parameterized PG calls; every declared case receives a fresh reset | Calling-convention map required; customer profiles not qualified |
| Results | Source AST ORDER BY preserves row order; otherwise duplicate-preserving multisets; result sets retain order | Conservative procedure-wide order flag may unnecessarily reject unordered sets in mixed-result procedures |
| Policy | AST UPDATE FROM, unordered TOP and nondeterministic function obligations; observed differences remain divergent | Corpus labels cannot admit a business choice; real clocks, no implicit clock freezing |
| Types/errors | Versioned numeric/decimal/money, date/time, binary, identifier and text contracts; explicit SQL error/SQLSTATE map | Unknowns unsupported; ambiguous 547 and user errors require explicit contracts; expanded maps are offline-tested |
| Profile | SQL Server collation and compatibility pinned and read back | Tested: Latin1_General_100_CI_AS / 160 |
| Capture | All user-table effects, raw metadata, OUT/RETURN, errors/messages, transaction exit, identity and SQL SEQUENCE metadata | Standalone sequence mapping, nested PG counts and complete transaction-event streams remain gated |
| Inventory | Missing twin refused per pair; unpaired-file hashes retained; parser-derived cross-database references | Partial dependency catalogue; full native transitive closure remains incomplete |
| Coverage | Qualified revision 1 unchanged; revision 2 passed nine native controls and six consuming pairs, including PG schemas and view exclusion | [Exact v2 scope and hashes](coverage-v2-results.md); cannot reuse revision 1 controls or infer universal coverage |
| Cases | Boundary/branch-value/trace proposals and bounded same-failure shrinking | Proposals need fresh execution; no global minimum or automatic path-solving claim |
| Tower | Registered procedure-equivalence-policy kind and signature verification bound to inventory/procedure/policy/evidence | No decision issued; comparator does not clear obligations from unverified proposals |

Historical public mapping profiles remain available. Comparison revision 5
explicitly supersedes legacy row-multiset/error/type assumptions through its
`syntax_contract` and `representation_policy`. Replay recomputes those fields.
Unmapped PG return behavior is unsupported, never silently assumed zero.

## Offline validation

```powershell
$env:PYTHONPATH = 'src;.;tests'
python -B -m unittest discover -s tests -p 'test_tsql*.py'
```

Native evidence used .NET 8 ScriptDom, SQL Server 2022 Developer, PostgreSQL
16.15/plpgsql_check, python-tds 1.16.1, psycopg 3.2.10 and cryptography 46.0.3.
Image digests and source/bridge hashes are bound in its signed plan.

## Approved VM execution only

This starts containers and requires explicit environment approval. Supply local
placeholder values; use a fresh output on every attempt. No generic Docker
cleanup or shared databases. Reset uses SQL CHECKSUM backup restore and PG clones.

```sh
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 python -B tools/run_tsql_native.py \
  --root . --expected-host APPROVED_VM_HOST \
  --output /private/evidence/NEW_ATTEMPT \
  --semantic-bridge /trusted/semantic/TsqlInventory.dll \
  --coverage-bridge /trusted/qualified-coverage/TsqlInventory.dll \
  --pg-image PINNED_QUALIFIED_IMAGE \
  --coverage-controls-evidence /private/evidence/COVERAGE_CONTROLS \
  --coverage-controls-report-sha256 EXPECTED_CONTROL_REPORT \
  --coverage-controls-key-sha256 EXPECTED_CONTROL_PUBLIC_KEY
```

For qualified collector-v2 comparisons, add `--coverage-revision 2`, repeat
`--coverage-schema dbo --coverage-schema business`, and supply the exact v2
control evidence/report/key from [the qualification](coverage-v2-results.json).
Revision 1 evidence is rejected. New schema scopes require fresh qualification.
All schemas are plan-bound. This runner is not a confidential customer deployment or
permission to transfer customer code.

## Independent replay

Copy only the evidence directory, never its private sibling. Obtain report and
recorder public-key hashes through the trusted handoff:

```sh
PYTHONPATH=src python -B tools/replay_tsql_native.py /path/to/evidence \
  --report-sha256 EXPECTED_REPORT_CONTENT_HASH \
  --key-sha256 EXPECTED_PUBLIC_KEY_HASH \
  --output /new/path/outside-evidence/audit.json
```

Replay makes no database/Docker calls. Actual owned-resource absence is a separate
read-only check. Raw captures, keys, logs and VM identifiers remain local.
Recorder signatures are not Tower decisions or independent attestation.
Customer dependency closure, security context, policy/certificate release,
concurrency and performance equivalence remain unassessed. The new results
include measured reset timing and throughput, not a production benchmark.
