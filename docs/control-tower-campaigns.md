# Control Tower: authorize and observe a paired campaign

Control Tower can authorize the bounded Oracle 26ai / AlloyDB NUMBER pilot and observe its detached engine. Shared estate, campaign and run selection keep these datatype cases separate from CloudBank application evidence. Opening or refreshing the UI never starts resources: execution requires a separately authenticated campaign authorization.

## Open the pilot

1. Start the local Control Tower using the normal project launcher.
2. Open **Estate**, select **CloudBank**, then close the estate picker.
3. Under **Campaign**, select **Oracle 26ai → AlloyDB · NUMBER pilot**.
4. In **Work queue**, inspect the proposed lanes, case bindings, environment observations and blockers.
5. Before authorization, **The run** says **Not run**. After authorization it polls the engine journal every three seconds while visible. **Convergence** lists signed terminal summaries. Switching back to **Retained estate evidence** restores the existing estate history.

The pilot reuses the CloudBank lab context, but its scope is the independent Oracle datatype catalog. Its 20 cases and five behaviours are not CloudBank application scenarios. Discovery continues to show the estate and selected application workload; the campaign's case bindings are listed in Work queue.

## What the numbers mean

| Figure | Meaning |
| --- | --- |
| Cases planned: 20 | The proposed NUMBER pilot size. |
| Source SQL files verified: 20 | Existing source harness files match the expected catalog bindings and SQL bytes. This is file verification, not database execution. |
| Oracle observations | Completed source case observations from the selected run; inspect the evidence class. |
| AlloyDB observations | Completed target case observations from the selected run. |
| Equivalent pairs | Both lanes satisfy independent expectations and the approved comparison contract. Forty lane executions form twenty pairs. |

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

The readback is unsigned operational information. Its content hash detects file damage; anyone able to replace the local file could also replace its hash. It is not engine evidence or an authorization input. The engine separately checks fresh database identities and connectivity during execution. A GKE control plane reported RUNNING does not establish worker availability.

## Selected history and human decisions

The recorded-run selector lists up to 100 indexed runs from the selected estate. Opening a run resolves its ID through that index, validates archive scope, byte count, hash and metadata, and replays the journal before rendering it. Pruned journals keep their history rows and convergence totals, but cannot display detailed events. A damaged archive shows an error and clears its figures. History listing and convergence never open the journal archives.

The current journal/recorded example is an explicitly labelled option for CloudBank retained evidence. Historical journal verification still uses the current checkout's replay contracts; incompatible old runs may become unverifiable until their original implementation is available. Selecting another estate or the new campaign does not import CloudBank results into it.

Existing normalization decisions remain bound to their configured estate authority. Approvals shown beside historical evidence represent current decision authority, not historical approval status. The pilot uses its own campaign operator authority; normalization approval cannot authorize database execution or spending.

## Hypothetical operator scenarios

**Preparing while resources are stopped.** Alex selects the NUMBER pilot and sees 20 verified source files, AlloyDB STOPPED and no native execution results. Alex can review case scope and discuss budget before resources start. The STOPPED state is an observation, not a failed test result.

**Returning tomorrow.** Sam opens yesterday's snapshot. The timestamp is unchanged and the view says stale. Refresh view alone cannot make it recent; Sam runs the read-only collector. If credentials have expired, the affected resources become unknown rather than retaining an apparent success.

**Comparing with an earlier application run.** Priya switches to retained CloudBank evidence and selects a recorded run. The engine's verified action timeline appears. Switching back to NUMBER immediately clears those figures: they belong to a different scope. A pruned run still contributes to Convergence but explains why its detailed journal is unavailable.

## Authorize and observe execution

Under **Authorize this campaign**, review the exact plan, enter the separate campaign credential and a reason, accept the terms, then select **Authorize and start paired run**. The plan binds both SQL hashes per case, implementation hashes, official Oracle image digest, target resources, comparison policy, runtime limit and estimated budget. An authorization must start within ten minutes. Duplicate requests retain one authorization and launch at most one worker.

The run opens automatically. It shows environment preparation, database identities, source observations, target observations, comparisons and cleanup. Expand a case to see raw values and the comparison result. Use **Refresh view** when another session starts a run. Closing the browser or web server does not stop the detached engine; keep the controller laptop awake and connected until cleanup is confirmed.

