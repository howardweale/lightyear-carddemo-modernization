# Codex instruction: Howard's decisions and next work after PRs #318–#320

Howard decided this on 2026-10-11 at 2:00 PM PT. It **supersedes**
`codex-review-fixes-318-320.md`, which was not sent; everything in it is folded in
here.

Part A records Howard's decisions. Part B is the work. Standing constraints are
unchanged:

- no model calls beyond the budgets approved below, and only after Howard's
  one-line "go" for the exact hash;
- no Maintec or customer data;
- no rewriting of preserved evidence;
- separate worktrees;
- no machine-wide configuration changes;
- merge only with Howard's commit-specific approval, after every required check
  on the final head has completed green.

Record Part A as a dated decision file, `docs/factory/howard-decisions-2026-10-11b.json`,
plus a milestone note. Bind each decision to the hashes it names. Where a decision
says "approved, subject to", nothing executes until the condition is met and
Howard has sent the one-line confirmation.

---

## Part A — Howard's decisions

### A1. Equivalence review sample (20 mutants)

Howard accepts the 20-mutant review in Appendix 1 as an **AI-assisted operator
review**: Claude reviewed the arguments, Howard accepted the review. It is not
independent human attestation. Record it that way.

**Result:** 20 of 20 arguments are correct within their stated scope.

- **CBTRN02C-delete-MOVE-718-447 is host-scoped.** `TWO-BYTES-BINARY` has no
  VALUE clause. GnuCOBOL zero-initialises it, but Enterprise COBOL does not
  guarantee that. Classify it as `equivalent (host-compiler-scoped)`. It may be
  excluded only for twin-scoped claims. For any z/OS-facing claim it counts as
  unresolved.
- **The sample is dominated by one idiom.** 17 of the 20 are mutations of the
  `APPL-RESULT` status sentinel, and so is most of the population: about 83 of
  the INTCALC and 98 of the POSTTRAN argued equivalents.

**Decision.** Replace random sampling with two steps:

1. **Class-level proof for `APPL-RESULT`.** In both programs, `APPL-RESULT` is
   read only through its two 88-levels, `APPL-AOK` (0) and `APPL-EOF` (16). It
   is never displayed, moved, passed, or moved to `RETURN-CODE`. Lines 133–135
   and 142–144 were checked.
   - Implement this as one mechanical check: a reference census over the
     parsed program, failing on any new consumer.
   - Use it to cover every argued equivalent whose only effect is on
     `APPL-RESULT`, restricted to values other than 0 and 16, or to deletions
     whose argument holds under the census.
   - It is invalidated if the source hash changes.
2. **Individual review of every remaining argued equivalent.** That is roughly 50
   across both programs: receiving scale and size, skip-PERFORM, `TWO-BYTES`,
   abend and status display, ROUNDED, and the rest. Prepare one packet in the
   same format as the 20-mutant sample. Claude reviews it, and Howard accepts or
   rejects it.

### A2. scenario-threshold/2 — approved as amended, effective only when B1 completes

Releasable requires all of the following:

- **Business logic.** 100% of business-logic outcomes covered.
- **I/O handling.** Every I/O-handling outcome covered by fault injection or
  individually accepted by Howard. The two EOF edges accepted on October 11
  stand.
- **Mutant kill rate.** At least 90% of systematic mutants killed, over at
  least 50 eligible mutants per program.
  - **Eligible** means all sites, minus listed compiler refusals, minus
    equivalents that are (a) compiler-proven (TCE), (b) covered by the
    `APPL-RESULT` class proof, or (c) individually reviewed and accepted under
    A1.
  - Host-compiler-scoped equivalents are excluded only for twin-scoped claims.
- **No unexplained survivors**, and every survivor that has an argument is
  dispositioned.
- **Output fields.** At least 2 distinct values for each compared output field.
- **Measured on a fresh compiled campaign at the current head** (B1.4), not on
  the `3283265d` campaign.
- **Register dependencies.** Arguments that depend on a keep-or-fix entry carry
  that dependency (B2) and are invalidated if the decision changes.

### A3. POSTTRAN human review sheet

Howard has reviewed the ten records and **accepts all ten**. The completed file
is `posttran-decisions-unsigned.json`; Howard will sign it through the operator
flow.

