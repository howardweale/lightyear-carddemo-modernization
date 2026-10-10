# Factory 2.2: public three-way reconciliation

This deliverable executes unchanged public INTCALC source with the GnuCOBOL twin,
the existing Python reference model, and the existing Java interest-calculation
service. Inputs come from the same hash-verified public fixtures. No expected
after-image is supplied to any of those executions. No model calls or containers
are used. `Factory three-way reconciliation` on Ubuntu 24.04 compiles and runs all
three, including the missing-disclosure failure, and retains the full report.

The Java harness compiles the actual service, record codec, zoned decimal and
record classes with Java 21; its only framework substitute is an inert `@Service`
annotation declaration. Harness and original source hashes are recorded. This is
not a test of Spring wiring. The Python reference is not promoted to twin truth.

## Comparison policy

Each pair receives a keyed field comparison AND a raw output hash comparison.
Filler, timestamp, numeric-sign representation and record-order differences are
reported, not silently normalized. Duplicate keys refuse comparison. The public
artifact retains all raw output, execution logs and individual differing fields.
A broad shared failure class is not sufficient: the negative case also checks the
source-specific missing-default-disclosure diagnostic. Agreement grants no z/OS
confirmation, release permission or qualification/measurement credit.

`reconciliation.md` and digest-bound `reconciliation.json` are generated from the
actual hosted executions. Disagreements start as **unresolved**, blocking oracle
promotion until source/operand evidence identifies the defective model or adapter.
The runner never edits a fixture or expected result to manufacture agreement.

## Platform probes and scope

The compiled platform probe checks signed packed decimal bytes and DISPLAY signs,
ASCII ordering of `A` / `a`, negative `ROUNDED` versus truncation, narrow numeric
assignment, leap-date intrinsics and the controlled clock. Real indexed operations
check missing file 35, duplicate key 22, missing key 23 and end of file 10. Assertions
pin observed GnuCOBOL behavior under the declared compiler flags; every z/OS match
is **unknown** until tested against an authorised Enterprise COBOL baseline.
No portable-language expectation is relabeled a measured z/OS result.

The public POSTTRAN scenario is executed by the twin, but current Python/Java
implement only INTCALC. Its row is explicitly `not-three-way-supported`, not pass
or agreement. Adding those independent implementations is outstanding. Future
workstream 1 scenarios must be registered with provenance and added to this matrix;
no unbuilt scenarios or coverage/mutant improvement numbers are claimed here.

## Reproduction and acceptance

On the same Ubuntu 24.04 / pinned GnuCOBOL environment as PR 2.1, set `JAVA_HOME`
to Java 21 and `PYTHONPATH=src:.`:

```sh
python -B -m unittest discover -s tests -p test_twin_reconciliation.py -v
python -B -m lightyear_mainframe.twin_reconciliation work/three-way-new
```

Do not reuse an output directory. Hosted execution/table and classification of
all actual disagreements are required before calling 2.2 complete. The exact
commit needs Howard's merge approval; no default oracle or existing evidence gate
is modified by this PR.

## First hosted findings (preserved, not a green acceptance)

Run 38088862638 compiled and executed all five public scenarios before its probe
assertion failed. Its account outputs matched byte-for-byte in all three INTCALC
success cases. Transaction differences affected only original/processing timestamps:
50 records in each original rehearsal and 13 in the discriminating case.
Classification: **twin clock-adapter defect**, not interest-calculation divergence.
The injected clock omitted fractional seconds; observed `.550000` versus requested
`.000000` is bound in the retained output. PR 2.1 now pins the full fractional clock.
No data or comparator ignore rule was changed.

The failing probe confused numeric DISPLAY rendering (`0012345-`) with raw
zoned storage (`001234N`). It now observes and asserts both separately using an
alphanumeric REDEFINES view. Packed signed bytes, rounding/truncation, dates,
collation and all four file-status probes matched the declared GnuCOBOL expectation.
The clock assertion now includes hundredths. These are test/adapter corrections;
no result establishes z/OS equivalence.

## Verified INTCALC milestone — October 10, 2026

[Hosted run 38089428759](https://github.com/howardweale/lightyear-carddemo-modernization/actions/runs/38089428759)
passed on implementation commit `413014469a75bc927d89f105ae72a0f3fb06b4da`:
eight focused no-suppression tests, actual COBOL/Python/Java runs, twelve scalar
platform assertions and exact signed packed-decimal bytes. Report seal:
`64da40dfba1d61c358f64b152644058c75cf6845435804e31872491712d18592`.
The companion result JSON retains source/output hashes and all pairwise comparisons.

| Public scenario | Twin / Python / Java result | Classification |
|---|---|---|
| Original rehearsal 1 | Exact byte agreement for accounts and transactions | No remaining discrepancy |
| Original rehearsal 2 | Exact byte agreement for accounts and transactions | No remaining discrepancy |
| Discriminating | Exact byte agreement for accounts and transactions | No remaining discrepancy |
| Missing default disclosure | All refuse with the matching source-specific diagnostic | Expected execution failure |
| POSTTRAN | Twin only: 262 posted, 38 rejected; RC4 | Missing independent Python/Java implementations |

The first three rows contain **18 exact pair/dataset comparisons**, with zero
remaining discrepancies. They are three fixture runs, not independent production
samples. The initial clock-adapter defect is classified and corrected with its
original mismatch artifact retained. No business-model defect was observed in
these INTCALC scenarios; that is not proof beyond the exercised paths.

Workstream 2.2 is complete for the existing INTCALC implementations and remains
partial for POSTTRAN/future generated scenarios. No new coverage or legacy-mutant
kill-rate result was measured in this milestone. The next behavioral milestone
is twin decision instrumentation and deterministic scenario generation, followed
by registering every new scenario in this same comparison matrix.
All z/OS platform confirmations remain unknown. No default oracle was changed.
Publication changes after the tested commit contain only milestone/result documents.