Expand **Signed campaign authorization** in The run to inspect the recorded operator, reason, timestamp, exact plan and signature. These are the terms bound to that selected run, even if the currently proposed plan has since changed. No operator credential or private signing key is displayed.

| Status | Meaning |
| --- | --- |
| `passed-bounded-native` | All pairs in the authorized plan passed with native identities/observations, no execution error, and confirmed cleanup. |
| `passed-simulated` | The workflow passed using simulated observations; never native evidence. |
| `failed` | Preparation, execution or a comparison failed. Retained observations remain inspectable. |
| `cleanup-required` | Resource restoration was not confirmed; recover before another launch. |
| `interrupted-or-unobserved` | No event for two minutes. A long cloud operation may still be running; this is not proof of termination. |

Oracle `-1438` and PostgreSQL SQLSTATE `22003` remain different raw codes. Only their reviewed numeric-precision-overflow class is mapped. Other selected values and nulls must match exactly and satisfy independent expectations. Target SQL explicitly renders the required dot/comma decimal separator for NLS probes; the comparator does not rewrite observations.

These results establish bounded NUMBER behaviour under this transformation. They do not establish full Oracle compatibility, application equivalence, production readiness or ten-dimension platform qualification. Repeated cases do not add distinct catalog coverage. This campaign's receipt is not automatically admitted into the separate native-catalog coverage gate.

Identity metadata can also be unknown: the paired pilot leaves isolation level null because Oracle's `USERENV` context does not expose that parameter. The separate wallet-based catalog runner explicitly configures READ COMMITTED and labels that value as accepted session configuration, rather than a metadata readback. See [Oracle's SYS_CONTEXT parameter reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SYS_CONTEXT.html).

## Provision the local lab

Install the project with Control Tower dependencies and configure the existing Google Cloud CLI account. Provision a separate authority:

```powershell
$env:PYTHONPATH = "src"
py -3.12 -m lightyear_workflow.campaign_service init-operator --operator-id alice --operator-name "Alice Example"
```

Provisioning reports the credential-file location and authorizes no run. Protect its private key and credential with operating-system access controls. Do not replace an existing authority: its public key verifies earlier evidence. A delegated agent must identify itself accurately, for example “Codex acting on user authorization,” and record the user's approval in the reason. It must not claim that the user clicked the button. Anyone controlling the local authority files controls its signatures; these are not independent external attestations.

Create ignored `work/campaigns/oracle26ai-alloydb-number/profile.json` with these exact fields, replacing the placeholder with a verified official **amd64 Oracle 26ai Free** manifest digest:

```json
{
  "oracle_image": "container-registry.oracle.com/database/free@sha256:<64 hexadecimal characters>",
  "budget_usd": 10,
  "estimated_hourly_usd": 2,
  "max_seconds": 3600,
  "runner_zone": "us-west1-a"
}
```

The $2/hour value is a conservative planning allowance for this lab, not a live pricing quote. Review current GCP pricing before adapting the plan. The engine rejects mutable image tags and checks fresh runtime identities.

The AlloyDB connection uses the private endpoint from a fresh read of the fixed GCP instance resource, and verifies the SQL version, database and user. Its internal server socket address is retained as a hash and a separate comparison field; it is not assumed to equal the managed connection endpoint.

Review and serve:

```powershell
py -3.12 -m lightyear_workflow.campaign_service review --root .
py -3.12 -m lightyear_knowledge_graph serve --port 8766 --no-browser
```

Open `http://127.0.0.1:8766/`. Do not change bound implementation or SQL while executing.

## Resources, spending and recovery

The adapter is fixed to project `lightyear-ms67-nonproduction`, region `us-west1`, AlloyDB cluster `cloudbank-ms71-alloydb`, primary `primary`, and the existing `cloudbank-ms67` subnet. It refuses to take over an already-running primary. Cloud SQL and GKE workers remain untouched.

It resumes AlloyDB and creates one owned `e2-standard-2` runner with a 20 GB boot disk, no service account and no cloud scopes. A temporary firewall permits SSH only from the Google IAP range to this runner. Its ephemeral external address supports official image/package downloads; Oracle publishes no container ports. The controller sends the existing AlloyDB credential only over SSH stdin, never command arguments or journals. Synthetic PostgreSQL expressions run inside transactions that roll back.