The reasons were recomputed from the public ACCTFILE, XREFFILE and DALYTRAN
data, processing all 300 records in batch order: 262 posted and 38 rejected,
matching the twin.

**Improvement for future sheets:** include the account state each decision
depends on, read before the record is processed:

- credit limit;
- cycle credit and cycle debit;
- expiry date;
- the computed `WS-TEMP-BAL`.

Without these, a reviewer can't check an over-limit decision from the sheet
alone.

### A4. POSTTRAN second opinion — revised plan approved, subject to two amendments

- **Approved:** Phase 1 under plan `97b105a5…`:
  - direct Responses API transport;
  - three calls, attempts and compilations;
  - 750,000 input and 192,000 output tokens;
  - 64,000 maximum output tokens per call;
  - two hours;
  - a **$36** hard cap.
- **Amendment 1, labels.** Phase 1 results are labelled
  `independent model-built candidate`, not "factory conversion".
- **Amendment 2, preflight.** Add a zero-generation transport check before
  attempt 1: send the exact Phase 1 packet to the input-token counting
  endpoint. Record it in the ledger.
- **No other changes.** Publish the amended plan, its hash and a diff against
  `97b105a5…`. Don't call any model until Howard replies
  "go POSTTRAN \<amended hash\>".
- **Phase 2 is not approved.** It waits for adjudication of the Phase 1
  disagreements.

### A5. Keep-or-fix: two new legacy behaviours, both kept by default

Add both to `keep-or-fix-register.json`, with source hashes and lines.

1. **Duplicate transaction ID: posting is not atomic.** `2000-POST-TRANSACTION`
   runs in this order:
   1. update category balance (2700);
   2. update account (2800);
   3. write TRANFILE (2900).

   A duplicate `DALYTRAN-ID` fails the WRITE (duplicate key), and the program
   abends with RC 12 *after* the balances were already updated.
   - **Decision: keep.** The converted code reproduces the abend and the
     partial update.
   - Redefine the duplicate-ID invariant to expect exactly that: abend at the
     duplicate, earlier records posted, the duplicate's account and category
     balances incremented, and no TRANFILE row for it.
   - This resolves the "duplicate-ID invariant unresolved" item.
2. **Cycle-debit sign convention.** Negative amounts are added into
   `ACCT-CURR-CYC-DEBIT`, so it goes negative. The over-limit test computes
   `CYC-CREDIT − CYC-DEBIT + amount`, so refunds and payments *raise* the
   balance tested against the limit.
   - On the public batch, this gives 38 rejections; a net-balance reading
     (`CYC-CREDIT + CYC-DEBIT + amount`) gives 23, and 19 records differ.
   - **Decision: keep.** The converted code reproduces it.
   - Add one generated scenario that discriminates the two readings, and a
     regression test.

Changing either behaviour needs a separate explicit decision.

### A6. B06 two-attempt request — approved in principle; new window

- **Approved:** the scope and sequence in
  `docs/b06-engineering-two-attempt-request.md`:
  - attempt 1 strict, attempt 2 diagnostic with the 10-return cap;
  - Oracle-only J1;
  - the per-attempt time limits;
  - zero credit;
  - the observer at 1,536 MiB, container 2,048 MiB.
- **Window moved to Tuesday, October 13, 2026, 9:00 AM–noon PDT.** October 12 is
  withdrawn.
- **Execution needs one executable commit** (B3.1). Deliver the revised request
  by **Monday October 12, 5:00 PM PDT**. Howard replies
  "go B06 \<commit\> \<request seal\>". Nothing runs without that line.
- **Attempt 2 caps.** Attempt 2's purpose is to see what follows the 12,400
  point, so it should be able to reach about **37,000 generation entries**
  (three times the cluster) within its 60 minutes.
  - Size the ordinary-evidence and metadata caps from the B3.2 projection to
    reach that point.
  - Howard pre-approves up to **150,000 ordinary-evidence records**,
    **1,500,000 metadata records** and **384 MiB of metadata** for attempt 2
    only.
  - Private output stays at most 8 GiB, and free space at least 60 GiB.
  - Attempt 1 keeps the current caps.
