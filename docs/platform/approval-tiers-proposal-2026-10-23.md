# P4: proposed approval tiers — 23 October 2026

Status: proposal only. Howard must make a separate, explicit written policy
choice before any tier can grant merge authority. Merging this document would
retain a proposal; it would not activate automatic merging, change branch
protection, approve a run, or change the existing exact-head approval rule.
Until that decision and a separately reviewed implementation, Howard approves
the exact final green head of every non-status PR. Existing conditional
status-only authorization remains limited to its original scope.

## Proposed tiers

| Tier | Eligible examples | Proposed merge rule |
|---|---|---|
| Routine | A trusted current-status rebuild, a non-evidentiary generated report, a mechanically proven typo-only documentation change | All required and applicable targeted checks green on the exact reviewed head; permitted only after Howard explicitly enables this tier; record the exact head, run and result in the daily queue. |
| Code | Source, tests, dependency manifests, configuration, workflows, generators, ordinary documentation with semantic changes | Fresh complete CI and Howard's explicit approval of the exact final head, as today. |
| Evidence and authority | Freezes, plans, retained results, receipts, signatures, keys, spend, runtime admission, protection or policy changes | Fresh complete CI, Howard's exact-head approval and an explicit written decision covering the authority or evidence change. Approval to merge never implies signing, execution or spending. |

A generated evidence report belongs to Evidence and authority, even if a bot
produced it. A receipt path stays in that tier even when its only change looks
like punctuation. No tier relaxes either current freeze fence or a held-draft
restriction. Fenced work remains ineligible until its separately stated hold
conditions and post-run review are satisfied.

## Proposed CI classification

The classifier would be a reporting and eligibility check, not a grant of
human authority. Its rules and allowlists would come from the trusted base
commit, with full head/base identities in the result. A candidate could not
replace the classifier or its own classification rules to lower its tier.

1. Enumerate the complete paginated Git diff, including additions, deletions,
   renames, mode changes, submodules and links. Reject incomplete enumeration
   and ambiguous file types. Classify both old and new names of a rename.
2. Recompute the COPAU/F2 and POSTTRAN fences, plus dated-record and receipt
   references. Any frozen overlap yields `eligible=false`, independent of
   tier. Missing fence inputs or unresolved references fail closed.
3. Mark every authority/evidence path, referenced path and dependency in its
   protected closure Evidence and authority. This includes policy code,
   signing/admission/verifier code, key metadata, workflows that validate
   authority, retained result generators, and any alteration of approval
   conditions. An unmapped path cannot be assumed Routine.
4. A Routine generated report must match a narrowly allowlisted report kind
   and path, approved producer identity and source inputs. CI regenerates it
   using trusted producer bytes and verifies exact output bytes. A changed
   producer or changed output schema is at least Code; an evidentiary output
   is always Evidence and authority. Status must bind current-main facts;
   stale regeneration is ineligible.
5. A Routine typo correction must pass a narrowly defined mechanical edit
   rule, not a model's judgment that a change is harmless. Changes to numbers,
   dates, links, negation, operational claims, scope, permissions, caps or
   approval language are excluded. Unrecognized prose edits become Code.
   Referenced/dated/authority documents never use this exception.
6. Ordinary source, tests, dependencies, workflows and remaining semantic
   changes are Code unless rule 3 raises them. Classify all paths and take
   the maximum tier. Empty, ambiguous or incomplete classifications refuse
   Routine eligibility. Emit reason codes and bound source hashes.
7. Independently verify all latest checks are terminal with no failures,
   required-ci and applicable frozen/targeted gates succeeded, the head is
   unchanged, current-main preservation passed and no hold applies. Never
   use success from an earlier head or an obsolete merge-tree review.

A classification correction must itself receive the highest affected tier's
review. Human approval of one head does not transfer after a push. A changed
base requires fresh preservation review; a conflict requires a reviewed
resolution and fresh CI. No squash, force push, history rewrite or protection
bypass is proposed.

## Proposed classifier fixtures and acceptance contract

These are fixture specifications for a later implementation, not executed
results. A separate implementation PR must run them in required CI, including
adversarial candidate changes to its own policy files. This document contains
no classifier code, workflow change or runtime switch.

| Proposed fixture | Expected tier / eligibility |
|---|---|
| Trusted current-status rebuild with exact regenerated bytes | Routine, eligible only after policy activation and all gates |
| Same report with stale source head or altered generated bytes | Routine classification retained; merge ineligible |
| Allowlisted typo in unreferenced narrative documentation | Routine, conditional on the mechanical edit proof |
| Typo plus one production-source edit | Code; the highest tier wins |
| Typo plus a new test or dependency version | Code; the highest tier wins |
| Routine report plus a changed receipt | Evidence and authority; the highest tier wins |
| Source edit plus a spend-cap or approval-rule edit | Evidence and authority; the highest tier wins |
| Generated verification report with a claimed observed result | Evidence and authority, never Routine |
| Punctuation-only change in a dated receipt or frozen path | Evidence and authority; fenced overlap is ineligible |
| Rename a protected file into a nominally routine directory | Evidence and authority; classify both names and references |
| Candidate changes classifier to label all files Routine | Evidence and authority; trusted-base classifier still applies |
| Unknown report type, new workflow, or unmapped path | At least Code; cannot enter Routine |
| Change “not approved” to “approved”, a limit, date or evidence URL | At least Code; Evidence and authority when it changes a protected claim |
| Missing changed-file page, malformed manifest or unresolved reference | Classification incomplete; merge ineligible |
| Mixed Routine/Code/Evidence edits, in every file order | Evidence and authority in every permutation |
| Green old head followed by a one-byte push | Merge ineligible until fresh exact-head checks and approval |
| Held draft with every check green | Merge ineligible while the hold applies |

The later CI suite must assert the exact tier, reason codes, source bindings
and eligibility for each case. It must prove monotonicity: adding a higher-tier
change can never lower the result. At least one negative control must attempt
to replace the candidate classifier/allowlist and still receive the trusted
base's higher-tier verdict. Passing these synthetic fixtures does not establish
that every production path has been classified; coverage of the actual path
and reference inventory is a separate required report.

## Proposed operational controls and Howard's decisions

The daily queue would list every pending exact-head approval and each Routine
merge since its prior refresh, with title, full head, required-ci run, summary,
tier reason, risks and merge receipt. The once-per-day marker remains one
comment updated in place; per-PR final-green comments remain on each PR.
Routine activity would not restart ten-minute monitoring.

Howard must explicitly choose whether to activate Routine at all, approve its
exact allowlist and mechanical typo rules, and decide how generated reports
fit the eight-open-PR ceiling. Recommended first activation, if wanted: retain
the existing two-path status scope only, then review any broader class in a
separate policy PR. No authority is inferred from a title, label, bot account,
empty review queue, available slot or this recommendation.

Before activation, the implementation must provide an audit-only CI period,
the complete path/reference classification inventory, the fixture results,
and an exact proposed protection/policy diff. Howard can reject or narrow it.
Disabling any future Routine automation must leave Code and Evidence approval
requirements intact. No repository setting changes are part of this proposal.

Java idiomatic-index change: zero. This proposal does not alter executable
bytes, original tests, frozen records, candidate inventories, run windows,
attempt limits, model or monetary caps. P1 and P3 validation remain ahead of
this proposal; P5's CI-only failure drills follow before the Wednesday
28 October 18:00 Pacific go/no-go.
