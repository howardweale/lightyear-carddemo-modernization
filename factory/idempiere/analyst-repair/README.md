# Analyst-led native journey repairs

This campaign generates partial invoicing again from public inputs and API references. MS88's private business expectations, native readback, footprint and equivalence judge remain unchanged. It uses the existing local Oracle and PostgreSQL checkpoint images. It starts no GCP resources.

The initial builder prompt is [builder-input.json](builder-input.json). It contains scenario inputs, the trace interface and source API examples, with every assertion removed from the MS86 example. It contains no predicted invoice totals, expected stock result or gate results. The builder proposes a Java file; the patch broker writes it. Neither agent has tools or access to the native databases.

## The repair boundary

After a failed native attempt, a deterministic filter reads its observations and constructs a closed list of permitted diagnostics. An analyst agent selects from that list. The controller, not the analyst's prose, constructs the next builder message.

| Permitted category | Information forwarded | Information withheld |
|---|---|---|
| Compile error | Candidate file, line, structural error code, API symbol or types | Echoed source from logs, arbitrary diagnostic strings, business values |
| API type mismatch | Typed accessor, return type, field and source hash | Assertion expected/actual values |
| Outside footprint | Changed table and a source-verified application call path | Database rows, counts and expected business outcomes |

The retained MS88 failures exercise all three classifications. The accounting-history case resolves to `Doc.postImmediate → DocManager.postDocument → Doc.post → Doc.deleteAcct`, which writes `T_Fact_Acct_History`. The footprint does not expand to admit the write.

The analyst returns one forward/reject decision with a closed reason code for every diagnostic identifier. Unknown identifiers, missing decisions, extra fields, explanatory prose and invented fixes are rejected. Only forwarded diagnostic objects reach the builder. A business-value failure or unsupported finding stops the campaign. A stopped campaign is not a verified journey. Permitted repairs do not require human approval; budget increases do.

Compiler diagnostics preserve visibility, declaring type and required/supplied parameter types. Where a symbol can be resolved in the pinned upstream source, the filter supplies matching public declarations automatically, including their declaring class and source hash. It exports signatures, never method bodies or expected values. Typed API risks in the enclosing failing method can be surfaced without revealing an assertion's expected and actual values.

## Prepare and execute

Use the Python environment with the `control-tower` extra and the prepared local Docker images described in [the native replay guide](../ms86-journeys/README.md). Run from the repository root:

```powershell
$env:PYTHONPATH = 'src'
$env:PYTHONUTF8 = '1'
python -m lightyear_calibration.journey_campaign prepare --campaign work/ms89/campaign-01 --executable <pinned-codex.exe>
python -m lightyear_calibration.journey_campaign run --campaign work/ms89/campaign-01 --executable <pinned-codex.exe>
```

Preparation pins the client version **and executable SHA-256**, public inputs, judge implementation, native environment and data lineage. Every agent invocation checks the client identity before launching. Every native stage checks implementation hashes. A different executable, altered prompt, changed scope or changed judge fails the precondition.

The initial limit is five client invocations in total, counting **both builder and analyst**, with 900 seconds per call and a four-hour campaign limit. A repair cycle needs one analyst and one builder call. Failed transports consume a call. There is no implicit fresh budget for another attempt. Retained failed databases consume local disk; cleanup removes only run-owned resources and destroys ephemeral credentials.

The original two replay receipts establish the starting data/environment lineage. Their implementation identities remain historical. The new controller has its own pinned identity; it does not pretend to be the old controller.

### A stopped campaign and a budget increase

`propose-resume` prepares a reviewable document; it neither raises the active limit nor calls an agent. After the operator approves that specific proposal, `resume` archives the previous plan, authorization and receipt, activates the signed amended plan and continues the cumulative call count. It never resets the counter to zero.

```powershell
python -m lightyear_calibration.journey_campaign propose-resume --campaign work/ms89/campaign-01 --executable <pinned-codex.exe> --max-client-invocations <approved-total-limit>
# Review resume-proposal.json and obtain approval before the next command.
python -m lightyear_calibration.journey_campaign resume --campaign work/ms89/campaign-01 --executable <pinned-codex.exe> --proposal-sha256 <exact-approved-proposal-hash>
```

Judge and public-input changes are refused. The proposal discloses any change to the new controller or diagnostic-filter implementation; such framework work is human assistance, even when candidate repair bytes remain zero. Previous signed stops and per-attempt implementation hashes remain available for review.

The signed campaign plan and its budget amendments govern **agent calls**. The original MS88 extension declaration is retained unchanged as the business/gate contract; its historical agent-policy numbers do not grant or constrain the separately authorized MS89 campaign budget. Each native plan links back to the exact active campaign plan and authorization.

