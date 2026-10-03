# MS94 B05 results and terminal audit

B05 completed with **19 final passes out of 20 cohort trials (95%)**, Wilson 95%
interval **76.4%–99.1%**. Three pilots are excluded. This supports the repair loop
on this one order-to-cash journey under the frozen B05 conditions. It does not
establish performance on other journeys, pool with B03, or authorize MS95.
B04 remains void. Operator review; not independent human attestation.

## Terminal audit

The new campaign-level audit **passed** on October 3, 2026. It independently
replayed all **31** signed publications from their local archives, recomputed all
**23** trial summaries and the report figures, and verified the plan, amendment,
executable, preflight, authorization and cohort-18 review chain. Every replay
verified full entry, complete gate, diagnostics, calendar, provenance, delivery
and operator review.

All **279** owned resources—217 containers, 31 networks and 31 volumes—were absent
both before and after replay. The entire `ly-ms93-compile-` container family was
also absent. Original compiler receipts omit random container names, so this is
a family-wide absence check, not a fabricated per-call identity inventory.
All **1,085 frozen files** and **1,879 protected files overall** were unchanged.
The audit verified 309 local signed records in addition to archive-internal checks.

[Signed terminal audit](terminal-audit.json):
`2949735a380202d34dd672cd7b2439e9cb9b20ecf7fa198f18e07cfd5e7cecc6`.

Original report: `d09fd6c309de9452cdd53723ff381a3d2dc02be15a38d6d8f4b2f924141a73de`.
Executable snapshot: `8cb754f83165b64ffb8e36a311fe633724e9b889b4e047299f66a9e6ce9a9ada`.

The audit used the unchanged frozen `tools.ms94_b05_publication` implementation.
The new local auditor's source hash is `dc9cf6d3df2f8207734170c0c6c9a8deacaa6c41a669fa6f878f9cbacb9dca78`.
No model calls, compilations or native executions occurred during the audit.
It did not alter, rerun or resume B05. Raw archives, captures, checkpoints and
keys remain local and are excluded from this results directory.

## Effectiveness and the remaining failure

| Cohort metric | Result |
|---|---:|
| First-try passes | 12/20 (60%; Wilson 95% 38.7%–78.1%) |
| Final passes | 19/20 (95%; Wilson 95% 76.4%–99.1%) |
| Eligible repairs converted to passes | 7/7 |
| Execution-failure attempts | 8 |
| Closed diagnostics exported / delivered to builder | 7 / 7 |
| Diagnostic delivery coverage | 7/8 (87.5%) |
| Exported but unsent diagnostics | 0 |
| Post-repair business failures | 0 |

Repair eligibility requires an execution failure with nonempty closed feedback
actually delivered to a subsequent builder invocation. It is not all failures.

Cohort 18 halted equipment-suspect after the support posting helper threw. The
recorded operator decision classified the candidate's posting sequence as B03
Category C misuse, continued to the next fresh slot, and left the failed verdict
unchanged. That trial received no repair diagnostic and remains the cohort's one
non-pass. This is operator review, not an independent human adjudication. Its
support-origin delivery limitation is preserved for B06 work, not retroactively fixed.

## Cost and time

Costs include the three excluded pilots; effectiveness rates do not.

| Resource | Recorded total |
|---|---:|
| Model / builder calls | 31 / 31 |
| Analyst calls | 0 |
| Compilations | 31 |
| Input tokens | 10,267,379 |
| Cached input tokens (subset of input) | 9,003,264 |
| Uncached input tokens | 1,264,115 |
| Output tokens | 378,476 |
| Agent time | 16,558.450 s |
| Native time | 12,294.577 s |
| Completed trials including finalization | 33,524.487 s |
| Operator waiting time | 34,573.219 s |
| Original campaign elapsed time | 68,147.172 s (18.93 h) |
| New independent terminal audit | 2838.547 s (47.31 min) |

Timing categories overlap and must not be added as if disjoint. Historical
monotonic durations are signed observations; replay checks their bindings and
sums rather than remeasuring past wall time. Original preparation time is not
recomputed by this audit and is not counted as zero. No dollar charge is
inferred from token counts; no invoice was inspected.

The original campaign stayed within 115 calls, 69 compilations and 26 hours;
each trial stayed within its signed finalization-inclusive deadline and its
5-call/3-compilation caps. The separate terminal audit creates no new candidate
outcomes and does not contribute to effectiveness rates.

## Review and publication status

The signed terminal audit and these results are published on `main` through
[PR #234](https://github.com/howardweale/lightyear-carddemo-modernization/pull/234),
merge commit `d4a97d04ee84f63b556ec905297863d2ba60585b`.
The preregistration and first executable/preflight evidence are also on `main`
through [PR #236](https://github.com/howardweale/lightyear-carddemo-modernization/pull/236),
merge commit `18a748d81b0c11953cffc91142d77743b0b15593`.
The r2 amendment, executable and preflight evidence were merged through
[PR #237](https://github.com/howardweale/lightyear-carddemo-modernization/pull/237),
merge commit `2defbb7074d453b1dd3a8c5e544cae2fa08297e5`.
The original plan head `0a157d0` and r2 head `51ada5e` are ancestors of that public
commit; the r2 executable evidence and controller files retain their original
bytes. These merges do not alter B05's frozen execution or B04's void status.

The **31 full evidence archives remain local**, so public availability of the
signed audit does not yet mean outside readers can replay the archives. The
[archive publication proposal](archive-publication-proposal.md) records their
measured size, leak-check findings and the release/replay gates. No archive
upload has been performed. Howard subsequently approved uploading in this task
on October 3; the proposal records that operator approval. The disclosure review
and public-only replay rehearsal remain incomplete, so upload approval is not
reported as leak clearance or public archive availability.

Review is operator review, not independent attestation. This audit does not
approve B06's preregistration or launch; J1 requalification, J2/J3 qualification
and the B06 native preflight remain pending.
