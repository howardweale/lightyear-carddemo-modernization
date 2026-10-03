# CardDemo z/OS intake readiness

Prepared October 2, 2026 (Pacific), with final rehearsal completed October 3 UTC,
for Maintec's October 5 delivery. Implementation branch: `codex/carddemo-zos-intake`.
The [Monday runbook](monday-runbook.md) contains the exact operator commands.

## Delivered capability

- Signed, read-only original arrival copy; complete file inventory, explicit transfer
  metadata, binary-transfer checks, plain-word gaps and an intake acceptance request.
- Pinned public bindings for INTCALC, POSTTRAN, CREASTMT and TRANREPT; strict existing
  copybook decoding, both parts of POSTTRAN rejects, EBCDIC text/ASA preservation,
  and explicit rejection/resend instructions for blocked or spanned variable records.
- JES/step/abend observations and compiler-option fingerprints; keyed determinism and
  before/after deltas without record values in command output.
- Draft timestamp proposals with a still-caught mutation, requiring an exact signed
  Control Tower normalization decision. Non-timestamp differences, added/deleted
  records, missing observations and changed starting data block proposals.
- Before-image bridge to the unchanged Java INTCALC candidate, explicit date inputs,
  signed execution and three-way verdict, and offline replay without executing Java.

All delivery values, original bytes, decoded records and candidate artifacts remain
in ignored `work/mainframe/arrivals/`. Safe Tower requests contain hashes and counts.
No delivery is sent to a model or external service. Intake acceptance remains an
operator decision; signatures do not constitute independent attestation.

## Validation performed

| Check | Result |
| --- | --- |
| New intake, corruption, custody, bridge and approval regressions | 45 passed |
| Existing mainframe tests, including all 501 pinned public binary records | 63 passed |
| Existing decision-service tests | 18 passed |
| Existing Decision Console tests | 11 passed; optional agent-SDK surface test skipped |
| Unchanged Java candidate Maven package/unit tests | 11 passed |
| Final complete public synthetic rehearsal | Passed; 3 runs, 50 files, zero intake findings |
| Determinism | Zero findings; one unapplied timestamp proposal |
| Java comparison and independent offline recomputation | Equivalent; replay verified |
| Arrival ignore check and whitespace check | Passed; no arrival files staged |

The optional Console MCP surface test was skipped because this isolated environment
has the Control Tower dependencies, not the agent SDK. The added CI workflow defines
Windows and Linux public-only rehearsals; remote CI has not been run for this branch.

The seven requested broken deliveries are covered: text conversion, missing job
output, truncated record, unknown file, JCL binding disagreement, non-zero return
code and unsupported VB framing. Additional tests cover tampering, wrong keys,
invalid metadata, duplicate bindings and stale or unapproved normalization.

## Final local rehearsal evidence

Arrival: `arrival-20261003T020025Z-ba6e6c8e6973`.
The signed records remain below `work/mainframe/arrivals/`; the following are signed
content hashes, not claims of public publication.

| Record | SHA-256 |
| --- | --- |
| Rehearsal report | `3ff536a5a8283c32da1eca322596c73b0e27c03d6de6a3b8b15e75e1071baf49` |
| Arrival manifest | `3608b4ca6d8046f1c587add58101baa675e8ccdb0b34ebf13b50e9a18b3de434` |
| Intake | `27b992242229ed6a474b5e91b7ce567c52b76c71f05bc8fd2805aa7fe72cacb8` |
| Java execution | `dd6710b1fa715dc3c73824d4ed50da6d55931c5964fc071e070004aa68253d6e` |
| Equivalent verdict, reproduced offline | `2528b8b239d9bca24f85201ec4e905fb99d5a2b5e20fac1d68d8114049c24272` |

The separate decode, observe, compare-runs, delta and replay commands were also
checked against this arrival. Earlier development rehearsals remain local and
unchanged; the final hashes above identify the corrected implementation's result.

## Scope and Monday requirements

This is public-fixture readiness, **not a native z/OS qualification**. The rehearsal's
after-images came from the local Python reference, with an explicitly planted
timestamp difference. The bridge reproduces the public input pairs subject to the
[documented source-pair exceptions](bridge-fixture-exceptions.md); it preserves the
EBCDIC source and never applies those exceptions to Maintec records.

Maintec must supply binary before/after images, readable submitted JCL and job output,
transfer DCB/code page metadata, and the actual clock/date parameters. Missing or
ambiguous inputs produce findings or refusal. Alternate HLQs need reviewed bindings;
the JCL reader is bounded, not a general interpreter. Unsupported log fields remain
missing. VB/BDW and spanned records require a resend in a supported framing.

Work was performed in a fresh clone with its own virtual environment. There were
zero model calls, zero Docker calls and zero native z/OS executions. B05, `work/ms94`
and all execution snapshots were untouched. Nothing has been published by this task.
