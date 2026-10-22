# MS-106 installation, backfill and signed-only correction
Recorded 2026-10-21. Additive correction; no original text or dated evidence replaced.

MS-106 and the October 14 local activation record assert an installed login service,
a seven-record signed historical backfill and activated signed-only consumers.
The October 17 correction clarifies attribution/source commits but repeats those
operational assertions. Available evidence does not substantiate ANY of the three
on Howard's machine. They must not be treated as verified current deployment facts.

1. Installation: no confirmed Factory installation folder, authority path, named
   login task, startup item or port-8769 listener was found in the checked locations.
   The approved paths in plan.md are proposed first-install locations, not recovered
   historical installation details.
2. Seven-record signed backfill: the unsigned contract and claimed decision hash
   are historical records, not retrieved cryptographic proof at a trusted current
   journal head. We have not verified a surviving signing authority/private half.
3. Signed-only activation: no verified local consumer trust configuration and
   fresh backfill proof were established. A JSON field saying signed_only=true or
   green CI cannot establish that Howard's consumers were actually activated.

This corrects the evidence status; it does not assert no installation or signature
ever existed on any machine. The October 14-15 session logs were not recovered in
the checked local session directories. Prior narrative assertions are insufficient
to reconstruct lost credentials or signatures and must not be silently re-enacted.

## Original records preserved
- docs/milestones/MS-106/MS-106.md
- docs/factory/factory-local-activation-2026-10-14.json
- docs/factory/factory-local-activation-correction-2026-10-17.json
- docs/factory/tower-backfill-request-2026-10-14.json
- docs/factory/tower-backfill-inventory-2026-10-14.json
- docs/factory/tower-backfill-supersessions-2026-10-17.json

## Seven historical records requiring Howard's new review
- docs/factory/howard-decisions-2026-10-11.json
- docs/factory/howard-decisions-2026-10-11b.json
- docs/factory/equivalence-operator-acceptance-2026-10-12.json
- docs/factory/intcalc-duplicate-category-approval-2026-10-12.json
- docs/factory/posttran-phase1-rerun-authorization-2026-10-12.json
- docs/factory/b06-afternoon-preparation-2026-10-13.json
- docs/factory/merge-hold-lift-2026-10-14.json

Howard reviews their exact sources and supersession record before signing. A new
signature records today's action with original source dates preserved. It must not
claim October 14 signing occurred, make a historical-only acceptance unconditional,
authorize native B06 activity, lift a new merge hold or approve new model spending.

## Dependent records and completion evidence
dependency-review.md explains the POSTTRAN runbook/amendment/plans/request/readiness,
COPAU F2, PR415/F8, G1-G3/B07, INTCALC/APPL/equivalence, release packets and consumer
trust consequences. dependency-inventory.json is the enumerated record list,
including every directly matching milestone/index/status path in the audited tree.

The correction stays in force until separate evidence establishes each claim:
- Installation: exact approved source/bundle, host paths, Howard SID, disabled task
  receipt and inspected ACLs, followed by Howard's own start verification.
- Backfill: Howard's new public key and verified new seven-record proof/current
  journal, with unchanged source content/dates/conditions.
- Signed-only: verified operator-owned consumer configuration, fresh trust/proof
  and explicit Howard activation, with refusal tests retained from CI.

Software review or merge does not complete these operational items. This PR
delivers proposed installation software, CI checks and an honest correction only.