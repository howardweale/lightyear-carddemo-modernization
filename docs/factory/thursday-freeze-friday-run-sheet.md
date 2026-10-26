# Thursday freeze and Friday COPAU run sheet — review draft, 26 October 2026

This checklist is prepared now for completion/review by Tuesday 27 October 18:00 PT. It records gates; it does not authorize a merge, signature, private-data preparation or run. No keys or secrets belong in this document, Git, chat, CI or artifacts. Codex performs no model calls, signing or Tower actions. Factory Tower remains the existing installation on port 8769; never 8768 and never a second root.

Latest instruction: no merges before the Friday run, and no CI runner usage during Friday 08:00–20:00 PT. This is stricter than the earlier Thursday merge deadline. If the existing main is not already ready, preparing green branch commits cannot satisfy the green-main run prerequisite under that rule. Report NO-GO and request a schedule or merge-policy decision in the next approval batch; do not infer an exception.

Time gates (America/Los_Angeles, PDT / UTC-7)
- Tuesday 27 October 12:00 PT (19:00 UTC): reservation exact-source review deadline, not a reason to delay ready work. Requests batched at 17:00 daily, plus 12:00 only if every actionable item is blocked.
- Tuesday 27 October 18:00 PT (28 October 01:00 UTC): exact #455 disposable-drills and required-ci green target; final eight-drill plan and this checklist due. Report a miss explicitly, including the external dependency, instead of silently moving Friday.
- Wednesday 28 October 12:00 PT (19:00 UTC): POSTTRAN execution PR latest, after Howard's signature/proof and final-head review. Aim to finish POSTTRAN Wednesday.
- Wednesday 28 October 18:00 PT (29 October 01:00 UTC): explicit COPAU go/no-go evidence review.
- Thursday 29 October before 07:46 PT (14:46 UTC): POSTTRAN single run AND receipt complete. POSTTRAN-bound paths remain frozen through 14:46 UTC. Do not merge or modify them in anticipation of success.
- Thursday 29 October 08:00 PT (15:00 UTC): main freeze. Nothing merges after this cutoff. The current no-merges-before-Friday-run instruction also applies; an exact-commit review alone does not lift that hold.
- Friday 30 October 08:00–20:00 PT (15:00 UTC–31 October 03:00 UTC): conditional COPAU window, not an authorization. The earlier of start + 28,800 seconds and window end is the hard stop.

Wednesday 18:00 go/no-go evidence
1. Exact #455 head, base, merge candidate and actual latest CI run links. All meaningful checks terminal, with disposable-drills and required-ci green. No previous-head success or a skipped drill substitutes.
2. One eight-row drill table with retained artifact paths, source hashes, case outcomes, raw controller receipts, attempt identity, nonce and accounting chain bindings. All unaccepted gaps fail closed. Planned evidence review: distinguish simulated boundaries from deployed path claims.
3. Reservation approval ledger: before/after hashes for every changed source, orchestrator.py and cli.py explicitly, complete hunks, and coordinated trusted-main validator/manifest. No unapproved source is published. Exact approval provenance must be real; pending/null manifest is inert and cannot be activation staging.
4. CI proof of reservation before every model transport; kill before reserve yields no send; kill after reserve retains usage/cost upper bounds and all completed observations; normal receipts retain their existing semantics. billing_final=false and the exact marker 'unknown; reserved upper bound recorded' plus Howard invoice reconciliation statement are required. Cap/reservation arithmetic stays unchanged.
5. Final launch executable/argv, configured provider routing, model config bytes/digest, selected roles, service tier/rates, input-token upper-bound and count-endpoint billing treatment. Existing byte bounds and estimates do not themselves prove billed-token coverage. Any unresolved required bound means NO-GO.
6. Actual Tower append route/fallback evidence, workspace execution mutation, network loss, wall deadline and duplicate admission proof. A synthetic POST or trust-head GET outage alone does not meet append-outage criteria.
7. POSTTRAN status and remaining reservation/receipt deadline; no conflict with frozen paths or its one-attempt namespace. No repeated reservation, run, repair or proof regeneration to recover a failed attempt.
8. List all approvals still pending and their owners. If any required item is missing, record NO-GO and propose a new window for Howard's decision; Friday does not move automatically. Do not infer approval from silence or the arrival of a time gate.