- **"Cause identified" for Part 6, pre-registered.** It means one of:
  - (a) a lifecycle or class-prepare record at the sequence of the first
    unmatched return that explains the missed entry breakpoint: request
    disabled, class redefined or reloaded, or thread-filter mismatch; or
  - (b) an application-phase marker that ties the about 12,400 point to one
    operation and reproduces in both attempts.

  Anything else counts as "not identified", and the firm stop rule applies.

### A7. Alternatives evidence (#319)

- Approved: a **read-only export** of the retained application image `554a5203…`.
  Use `docker image save` or an equivalent layer export to extract its JDK.
  - No container is created or started.
  - No network access.
  - Outside any J1, B06 or evidence window.
  - Record the command, the image digest and the hashes of the exported
    layers.
- Approved: prepare, but **don't submit**, a contingent native count-only
  request, as described in B4.2.

### A8. B07

- **Primary hypothesis:** two-sided superiority of graph (G) over plain search
  (S) on final pass rate, pooled across J1–J3 and stratified by journey. The
  test follows the slot-independence decision already in the plan. Report the
  effect size and its interval.
- **Non-inferiority margin: 15 percentage points**, for the secondary claim that
  G is not worse than S. The ±15-point precision matches 72 analysed trials per
  arm. Run the pre-freeze power simulation. If it shows the margin can't be
  assessed at the planned size, report that to Howard before freezing.
- **No sample-size reduction.** Keep 24 analysis slots per journey and arm, and
  no drift arm.
- **Calendar.** The 96-hour cap is replaced by a two-runner window of at most
  **14 calendar days**, with both arms on both runners as planned.
- **Spending is not approved yet.** Before any trial, bring Howard the exact
  model-call, token and dollar budget for G+S.
- **Sequencing.** B07 starts only after the B06 Part 6 decision, and after the
  Part 1.5 graph-coverage proof has passed.

### A9. Multipass reproduction

Howard replaces the Multipass requirement. The replacement is two clean twin
builds from an `ubuntu:24.04` image pinned by digest, on two different machines:
the GitHub-hosted runner, plus Howard's Mac or a cloud VM. The build passes if
the compiled binary hashes match. Any difference goes in the twin limits
register.

### A10. ZD&T

- **No purchase yet.** Codex drafts a design note only (B5.2).
- Howard will ask IBM to confirm in writing that the licence covers internal
  engineering calibration, and demos where Lightyear converts client code. IBM
  excludes "preproduction testing".

### A11. Priority of spec workstreams after Part B

Do them in this order:

1. **Generic scenario engine** (Workstream 1.2, B2.3). It is the product claim.
2. **Dual-run prototype** (Workstream 5). It is the customer story. Use
   CardDemo batch, with the twin standing in as "legacy production".
3. **Production versus evidence mode** (Workstream 4).
4. **Parallel candidates** (Workstream 3).

For each, write a one-page plan for Howard before starting.

---

## Part B — the work

**Order:** B3 first (the B06 deadline is Monday 5 PM), then B1, then B2. The
rest can run in parallel.

### B1. Equivalent-mutant evidence (#318)

1. **Trivial compiler equivalence (TCE).** For each of the 227 argued
   equivalents:
   - compile the original and the mutant with the pinned GnuCOBOL at an
     optimising level;
   - compare the generated C, or the stripped object code, after removing line
     and debug directives;
   - record identical output as `equivalent (compiler-proven)`.
2. **The `APPL-RESULT` class proof** (A1.1): implement the census and apply it.
3. **Targeted kill attempts for what remains.**
   - Run a bounded generated campaign that varies exactly the fields and paths
     each argument claims are irrelevant: 200 cases per mutant, fixed seed.
   - A kill refutes the argument, and the mutant moves to `killed` with its
     witness.
   - Report the refutation count, even if it is zero.
4. **Fresh compiled campaign at the current head.** The generator changed after
   the measured campaign. Rerun the full compiled campaign at the current head
   and confirm:
   - 421 and 483 sites;
   - zero refusals;
   - identical dispositions for retained IDs.

   Publish any differences. Threshold/2 is measured on this run.
5. **Remaining review packet** (A1.2): every argued equivalent not covered by
   items 1–3.