Cleanup deletes the labelled runner and scoped firewall, restores AlloyDB to STOPPED, and records the outcome. Each cleanup operation is attempted independently. Foreign resources are not adopted or deleted.

The active-runtime limit is 10–60 minutes, and the configured estimated cost must fit the budget. **The dollar amount is an estimate, not a guaranteed billing cap.** Cleanup can take extra time; existing storage/backups still incur charges. The VM has a maximum lifetime with automatic deletion. That safeguard does not stop AlloyDB if the controller laptop loses power.

A crash never triggers automatic SQL replay. An uncertain dispatch retains its authorization and blocks a new launch. After the original worker has stopped, recover using its exact displayed run ID:

```powershell
py -3.12 -m lightyear_workflow.campaign_engine recover --root . --run-id number-<32 hexadecimal characters>
```

Recovery takes the exclusive writer lock, verifies signed resource ownership, and retries cleanup only. It records a separate signed result without rewriting the original verdict. It refuses while the original worker owns the journal; do not remove that lock or fabricate completion. Restore credentials/connectivity before retrying failed recovery. Check GCP directly if the controller cannot be recovered.

Convergence reads signed terminal summaries without opening journals. Pruned details show unavailable instead of “not run”; damaged evidence clears figures. Historical replay uses the checked-out comparison contract, so preserve the bound implementation with exported evidence.

## Additional hypothetical scenarios

**A first live run.** Alex approves twenty cases and the $10 estimated allowance. Source observations rise before target observations; equivalent pairs stay zero until comparison actually occurs. Alex waits for a terminal verdict and confirmed cleanup.

**A mismatch.** One target value differs. Both raw values remain visible, the engine reports failure, and cleanup still runs. A revised transformation requires another reviewed plan and authorization.

**A closed browser.** Sam reopens the Tower and selects the same campaign/run. The detached worker continued; no second execution is launched.

**A laptop outage.** The VM expires, but AlloyDB may remain on. Sam restores connectivity and invokes recovery. The original failed/interrupted verdict remains, alongside later cleanup confirmation.

**A simulated demonstration.** Priya sees twenty matching pairs labelled `passed-simulated`. She can evaluate the workflow but cannot call it native evidence; the weaker lane prevents that promotion.

The factory prepares the transformation. The engine judges observed behaviour. The Tower records the person's acceptance of operational scope, risk and spending terms and exposes the resulting evidence.

## The 100-pair campaign

Select **CloudBank → Oracle 26ai → AlloyDB · 100 datatype pairs**. This is a
separate campaign from the NUMBER pilot; its run selector and Convergence show
only its own runs. The operator authority and resource lock are shared, so an
active or unclean pilot blocks the larger campaign too.

The proposed scope is NUMBER, CHAR, VARCHAR2, DATE and TIMESTAMP, 20 cases each:
100 catalog case pairs, 200 lane executions and 25 bounded behaviours. NUMBER
is a baseline rerun. These case dimensions exercise reviewed synthetic probes;
they are not a claim to cover every value, collation or time-zone behaviour.
See the [SQL contract and mappings](../data-modernization/oracle-paired-core100/README.md).

Prepare `work/campaigns/oracle26ai-alloydb-core100/profile.json` using the profile
schema above. Review it with:

```powershell
py -3.12 -m lightyear_workflow.campaign_service review --root . --campaign-id oracle26ai-alloydb-core100
```

The existing pilot approval does not authorize this expanded plan. Review the
100-case terms, enter the reason and accept the scope and spending estimate.
Changing campaign clears unfinished authorization fields. Refreshing the same
campaign preserves them. The engine rejects a plan changed since review.

In **The run**, counters use 100 as the denominator. **Family progress** shows
source observations, target observations, comparisons, matches, differences,
blocked cases and pending cases. Pending means comparison has not happened
while the run is active. Blocked means a terminal run ended before those
comparisons. A comparison mismatch does not discard other families; a client
execution failure stops further SQL and proceeds to cleanup. A later retry is
a newly authorized campaign, never automatic replay.

Each family has a separate signed journal anchored to a checkpoint in the
campaign journal. No journal needs more than 256 events. Expand **Case evidence**
for observations or the timeline for verified events. **Convergence** retains
the signed family summaries when detailed journals are pruned; the detailed
view and catalog overlay then say unavailable rather than manufacturing counts.

