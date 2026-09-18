# Native Oracle 26ai → AlloyDB: 100 bounded datatype pairs

**Result: `passed-bounded-native`.** One authorized run completed 100 Oracle
executions, 100 AlloyDB executions and 100 successful comparisons. All five
families passed 20/20: NUMBER, CHAR, VARCHAR2, DATE and TIMESTAMP. No mismatch,
execution error or blocked case was recorded. Cleanup completed.

Run: `core100-45bae6fc54684445a2b1dd5544c6e537`.
Execution implementation: `c1f1b2c` (full revision in the manifest; exact
implementation and SQL hashes are in the signed authorization).
Observed versions: Oracle 26ai Free `23.26.3.0.0`, `FREEPDB1`; AlloyDB PostgreSQL
`16.13` on the fixed `cloudbank-ms71-alloydb/primary` resource.

The export contains the original signed authorization, 339 verified events and
the signed terminal summary. The 39-event parent journal anchors five 60-event
family journals. The flattened JSON preserves each journal's sequence and hash
chain. The RunStore bound remains 256 per journal.

AlloyDB was restored to **STOPPED / NEVER**. The owned runner VM and IAP firewall
were deleted. `operational-readback.json` separately records the post-cleanup
GCP readback: AlloyDB and Cloud SQL stopped, with no owned VM, firewall or boot
disk. That file is explicitly **unsigned operational evidence**; its manifest
hash protects export integrity, not independent attestation. GKE's existing
control plane remains running, and existing storage/backups still incur costs.

Authorization-to-terminal elapsed time was **1,481.357 seconds (24m 41s)**,
including startup and cleanup. At the approved $2/hour planning rate, rounded up
to cents, this is **$0.83 estimated incremental consumption**, within the
additional $10 estimated allowance. It is not a measured GCP bill or a billing
cap, and excludes ongoing storage/backups. This was one successful attempt.

The prior NUMBER pilot's 20 cases are included in this 100, so aggregate coverage
is **100 unique pairs / 25 bounded behaviours**, not 120. The read-only catalog
overlay verifies signatures, SQL and expectation bindings, family checkpoints
and comparator replay before admitting the result. Each behaviour needs all
four catalog cases to meet the paired probe contract.

This is bounded datatype evidence with explicit target SQL transformations and
reviewed diagnostic mappings. It does not claim every Oracle datatype value or
behaviour, Oracle 19c coverage, CloudBank application equivalence or a new
platform qualification. The separate [CloudBank AlloyDB nonproduction
qualification](../../cloudbank-alloydb-platform-qualification.md) remains intact.
The legacy 4,000-execution wallet gate requires 2,000 cases on each of Oracle
19c and Oracle 26ai; this paired export does not rewrite that gate, and AlloyDB
executions never count as Oracle executions.

The campaign authority is the same operator-controlled Ed25519 key as the prior
pilot, fingerprint
`36fdf4766568b1880c1bddef92f450c6a41279d01ff11c0abd6f78e2215c6552`.
The delegated actor records the user's scope and spending approval; it does not
claim the user personally clicked the UI. No private key, operator credential
or database password is exported. These signatures provide provenance and
integrity within that authority, not independent vendor certification.

Offline verification (no cloud operations):

```powershell
$env:PYTHONPATH = 'src'
py -3.12 -m unittest tests.test_paired_core100_export -v
py -3.12 -m lightyear_data.oracle_paired_coverage --root .
```