Then report against threshold/2, separately for twin-scoped and z/OS-facing
claims.

### B2. Register links, sign quirk, scenario engine (#318)

1. **Register dependencies.**
   - Add `depends_on_register` to every equivalence argument that relies on a
     keep-or-fix entry, and scan all of them.
   - Known case: `CBTRN02C-delete-MOVE-557-314`. It is a dead store only
     because of REWRITE-109.
   - Changing that decision invalidates the dependent arguments. Prove this with
     a fixture register in which REWRITE-109 is flipped to "fix".
2. **A5 register entries and scenarios:**
   - the duplicate-ID non-atomic abend, with the invariant redefined as in A5;
   - the cycle-debit sign scenario, with its regression test.
3. **Generic scenario engine** (Workstream 1.2). Today `scenario_generation.py`
   hand-lists the variants for each program, and its "solver" picks from
   hand-chosen 3–4 value domains for 2 of the 102 decisions. Rename that
   generator `curated-finite-witness` in receipts now. Then build the generic
   version:
   - **Boundaries from layouts.** Derive them from every input field's bound
     copybook PIC and USAGE, with no per-program code:
     - limits;
     - zero;
     - ±1 at the scale;
     - sign;
     - rounding straddles at each COMPUTE that uses the field.
   - **Constraints from the decision inventory.** Translate the 102 inventoried
     conditions, through the bound data flow, into constraints over input
     fields. Solve them with Z3, or exhaustively over derived domains. Build
     the input records from the copybook layout. List the conditions that
     could not be translated, and why.
   - **Coverage-feedback loop.** Target uncovered outcomes until each is covered
     or proven unreachable, within a declared budget.
   - **Acceptance test.** Run it with zero hand-written scenarios on two unseen
     CardDemo batch programs, for example CBTRN03C and CBSTM03A. For each one,
     report:
     - business-logic and I/O coverage;
     - the systematic kill rate;
     - the gaps.

   Bring Howard the one-page plan (A11) first.

### B3. B06 executable request (#320) — deliver by Monday Oct 12, 5:00 PM PDT

1. **One executable commit.**
   - Prepare the hold-release change on its own branch.
   - Bind its exact commit, the unchanged observer source hash `02b2f7fd…`,
     the 14 class hashes and a new request seal for the **October 13**
     window.
   - The runner verifies every bound hash before launch and refuses on any
     difference.
   - No merge to `main` before execution unless Howard approves it separately.
2. **Projected stopping points.** Using r3's per-entry rates and the bounded
   format's measured per-entry sizes, give the generation-entry count at which
   each cap trips:
   - ordinary evidence (r3 had about 2.0 non-audit records per entry);
   - metadata records and bytes, at native payload sizes;
   - pending slots;
   - private output.

   Set attempt 2's caps within the A6 ceilings so that it can reach about
   37,000 entries. If it can't within those ceilings, say so.
3. **Pre-registered criteria.** Put the A6 "cause identified" criteria into
   the request, and into the Part 6 report template.
4. **2c witnesses.** Confirm the bounded format records class-input witnesses
   for every generation entry. In #319, 61.5% of entries had none. If it
   doesn't, add them and re-run the r6 host test to show memory is unchanged.

### B4. Alternatives (#319)

1. Using the A7 export, rerun the JLI, CDS and dump matrix on Linux with the
   retained image's exact JDK, against the synthetic fixture. Report it beside
   the Windows Corretto results.
2. Prepare, but don't submit, a contingent request used only if Part 6 finds no
   cause: one native **count-only** run with the entry-only counter, comparing
   a JLI and CDS image trained on a J1 host replay against the untouched
   runtime.
   - No payload capture.
   - Give its window, caps and expected cost.

### B5. Twin

1. **cp037.**
   - Reword the 54/54 result as "no regression from cp037 key mode". Every
     CardDemo key in those cases is numeric, so ASCII and EBCDIC order agree
     anyway.
   - Add discriminating fixtures: mixed letter and digit indexed keys, with the
     expected EBCDIC order from the collation probe.
   - Show that cp037 mode yields EBCDIC order and ASCII mode doesn't.
   - The decimal-only restriction stays until z/OS or ZD&T confirms.
