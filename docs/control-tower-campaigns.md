# Control Tower: campaign preparation

The first operational campaign increment adds shared estate, campaign and recorded-run selection. It lets an operator inspect the proposed Oracle 26ai / AlloyDB NUMBER pilot before execution is connected. It does not create cloud resources, execute SQL, authorize spending or issue qualification receipts.

## Open the pilot

1. Start the local Control Tower using the normal project launcher.
2. Open **Estate**, select **CloudBank**, then close the estate picker.
3. Under **Campaign**, select **Oracle 26ai → AlloyDB · NUMBER pilot**.
4. In **Work queue**, inspect the proposed lanes, case bindings, environment observations and blockers.
5. **The run** says **Not run**. **Convergence** has no indexed campaign runs. Switching back to **Retained estate evidence** restores the existing estate history.

The pilot reuses the CloudBank lab context, but its scope is the independent Oracle datatype catalog. Its 20 cases and five behaviours are not CloudBank application scenarios. Discovery continues to show the estate and selected application workload; the campaign's case bindings are listed in Work queue.

## What the numbers mean

| Figure | Meaning |
| --- | --- |
| Cases planned: 20 | The proposed NUMBER pilot size. |
| Source SQL files verified: 20 | Existing source harness files match the expected catalog bindings and SQL bytes. This is file verification, not database execution. |
| Native executions: Not recorded | No admitted journal exists for this new campaign. |
| Target equivalents: Not recorded | No paired Oracle/AlloyDB result exists for this campaign. |

If source-file verification fails, the prepared count becomes **Not recorded**, rather than retaining 20. The broader catalog, previous live CloudBank runs and previous AlloyDB nonproduction qualification remain separate evidence. Neither a prepared file nor a running cloud resource establishes equivalence.

## Environment readback

From a project terminal with the Python environment and Google Cloud CLI configured:

```powershell
$env:PYTHONPATH = "src"
py -3.12 -m lightyear_workflow.campaigns collect --root .
```

On other platforms, use `python -m lightyear_workflow.campaigns collect --root .` with the package installed or `PYTHONPATH=src`.

This explicit CLI operation describes three fixed resources in project `lightyear-ms67-nonproduction`: the AlloyDB primary in `us-west1`, the Cloud SQL baseline, and the GKE control plane. It saves only resource state and observation metadata in ignored `work/campaigns/oracle26ai-alloydb-number/readiness.json`. It does not retain credentials, private addresses or raw command output. A failed resource lookup is recorded as unknown; the process exits unsuccessfully if any lookup failed.

Click **Refresh view** after collection. Browser reads never contact GCP and never renew observation timestamps. Observations become **stale after 15 minutes**. Missing, damaged, future-dated or incorrectly scoped snapshots show unavailable/invalid states. Stale observations retain their original timestamp and do not become current health claims.

The readback is unsigned operational information. Its content hash detects file damage; anyone able to replace the local file could also replace its hash. It is not engine evidence or an authorization input. Oracle runtime identity, database connectivity, workers and application health are not checked in this increment. A GKE control plane reported RUNNING does not establish worker availability.

## Selected history and human decisions

The recorded-run selector lists up to 100 indexed runs from the selected estate. Opening a run resolves its ID through that index, validates archive scope, byte count, hash and metadata, and replays the journal before rendering it. Pruned journals keep their history rows and convergence totals, but cannot display detailed events. A damaged archive shows an error and clears its figures. History listing and convergence never open the journal archives.

The current journal/recorded example is an explicitly labelled option for CloudBank retained evidence. Historical journal verification still uses the current checkout's replay contracts; incompatible old runs may become unverifiable until their original implementation is available. Selecting another estate or the new campaign does not import CloudBank results into it.

Existing normalization decisions remain bound to their configured estate authority. Approvals shown beside historical evidence represent current decision authority, not historical approval status. The new pilot cannot use that normalization authority to run databases or spend money. There is no start button in this increment.

## Hypothetical operator scenarios

**Preparing while resources are stopped.** Alex selects the NUMBER pilot and sees 20 verified source files, AlloyDB STOPPED and no native execution results. Alex can review case scope and discuss budget before resources start. The STOPPED state is an observation, not a failed test result.

**Returning tomorrow.** Sam opens yesterday's snapshot. The timestamp is unchanged and the view says stale. Refresh view alone cannot make it recent; Sam runs the read-only collector. If credentials have expired, the affected resources become unknown rather than retaining an apparent success.

**Comparing with an earlier application run.** Priya switches to retained CloudBank evidence and selects a recorded run. The engine's verified action timeline appears. Switching back to NUMBER immediately clears those figures: they belong to a different scope. A pruned run still contributes to Convergence but explains why its detailed journal is unavailable.

## Next increment: authorized paired execution

The next PR must connect a bounded engine workflow for these exact 20 cases: implement the AlloyDB harness and comparison contract, capture fresh Oracle 26ai and AlloyDB identities, check access, bind human authorization to case hashes/targets/budget/expiry, run both lanes, publish observations and comparator results, and record terminal history. It also needs cleanup and interruption handling, with explicit cloud resource policy.

The factory prepares the transformation. The engine judges observed behaviour. The Tower is where a person will accept the exact operational scope, risk and spending terms. This PR establishes the scope and evidence display needed for that decision; the campaign-specific decision and execution mechanisms come next.
