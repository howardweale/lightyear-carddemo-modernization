# Oracle native execution admission matrix

MS #51 converts the completed bounded catalog into a governed two-version native execution
contract. It does not claim that the required SQL harnesses or database runs already exist.

| Domain | Catalog cases | Required 19c + 26ai runs | Native runs admitted |
|---|---:|---:|---:|
| expressions | 240 | 480 | 0 |
| globalization | 180 | 360 | 0 |
| operations | 100 | 200 | 0 |
| plsql | 320 | 640 | 0 |
| queries | 240 | 480 | 0 |
| schema-dml | 200 | 400 | 0 |
| schema-objects | 140 | 280 | 0 |
| structured-data | 140 | 280 | 0 |
| transactions | 180 | 360 | 0 |
| types | 260 | 520 | 0 |
| **Total** | **2000** | **4000** | **0** |

The index defines 20 version/domain batches. Every admitted native result must
bind the exact case expectation, SQL harness hash, database identity, session settings, diagnostics,
timestamps, runner identity, and an environment-key signature. The earlier eight-fixture SQL file
has completion markers but no per-case native observations, so it remains ineligible as catalog
native evidence.

Native SQL harness materialization, authorized 19c and 26ai execution, target equivalence,
iDempiere application equivalence, CloudBank mapping, migration completion, and production
readiness remain blocked.