## Measurements and independent review

Each call records prompt, event transcript and proposal hashes, reported token usage, elapsed time and failure status. Each native attempt publishes its judge hashes, candidate hash, signed result and elapsed time. The campaign totals include failed transports, failed native attempts and analyst calls. Unknown usage is explicitly unknown. Cached input tokens are a subset of input tokens, not an extra charge added to them. The signed-in account exposes no per-call dollar invoice, and local electricity is not measured.

The zero-byte metric applies to **repair source and repair messages after the pinned initial prompt**. It excludes writing the specification, API documentation, controller and judge. An audit compares each executed candidate byte-for-byte to the signed model proposal, and each repair prompt to the initial prompt plus the previous candidate and selected diagnostic objects. Drift produces an invalid-provenance result with an unknown metric, not a fabricated zero. Signatures establish local attribution, not independent attestation.

Control Tower's **Run** panel shows the native attempt, pinned client, judge hashes and whole-campaign costs after completion. Costs belong to the entire campaign, even when viewing one attempt. Earlier failures remain visible.

The campaign audit export contains every call, candidate, diagnostic, native attempt plan and failed receipt, but excludes private keys, retained database filesystems and credentials. Its verifier checks provenance and recomputes accounting. Native database readback has a separate lossless evidence publication and gate replay; passing the audit verifier alone does not mean the journey passed.

```powershell
python tools/publish_journey_campaign.py publish --campaign work/ms89/campaign-01 --output <new-audit-directory>
python tools/publish_journey_campaign.py verify --output <audit-directory>
```

## Recorded campaign

Campaign 01 initially stopped after nine calls, then accepted the revised type diagnostic in analyst-only call 10. The user raised the cumulative budget to twenty. Calls 11 and 12 produced an agent repair that completed both Oracle and PostgreSQL and passed their individual business readback checks. The combined judge still rejected two shipment timestamp differences and three extra numeric trace representations. Current status is **`halted-nonrepairable`, not verified equivalence**: no permitted structural diagnosis remains. Twelve calls were used and eight remain. Zero human-authored candidate/repair-message bytes is verified; three earlier human-authored controller revisions are separately disclosed.

The [MS89 writeup](../../../docs/milestones/MS-89/MS-89.md) contains full measurements. The [published audit](../../../docs/calibration/idempiere-analyst-repair/campaign-01/receipt.json) can be verified without a model or database call:

```powershell
python tools/publish_journey_campaign.py verify --output docs/calibration/idempiere-analyst-repair/campaign-01
python tools/publish_journey_campaign.py verify --output docs/calibration/idempiere-analyst-repair/campaign-01-recheck
python tools/publish_journey_campaign.py verify --output docs/calibration/idempiere-analyst-repair/campaign-01-paired-review
```

Type diagnostics now include model accessor/type evidence derived from the pinned upstream commit, the pinned String/Boolean accessor implementations, and separate API-call/failure-frame lines. No expected business values are exposed. The analyst must decide each diagnostic with a closed reason code; an empty or incomplete decision list is invalid. Valid rejection of every diagnostic still stops the factory. Only selected structural facts reach the builder.

For an explicitly requested diagnostic recheck, `propose-recheck` prepares a plan with the **unchanged cumulative budget**. `recheck --proposal-sha256 <hash>` archives the old stop, repins disclosed controller changes, and makes at most one analyst call. It cannot launch the builder or native execution, and refuses preparation when no approved call remains. This is not permission to increase a budget.

## Timestamp contract

[The signed decision](../contracts/oracle-date-second-precision.json) accepts second-level precision for **`adempiere.m_inout.shipdate`**, whose Oracle datatype is `DATE`. Howard Weale owns the decision; review is due **25 December 2026**. It does not apply to every date/time column. Raw fractional values and the original failing precision probe remain recorded. A datatype change or requirement for subsecond ordering triggers review. No existing MS86–MS88 receipt is rewritten, and this decision alone does not promote a broad equivalence claim.

## Retrospective MS88 audit

The [attempt audit](../../../docs/calibration/idempiere-partial-invoicing/attempt-audit/receipt.json) publishes all four original native plans, authorizations and receipts, plus the first failed transport's invocation record. The first transport never ran a judge and is marked accordingly.

```powershell
python tools/audit_journey_attempts.py verify --output docs/calibration/idempiere-partial-invoicing/attempt-audit
```

Verification checks the signatures, original plan bindings and unchanged judge hashes, business expectations and acceptance contract. It needs no database or model call. The new report does not make missing MS88 token or elapsed-time measurements knowable.
