# MS92: measure the frozen factory

Status: implementation and native observer qualification complete; scored runs are **not started**. No MS92 builder or analyst calls have been made. The run allocation and exact campaign budget still require approval.

## Experiment

Ten trials of one declaration estimate a rate for that declaration. Different conditions must not be pooled into a single success rate. The prepared design supports ten fresh trials per condition:

| Condition | Change from the baseline | Question |
| --- | --- | --- |
| Baseline | No builder-input change from MS91 | Is the result repeatable with independently observed transaction activity? |
| Procure-to-pay | Purchasing work order and trace fields; same API examples and conventions | Does the factory handle PO, receipt, vendor invoice and outbound payment without a purchasing-specific worked example? |
| Without decimal hint | Remove only the decimal-format instruction | Does removing that instruction affect first-try or eventual passes? |
| Without Boolean hint | Remove only the explicit typed Boolean signature | Can the frozen structural repair loop recover without that hint? |

The two hints are removed separately so their marginal effects can be distinguished. These are ablations of explicit hints, not removal of every relevant clue from the inherited API example or the model's training. Procure-to-pay is new to this factory's worked examples; no claim is made about the foundation model's prior knowledge.

Ten per condition means **40 trials**, not ten overall. A ten-trial procure-to-pay cohort is also prepared as a smaller first campaign. Neither proposal is authorized. Each condition uses an identical signed plan across its replicas. Trials start with a new ephemeral model session, the same initial input, an empty candidate and fresh isolated database copies. Earlier trial outcomes are not fed into later trials. A fixed-seed round-robin order interleaves the four conditions in the full proposal.

## Fixed controls and stopping rule

Each trial proposes at most five client calls: one initial builder, followed by up to two analyst/builder repair cycles. The active limit is one hour per trial. The ten-trial proposal is bounded by 50 calls and ten hours; the four-condition proposal by 200 calls and forty hours. These are maxima, not expected consumption. Cleanup and evidence publication add overhead. The remaining cohort execution allowance also bounds the next trial.

Before generation, the plan pins the implementation, private judge, comparison register, builder input, work order, native image identities, application source and CLI executable hash. The requested model is `gpt-6-astra` with high reasoning. The provider-resolved model snapshot is unavailable and is not claimed pinned. Organization API migration remains deferred; there is no GCP provisioning, and per-call dollar billing is unknown.

Complete the prespecified sample despite business failures, unsupported repairs or exhausted trial call budgets. Never replace a failed trial. Stop early for changed frozen identities, incomplete cleanup, invalid observer capture or provenance, exhausted cohort execution time, or explicit operator cancellation. Publish every remaining slot as `not-started` with the reason. No controller, judge, prompt, budget or comparison-policy amendments are permitted within the cohort.

Cancellation takes effect before the next trial; an active bounded trial finishes and cleans up. Use `python -m lightyear_calibration.repeatability cancel --cohort <folder> --reason "operator reason"`. A cancelled cohort cannot resume; a later campaign requires a new declaration.

The repair channel remains compile errors, API type mismatches and writes outside the declared footprint. Expected business values never enter it. A decimal representation failure with no supported structural diagnostic must halt; the experiment does not silently add a semantic repair channel to improve its score.

## Report every outcome

Each trial reports first-try pass, pass after repair, halt or invalid evidence, along with native attempts, repair candidates, calls, tokens, elapsed time, judge hashes and publication location. Invalid and halted trials stay in the started denominator. Planned and unstarted slots are shown separately; zero starts produces an unknown rate, not 0%.

First-try means one passing candidate and one client invocation, using the inherited lessons disclosed in [input-provenance.json](input-provenance.json). Report first-try and eventual-pass rates separately for each condition. Descriptive 95% Wilson intervals expose the small sample: even 10/10 has a lower bound of about 72%. Shared infrastructure, model-service drift and related inputs limit independence and generalization. The experiment estimates this bounded workflow's performance, not a universal factory success rate.

The per-trial publisher retains all calls, candidates, hashes, native captures and judge results, including failed attempts. A frozen-provenance failure may prevent a trusted evidence package; its invalid outcome and original local artifacts are still retained. No green receipt is substituted.

## Database observation comes first

A separately credentialed observer runs outside the generated application's writable mount. Oracle captures session identity, TX/TM locks, live transactions, rollback counters and undo statistics. PostgreSQL captures sessions, relation/transaction locks, blocker relationships and transaction completion status. The monitor allocates private PostgreSQL transaction IDs to resolve observed 32-bit IDs against a later 64-bit identity; this changes engine transaction metadata but does not write application rows.

The final disposable qualification captured native wait and rollback witnesses on both engines, with application row multisets unchanged and cleanup complete. All three unsuccessful pre-freeze instrument attempts and the final pass are preserved in [the qualification publication](../../../docs/calibration/idempiere-native-observer/README.md). They are instrument-development outcomes, **not scored factory journeys**.

Operations trials require both engine captures as well as the original native business checks. Missing native witnesses halt the journey; corrupt or incomplete observer evidence stops the cohort. The observer proves bounded wait/rollback activity involving `adempiere.c_bpartner`. It does not establish exact per-row undo attribution, crash recovery, arbitrary concurrency or load qualification. Procure-to-pay is sequential and makes no transient-lock or rollback claim.

## Private purchasing judge

The private judge checks native vendor roles, document direction, links from purchase order to receipt to vendor invoice, quantities, fractional price, discount, tax base and rounding, outbound payment, invoice settlement, inbound stock movement, allocation signs and balanced posted accounting. Synthetic unit fixtures validate the judge's refusals; they are not native purchasing results. Purchasing has not yet passed a native factory trial.

The numeric rule is exact decimal equality selected by native column type, with no tolerance and no exponent notation. Existing timestamp decisions retain their owner, review date and scope. UUID and audit-time scopes explicitly include the four purchasing footprint tables before generation; no rule is learned from a scored outcome.

## Provenance and preparation

The baseline prompt is unchanged from MS91. The public provenance register identifies the MS86 API example and locking lesson, MS88/MS89 Boolean and accounting lessons, and MS89/MS90 decimal-format lesson. Short provenance sections have been added to MS87–MS91, including the existing MS90/MS91 Word documents. This makes prior teaching visible whenever a milestone reports a first-try pass.

Observer fixes, purchasing judge construction, test fixtures and controller improvements in this change are human preparation **before** any scored declaration. They do not count as zero human preparation. After declaration, the target is zero human-authored candidate/repair-message bytes and zero controller changes.

## Operating commands

From the repository root with the project Python environment and `PYTHONPATH=src;.`:

```powershell
python -m lightyear_calibration.repeatability prepare `
  --cohort work/ms92/new-proposal --executable <pinned-codex.exe> `
  --qualification factory/idempiere/ms86-journeys/runs/journey-0876955b3bc14e65b18a530ba6882a88 `
  --variant procure-to-pay --runs-per-variant 10 --max-calls 5

# Only after explicit approval of this plan, source transfer and budget:
python -m lightyear_calibration.repeatability authorize `
  --cohort work/ms92/new-proposal --plan-sha256 <reviewed-hash> --approval <operator-approval>
python -m lightyear_calibration.repeatability run `
  --cohort work/ms92/new-proposal --executable <pinned-codex.exe>
python -m lightyear_calibration.repeatability report --cohort work/ms92/new-proposal
```

Omitting `--variant` prepares all four conditions, ten trials each. Preparing a plan neither authorizes it nor invokes the model. Do not edit any pinned source or input after preparation; prepare a new plan instead. Existing MS91 evidence and its original judge remain unchanged.