The work queue's **Catalog coverage across verified native runs** is an
aggregate, separate from the selected run. It verifies published pilot evidence
and locally installed authority evidence, replays comparisons and binds SQL to
the current supported probe contract. NUMBER's earlier 20 cases plus a passing
100-case run yield **100 unique paired cases**, not 120. A later native mismatch
supersedes the earlier pass for that case; simulated runs cannot inflate or
replace native coverage. Missing or corrupt evidence makes counts unknown.

This overlay reports 26ai paired-probe coverage. The older 4,000-execution native
gate requires 2,000 cases on Oracle 19c plus 2,000 on Oracle 26ai under a different
wallet receipt contract. The overlay does not rewrite it, and AlloyDB is not a
second Oracle lane. Neither report establishes full platform qualification.
The existing [CloudBank AlloyDB nonproduction qualification](cloudbank-alloydb-platform-qualification.md)
remains a separate retained result. This datatype campaign neither revokes it
nor extends it to broader Oracle semantics or production workloads.

Read the same aggregate without cloud calls:

```powershell
py -3.12 -m lightyear_data.oracle_paired_coverage --root .
```

**Hypothetical: CHAR loses padding.** Alex sees NUMBER 20 matched, CHAR 19 matched
and one different. The raw target string is shorter. The other families can
finish; the overall run fails and cleanup is attempted. Alex reviews the
transformation rather than approving a comparator that silently strips spaces.

**Hypothetical: connection lost during DATE.** Sam sees completed earlier
families and a partial DATE family. The remaining comparisons become blocked
when the run terminates. Sam confirms cleanup (or invokes recovery with the
displayed `core100-…` run ID) before authorizing another run. Recovery retries
cleanup only and retains the original failure.

**Hypothetical: 100 green simulated pairs.** Priya can evaluate progress and
inspection in the browser. The run explicitly says `passed-simulated`, and its
100 matches add zero native catalog coverage.

## The 260-pair datatype campaign

Select **CloudBank → Oracle 26ai → AlloyDB · 260 datatype pairs**. The campaign
includes the previous 100 cases plus 160 new cases: BINARY_FLOAT, BINARY_DOUBLE,
NCHAR, RAW, TIMESTAMP WITH TIME ZONE, TIMESTAMP WITH LOCAL TIME ZONE, INTERVAL
YEAR TO MONTH and INTERVAL DAY TO SECOND. Each family contributes 20 pairs.
Review the [bounded SQL contract](../data-modernization/oracle-paired-types260/README.md)
before interpreting the coverage claim.

Use the separate `oracle26ai-alloydb-types260` profile and campaign ID when
reviewing or authorizing. Its 260-case scope requires its own authorization;
earlier pilot approvals cannot launch it. The same authority and resource lock
prevent overlapping campaigns. The run shows four counters out of 260, thirteen
family rows, raw case observations, signed events and cleanup. Convergence shows
this campaign's signed history. For cleanup recovery, use the exact displayed
`types260-…` run ID with the recovery command above.

**Hypothetical: one floating bit differs.** Morgan sees 259 equivalent pairs and
one mismatch. The float's raw hex differs; the comparator does not round the
values into agreement. The run fails while retaining every family's result.

**Hypothetical: time-zone probes pass.** Lee can claim that the selected UTC
instants and session displays matched. Lee cannot claim preservation of every
original region name or daylight-saving transition: those probes are not in
this contract.

**Hypothetical: interruption after the original five families.** Jordan sees
100 matches and 160 blocked comparisons. Cleanup proceeds; remaining pairs are
not counted as failures of database semantics or as passes. A fresh authorization
is needed to run again. The aggregate deduplicates these baseline case IDs.

**Hypothetical: all 260 pass natively.** The selected run shows 260/260 and the
catalog aggregate shows 260 unique equivalent cases / 65 bounded behaviours,
not 380 by adding the overlapping campaigns. This does not establish additional
platform qualification. A green simulation contributes no native coverage.

The [published native 260-pair result](receipts/oracle26ai-alloydb-types260-20260917/README.md)
contains a successful 260/260 run and the earlier failed interval-harness attempt.
Both retain their authorizations, observations and cleanup evidence. The combined
planning estimate was $2.94 against the approved additional $10 allowance;
the estimate excludes ongoing storage and is not a measured bill.
