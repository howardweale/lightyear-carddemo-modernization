# Factory review follow-up for PRs 311–317 — 2026-10-11

The source/data-flow classification confirms that the existing public+generated
receipt covers all inventoried business outcomes: INTCALC **8/8 business, 56/86
I/O, 64/94 combined**; POSTTRAN **24/24 business, 49/86 I/O, 73/110 combined**.
This is a classification of previously observed events, not a new native run.
`decision-classification.json` lists every outcome with exact source hash and
reviewed data-flow rationale. A missing tariff chooses a business fallback; a
missing card/account chooses a business rejection. These are deliberately not
classified by a status-name regex. EOF traversal and operational failure paths
are I/O handling. Any source change refuses until classification is reviewed.

The prospective lexical-overlap corrections are in
`docs/oct10-factory-foundations-milestone.md` and
`docs/business-rules/milestone-2026-10-10.md`. The instrumentation milestone already
labels 16/47 correctly. No signed historical evidence was rewritten. Repository
search found no other literal 16/47 coverage claim in docs, catalogues or views.

Systematic generation currently inventories **427 INTCALC and 490 POSTTRAN**
source-site mutants. These counts are generated, not claims of compiled mutants
or kills. The remote Ubuntu24 campaign compiles every member, compares return codes, complete logical outputs and program stdout (excluding probe records), separates divergent
kills, failure kills, survivors and compilation refusals, and preserves every
result. A survivor is unresolved unless a scenario kills it or a reviewed
individual equivalence proof exists. Only individually listed source-bound overwritten-sentinel or indistinguishable-failure-value arguments may exclude a surviving compiled mutant; each excluded survivor carries its own exact source-bound rationale. Binary-layout arguments additionally require a recorded compiler LENGTH probe. They are not blanket waivers; the old eight hand-picked mutants do not form the new denominator.
Mutants with altered FD layout may legitimately not compile or fail admission;
those outcomes remain visible. Receiving-field mutations also cover every numeric PIC site in the pinned included copybooks. Each operand is hash-bound; originals are preserved.

Engineering-only I/O fault declarations select a specific operation, status,
expected diagnostic and RC before compilation. Derived executables keep original
source bytes and source-line probe identities. Expected CEE3ABD refusals have RC12.
The account REWRITE handler sets reason109; its actual downstream behaviour is
recorded by the campaign rather than treated as an assumed abend. No z/OS failure
mechanism equivalence is claimed. The compiled cp037-vs-ASCII twin reconciliation matched **46/46** public/generated cases at head `2cb581d`; the [receipt summary](cp037-twin-review311-reconciliation.json) binds the exact run and full receipt. This includes returned bytes, status and refusal classes. Decimal-only production restrictions remain; these cases do not establish z/OS alphanumeric-key semantics.

The unsigned revised threshold proposes 100% business outcomes, all I/O outcomes
covered or individually accepted in an exact signed operator policy, 90% kills
over at least 50 systematic eligible mutants with listed equivalence exclusions,
and two distinct values in each compared output field. Compiler refusals and
unresolved survivors block adequacy. Howard has not approved this threshold.

The revised POSTTRAN preregistration is
[revised-plan.json](posttran-second-opinion/revised-plan.json). It pins the actual
installed Codex0.160.0 bytes (`4b01d5920e6785614727443bbecf343f4dedbb7347052b72ba805aab6353ef01`)
and explicitly does not pretend CLI configuration enforces a server token cap.
The proposed dispatch path is an explicitly supplied Responses API transport with
`max_output_tokens=64000`, including reasoning. The offline broker requires the
new exact plan approval and rejects prior approval, attempt/dollar reservation
exhaustion, changed inputs/client bytes, missing usage, cap breach and incomplete
responses. It is not connected to credentials or a live transport.

Prior public factory evidence records 89,246 aggregate output tokens across ten
calls (8,924.6 mean), but does not separate reasoning or record per-call tails.
64,000 is therefore proposed headroom, not a measured tail percentile. Phase1
proposes three calls, 750,000 input/192,000 output tokens, two hours and $36
API-equivalent cap; phase2 proposes two calls and $24, still separately blocked
on adjudication and approval. Conservative retained planning rates reserve
$11.05/call. Fresh official price verification is required before dispatch.
The previous approved $25/48,000-token plan does not authorize this revision.
**Zero model calls, compilations of model output or candidates were produced.**

The readable [POSTTRAN review page](posttran-human-review.html) is a standalone
HTML file: download/open locally, enter each decision/reason and your name, then
return its unsigned JSON in chat. No GitHub Pages deployment is claimed, and no
operator signature is created by the page.

Actual compiled campaign results and final-head CI will be recorded before this
PR is offered for commit-specific merge approval. No B06 native run or hold was
changed by this work.

The first completed older INTCALC campaign (497 source-only mutants, before stdout strengthening and copybook sites) measured58 divergent kills,135 failure kills,191 survivors and113 compiler refusals. This193/497 result is preserved as preliminary evidence, not replaced by the old8/8 narrative. Current full-set results remain required.

Surviving mutants also receive up to three declared fault challenges chosen from their source paragraph or representative error/extended-status/INVALID-KEY paths. The same fault seam is applied to the baseline and mutant; an incompatible seam or a derived compile refusal is recorded as unavailable, never counted as a kill of a normally compiled survivor. Predicate probes in these fault-mutant copies are not claimed as changed-code coverage. New killing fault/scenario pairs are retained explicitly.

Review of the earlier compiler refusals found a generator defect: digit-prefixed paragraph identifiers such as `1000-READ` had been split into numeric constants. Those false sites are removed, rather than silently treated as meaningful invalid mutants; their old results remain preserved. Numeric receiving-site generation now handles both literal/repeated PIC digits and parenthesized scales. The corrected427/490 inventories therefore supersede the preliminary497/499/531 and604 denominators. A new large-rate INTCALC scenario targets narrowed monthly/total receiving fields. Individually listed dead-counter and empty-fee-paragraph arguments make no claim about other survivors.

Survivor-driven synthetic cases add a third account, successful DEFAULT tariff fallback, cyclic debit, invalid-then-valid and new-then-existing transaction sequences, and expiry-prefix boundaries. These are new witnesses, not assumed kills. A compiled LENGTH probe records binary storage classes before any corresponding ABI-preservation argument is permitted. All new outcomes remain subject to the full compiled campaign.

Completed pre-challenge fault campaigns reached **INTCALC 8/8 business, 85/86 I/O, 93/94 combined**, and **POSTTRAN 24/24 business, 85/86 I/O, 109/110 combined**; all 24/24 and 29/29 declared fault expectations matched respectively. The only unobserved edge in each is the first EOF guard false edge. [Source-bound gap arguments](io-gap-arguments.json) explain why TEST BEFORE prevents that edge; these arguments neither remove it from the denominator nor count as Howard's acceptance. POSTTRAN reason109 returned RC0; this observed failure propagation gap remains visible.
