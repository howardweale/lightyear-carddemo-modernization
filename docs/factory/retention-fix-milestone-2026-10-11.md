# PR322 retention correction — 2026-10-11

Run 38190468540 remains failed at head `a091471d69bdf61c1f72b1d22fe3bc870ace1ece`. New campaigns start empty at the new published head; no old campaign is resumed. The 8 GiB guard and 180-minute job limit are unchanged.

## Measured diagnosis and projection

Preserved artifact inventories and streaming SHA-256/gzip-level-1 measurements:

| Program | Fresh bytes | Targeted bytes | Fresh seconds | Targeted seconds | Fresh runs | Fresh bytes/run | Targeted runs | Targeted bytes/run |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| INTCALC | 730,762,199 | 489,913,166 | 1,313 | 2,397 | 6,465 | 44,677 | 6,856 | 56,868 |
| POSTTRAN | 37,184,546,575 | 225,932 | 1,945 | 5 (guard only) | 5,915 | 6,199,214 | 0 | unavailable |

Bytes/run above use run-folder bytes, excluding build/summary/TCE overhead. POSTTRAN stopped before its first targeted case because the old targeted guard included the fresh campaign. Its largest refused run folder was 1,597,610,994 bytes. Deduplicating and gzip-compressing **all** archived fresh files measured 107,400,693 bytes for INTCALC and 526,126,136 for POSTTRAN; selective retention keeps fewer case files. Non-run build bytes remain separate.

The [machine-readable projection](retention-projection-2026-10-11.json) records measured sources, formulas and assumptions. It reserves raw build bytes plus all compressed archived bytes and receipt allowance; target peak allows two simultaneous largest observed POSTTRAN run folders plus 256 MiB of retained data/metadata. This is an empirical projection, not a guarantee about unseen data.

| Program | Fixed shards | Projected job minutes | 180-minute headroom | Fresh peak / 8 GiB headroom | Targeted peak / 8 GiB headroom | Required free disk before compile |
|---|---:|---:|---:|---:|---:|---:|
| INTCALC | 2 | 87.3 | 2.06x | 0.64 GiB / 12.56x | 3.23 GiB / 2.48x | 8,294,404,510 bytes |
| POSTTRAN | 4 | 62.0 | 2.90x | 2.96 GiB / 2.71x | 3.23 GiB / 2.48x | 9,280,391,428 bytes |

Actual free disk is measured by each runner **before compilation** and recorded in `retention-preflight.json`. A runner below twice the projected combined peak refuses to start. Timing uses INTCALC's completed targeted run rate with a 1.5x execution factor, 1.25x observed fresh duration and 240 seconds overhead. Each shard freshly compiles the same exact head and processes a fixed slice of sorted mutant IDs. INTCALC is also split to preserve twofold wall margin after removing baseline byte caches.

## Retention and completeness

Every case runs in a fresh temporary directory. RC (null if unavailable), exact file SHA-256s, normalized comparison hashes, execution time and byte count remain in receipts. Ordinary no-kill case directories are removed. Full target bytes are retained only for the first killing witness, every refusal, and samples 0 and 199, for both sides of the comparison. Files are SHA-256 addressed and gzip-compressed once per store. Fresh compiled comparisons use the same store for refusal/witness preservation, while baseline after-images and actual build artifacts remain bound by the compiled campaign manifest.

Fresh and targeted budgets are checked separately. Each phase records actual stored bytes, logical bytes/run, temporary peak, compressed retained bytes and elapsed time. No output budget is raised. All shards seal their inventories; aggregation verifies the exact head, unique full partition, all 200 indices per targeted mutant, classifier results, sample/refusal/witness policy, retained blob hashes and cross-shard fresh results before producing any threshold assessment. Missing comparisons remain evidence gaps; compiler or class arguments do not erase them.

## Corrected claims

The additive correction in [PR318's milestone](review311-317-milestone.md) and [summary JSON](systematic-review311-summary.json) supersedes nine miscredited POSTTRAN kills without altering raw records. The completed fresh phase of failed run 38190468540 confirms 360/483 POSTTRAN kills and 308/421 INTCALC kills. INTCALC shared the classifier but lost no formerly claimed kill; its evidence gaps remain visible. Final new-head twin and z/OS-facing assessments, proof categories, refutations and evidence-gap counts must come from the complete aggregate, not these old-head measurements.

No native B06 execution, model calls, Phase 2 approval, threshold activation or release authorization follows from this engineering CI change. Howard's commit-specific merge approval remains required for the new code head after green CI.

Offline validation: 30 focused tests across retention, campaign provenance, equivalence decisions and CI selection passed (16 equivalence tests plus 14 retention/provenance/CI tests). Source syntax and whitespace checks run before publication. New-head compiled measurements remain pending CI.

The initial retention head `86d20034de09a644d0ff02d1951130eabf01a879` correctly failed historical-packet hash reproduction after the additive summary correction. The exact pre-correction summary is now archived byte-for-byte, with an explicit pinned hash and body-equality check; the historical sample remains unchanged. The subsequent head runs fresh CI; neither head is resumed into another.