Planned prerequisites: main must be green and approved by Thursday 08:00 PT
- Planned prerequisite: Howard-approved exact final green commits for the required production durability changes and matching main-policy binding. Preserve all frozen POSTTRAN, F2, judge, workflow and operational-record constraints.
- Current main required-ci and applicable source, frozen-path, model-admission, budget, isolation, public-corpus and targeted regression gates. The corresponding artifacts must identify this exact main commit, not a branch parent.
- Planned prerequisite: an exact build/merge record tying approved #455 source bytes to main, with no unapproved intervening change. Pending policy/runtime incompatibility is a blocker; no bypass or temporary waiver.
- POSTTRAN run/receipt completion before 07:46 PT and independent confirmation of frozen-path expiry. That does not permit a late merge after 08:00.
- Deferred qualification fixes remain separate from #455, excluded from run-bound paths, and unmerged until after the run. They cannot be smuggled into the freeze commit to turn unrelated gates green.

Frozen-main preparation sequence (public documentation/evidence only by Codex)
1. Record the exact main commit/tree, applicable protected-path hashes and successful current-main CI. Lock further merges at 08:00 PT.
2. Planned step: rebuild the public COPAU corpus index and boundary in authorized CI from that exact frozen commit and the exact 403-file workspace manifest (380 capsule members + 23 source objects). Record image, observer, policy, WorkOrder, request, plan and source hashes. Never consume work/mainframe/arrivals/ or other Maintec data.
3. Preserve first-run graph=none, memory=disabled, context=packed and the known packed-context limitation. No graph/memory expansion. Changes to source, workspace, launch templates or settings invalidate prior index approval.
4. Present exact boundary/index digests and documented dynamic-input limits for Howard's review. Public collection success is not approval. Do not access or generate private bundles or credentials.
5. Planned operator step: Howard performs any separately approved private custody and signature steps outside Codex. Retain only permitted public attestation/binding references. No secret value, credential, private key, private path or private expected value is requested or copied here.
6. Recompute dated concrete F2 records from the frozen executable and Howard-provided public metadata. Preserve historical records. Bind exact model-config consumption, provider/model/roles, boundary/index, image, workspace, current Tower trust and plan/request seal. No invented digest, issuer, approval or journal head.
7. Planned step: recheck the exact final records and runtime in CI under the authorized stub-only/no-signing arrangement. request_ready=true requires all bindings and gates; run_authorized remains false until Howard's separate signature and go decision.
8. Any needed production change after the freeze means stop and seek a new window; Planned stop rule: do not amend the approved run's bytes in place.

Friday run sheet — Howard's conditional actions, not actions Codex will execute
Before 08:00: finish and retain all CI checks; no CI runner usage is allowed from 08:00 through 20:00 PT. Planned preflight: verify the exact approved frozen executable, plan/request, workspace/image, final launch/config and current trusted Factory Tower head. Planned preflight: match every approved hash, required receipt and remaining artifact retention. Confirm no prior consumed reservation and no unaccepted drill/billing/admission gap. Confirm the operator identity campaign-authorizer and existing Factory Tower on port 8769.
At or after 08:00: Howard makes the explicitly reviewed decision and signature through the existing Factory Tower. No machine signs. A GitHub approval alone is not the Tower signature. Missing signature or proof means no execution.
Planned immediately before launch: verify the final signed bindings and launch window. Planned invariant: preserve USD10, 28,800 seconds, the reviewed role/model configuration, zero automatic retries/fallback and all attempt/repair limits of the exact approved COPAU plan. Do not import POSTTRAN's allowance into COPAU or vice versa. POSTTRAN is one attempt only.
During execution: use the existing reserved/observed journal and complete controller evidence. Observe deadlines and caps without touching configuration. Planned stop condition: stop on an append failure without approved durable fallback, changed workspace/bindings, signature/trust failure, leak/isolation detection, denied network boundary, missing reservation, unknown completed-call accounting, cap violation or elapsed/window boundary.
On interruption: preserve all original bytes, nonce and reservation. Planned interruption rule: use only an approved abort-only reconciliation path; no automatic resume/retry/new admission, deletion, reset, key regeneration or history rewrite. Planned pending-usage rule: use the exact accepted marker only when every condition is proven. Howard later reconciles actual cost against the provider invoice.
At completion/stop: retain raw receipt, identity, hash-chained accounting/events, each physical reservation/observation, observed completed usage, final status, exact executable/config and CI/artifact provenance. Flag billing_final=false whenever required; never invent zero cost. End no later than min(start+8h, 20:00 PT). No late finishing grace period.

Current disposition
NO-GO remains the evidenced state until the required gaps close. Not authorized: this draft grants no Friday run or machine signing. Green main, a ready F2 request and a verified billable upper bound are not established. The latest request's CI-only/no-model/no-keys/no-machine-signing rules take precedence over earlier fixture workflows.

Source references inspected statically at main 62170a5e6644bc8a41b05aa708a0a9c8c7f0d3ef:
docs/factory/copau-f2-prerequisites-2026-10-22.md
docs/factory/copau-run-visible-boundary-2026-10-24.md
Retained POSTTRAN execution handoff and Monday refresh evidence under work/oct18-review-fixes.