2. **ZD&T design note (A10).** Cover:
   - an `ibm-zos-emulated` calibration rung;
   - a one-time run of the preregistered INTCALC and POSTTRAN scenarios,
     through the Zowe CLI;
   - COBDATFT and MVSWAIT assembly, bind and caller execution;
   - which twin-limits entries each step resolves;
   - the host's needs: Ubuntu or RHEL, 300 GB of disk, a USB licence key;
   - the licence question.
3. **Two-machine reproduction** (A9).

### B6. Housekeeping

- **`docs/factory/current-status.md`.** Generate it from the decision files,
  registers and latest receipts. Tower links this, not the historical
  milestones.
- **CI timing.** Report push-to-green times for #316–#320, plus the queue.
- **Labels.** Make the A4 labels and the B2.3 generator rename everywhere
  receipts or docs use the old names.

## Report back

Lead with:

1. the B06 executable request: commit, seal, projected cap stopping points and
   attempt 2 caps. It is due Monday 5 PM PDT.
2. the amended POSTTRAN plan hash and its diff;
3. B1 results: TCE-proven, class-covered, refuted and individually-reviewable
   counts, and the fresh campaign, against threshold/2;
4. the generic scenario engine plan.

For each PR, give its link, the focused tests, and the completed green
final-head CI result.

---

## Appendix 1 — review of the 20-mutant equivalence sample (Claude, for Howard)

The verdicts below were checked against `spec/mainframe/public-source` at the
pinned hashes.

| Mutant | Verdict | Note |
|---|---|---|
| CBACT04C-constant-403-212 | Agree | `APPL-RESULT` read only through 88-levels 0/16; 11 is neither |
| CBACT04C-delete-MOVE-601-355 | Agree | 8 is retained; neither 0 nor 16; the failure branch is unchanged |
| CBACT04C-delete-ADD-192-50 | Agree | `WS-RECORD-COUNT` (group `WS-COUNTERS`) has no other reference |
| CBACT04C-delete-MOVE-401-211 | Agree | 1110-GET-XREF-DATA has no 8 initialiser; the prior successful operation left 0; failures abend |
| CBACT04C-receiving-size-133-19 | Agree | S9(9) and S9(8) COMP are both 4 bytes on GnuCOBOL and on z/OS; values are small |
| CBACT04C-constant-523-286 | Agree | Sentinel 8 is overwritten before any read |
| CBACT04C-delete-MOVE-502-277 | Agree | Same invariant as 401; the prior operation left 0 |
| CBACT04C-delete-MOVE-290-128 | Agree | Sentinel 8 is overwritten before any read |
| CBACT04C-constant-235-81 | Agree | Sentinel 8 is overwritten before any read |
| CBACT04C-delete-MOVE-240-91 | Agree | 8 is retained; neither 0 nor 16 |
| CBTRN02C-constant-583-332 | Agree | Sentinel 8 is overwritten before any read |
| CBTRN02C-delete-MOVE-718-447 | **Agree, host-scoped** | `TWO-BYTES-BINARY` has no VALUE clause; zero start holds on GnuCOBOL, not guaranteed on z/OS |
| CBTRN02C-constant-638-377 | Agree | Sentinel 8 is overwritten before any read |
| CBTRN02C-constant-515-283 | Agree | 13 is neither 0 nor 16 |
| CBTRN02C-constant-255-87 | Agree | Sentinel 8 is overwritten before any read |
| CBTRN02C-constant-515-282 | Agree | 11 is neither 0 nor 16 |
| CBTRN02C-delete-MOVE-455-246 | Agree | 8 is retained; neither 0 nor 16 |
| CBTRN02C-constant-680-414 | Agree | 11 is neither 0 nor 16 |
| CBTRN02C-constant-588-339 | Agree | 11 is neither 0 nor 16 |
| CBTRN02C-constant-718-445 | Agree | -1 to unsigned binary stores 1, so the left byte is still 0, then the right byte is overwritten; same on z/OS |

**Limit of this sample.** Zero errors in 10 per program bounds the error rate
only at about 26% (95%). It mostly exercises the `APPL-RESULT` idiom. That is
why A1 replaces random sampling with a class proof plus full review of the rest.
