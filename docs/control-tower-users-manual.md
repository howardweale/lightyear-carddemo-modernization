# Control Tower user manual

Revision October 6, 2026. Operator review; not independent attestation.
This manual describes the current scoped Decision Console and the CardDemo z/OS
intake. It replaces the older normalization-only navigation instructions for
this workflow. The legacy Discovery viewer remains a separate read-only view.

## 1. Open the correct Tower

| Work | Scope | Where to open it |
| --- | --- | --- |
| Incoming Maintec files | `carddemo-zos` | Intake Console, normally `http://127.0.0.1:8767/` |
| B06 | `ms94-b06` | Its separately installed Console, currently port 8766 |
| Public Verify graph | Separately provisioned Verify scope | Its configured Console; no automatic activation |

Signing in to B06 does not expose CardDemo or Verify requests. Selecting a graph
or workload in Discovery does not switch the authority. Use a separate data root,
authority and journal for each engagement. Keep the current B06 service running.
The Console records decisions; it does not run Java, Docker, models or z/OS jobs.

Before delivery, have an administrator complete the
[CardDemo workspace and identity setup](mainframe/carddemo-zos-tower.md#workspace-and-identities).
Do not create another authority if one already exists. Confirm the public key
fingerprint through a trusted channel. Keep keys outside the engine-writable
intake root; keep individual credentials with their owners. An intake signing
key, Tower decision authority and an agent credential are different things.

For an already configured intake, use a separate PowerShell terminal and actual
installed paths (the example checkout path is not proof it exists):

```powershell
$IntakeRoot = 'C:\Users\howar\OneDrive\Documents\ChatGPT\lightyear-carddemo-modernization\work\carddemo-zos-intake'
Set-Location -LiteralPath $IntakeRoot
$env:PYTHONPATH = 'src;.'
$env:PYTHONUTF8 = '1'
$Python = Join-Path $IntakeRoot '.venv/Scripts/python.exe'
$TowerAuthority = 'C:\ProgramData\Lightyear\CardDemoTowerAuthority\authority.json'
if (!(Test-Path -LiteralPath $Python) -or !(Test-Path -LiteralPath $TowerAuthority)) {
    throw 'Complete the separate intake setup and use its actual paths first.'
}
& $Python -m lightyear_control_tower serve --root $IntakeRoot --authority $TowerAuthority --port 8767
```

Open the printed loopback URL. Sign in using **Individual credential**. Confirm
the scope and operator identity, then select **Work queue**. The available tabs
are Campaigns, Work queue, Catalogue, Customer workspace, Decision history and
Graph memory. CardDemo's **Customer workspace** is the read-only arrivals view.
Never paste a private key, dataset, SYSOUT or record value into any login or note.

## 2. Prepare for the arriving folder

1. Pin the reviewed intake code revision and retain it for replay. Build the
   existing Java INTCALC candidate before touching a delivery, using the
   [preparation commands](mainframe/monday-runbook.md#prepare-once-before-delivery).
2. Run the public-data rehearsal first. A passing rehearsal is not Maintec
   acceptance and not evidence of fresh z/OS execution.
3. Set `$IntakeKey`, `$IntakePublicKey` and `$Jar` to the provisioned intake key,
   independently trusted public key and built candidate JAR. Do not use a
   rehearsal key for actual acceptance. Do not overwrite existing keys.
4. Keep the delivered folder unchanged. The tool copies it into a fresh ignored
   arrival. Keep all originals, decoded values, candidate outputs and logs local.
5. Check the delivery contract: submitted JCL/procedures, complete readable job
   output, return codes, before/after dataset images, listings, notes and `run.json`
   transfer metadata. Ask for missing metadata; never infer expected values.

Metadata must identify job, steps/DDs, encoding and DCB, processing parameters,
explicit candidate timestamp and starting state. Dates in examples are not live
defaults. See the [delivery contract](mainframe/monday-runbook.md#delivery-contract)
for accepted formats and resend instructions. VB/BDW/spanned input is refused;
request supported unblocked binary RDW or fixed sequential binary exports.

## 3. Freeze the delivery and review intake acceptance

Run commands in a second PowerShell terminal in the same intake root, with the
same environment and `$Python` variable. Substitute the actual delivery path.

```powershell
$Delivery = 'C:\Users\howar\Downloads\Maintec-CardDemo'
$Received = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
$Intake = & $Python -m lightyear_mainframe intake $Delivery --key $IntakeKey --source-description "Maintec delivery received $Received" | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw 'Intake refused. Preserve the supplied folder.' }
$Arrival = Join-Path 'work/mainframe/arrivals' $Intake.arrival_id
Get-Content -LiteralPath (Join-Path $Arrival 'gaps.md')
```

Read `status` and the findings count, not only the command's exit code.
`ready-for-review` is not acceptance. Resolve missing files/DCB/encoding/return
codes with Maintec before accepting. A corrected delivery becomes a **new**
arrival, with an attribution note; never edit an existing `original/`.

In Tower:

1. Select **Customer workspace** and confirm the arrival hash and counts.
2. Select **Work queue**; open the `intake-acceptance` item for that hash.
3. Read the bound evidence and local gaps. Tower deliberately shows no records.
4. With Howard's `qualification-approver` role, choose `accepted` or `rejected`,
   complete the requested fields, then click **Record decision** once.
5. Confirm the signed event in **Decision history**. Refresh instead of submitting
   repeatedly. An accepted intake does not establish equivalence or launch a job.

The inbox is `work/control-tower/requests/carddemo-zos/` under the **data root
passed to serve**, not automatically the source-code folder. Its safe review
records live under `work/mainframe/review/`. A root mismatch is a common cause of
an empty queue; do not repair it by copying a key or using the B06 root.

## 4. Decode, observe and compare locally

Intake assigns opaque IDs, not fixed job ordering. Inspect the local
`runs/run-NNN/run.json` privately to identify the intended job and repeat run.
Use actual IDs below; these examples are not instructions to assume run 1 is INTCALC.

```powershell
$Run1 = Join-Path $Arrival 'runs/run-001'
$Run2 = Join-Path $Arrival 'runs/run-002'
& $Python -m lightyear_mainframe decode-run $Run1 --public-key $IntakePublicKey
& $Python -m lightyear_mainframe observe-run $Run1 --public-key $IntakePublicKey
& $Python -m lightyear_mainframe decode-run $Run2 --public-key $IntakePublicKey
& $Python -m lightyear_mainframe compare-runs $Run1 $Run2 --public-key $IntakePublicKey
& $Python -m lightyear_mainframe delta $Run1 --public-key $IntakePublicKey
```

Stop after any tool refusal; inspect its local evidence and preserve it. Missing
or conflicting metadata is not a reason to guess. Compare repeat runs only when
the before-images, parameters and restoration identity support the comparison.
Duplicate keys make comparison indeterminate. Counts and field paths may be
shared only under the disclosure policy; decoded values remain private.

POSTTRAN, CREASTMT and TRANREPT stop at intake/observation/comparison here. There
is no Java candidate for those jobs in this intake workflow.

## 5. Decide any normalization before sealing the verdict

A comparison may draft the narrowly supported processing-timestamp exception.
It is a proposal, not a rule. An authenticated `zos-intake` agent must submit its
exact `zos-tower-rule/1` via `propose_rule`; this is a deterministic MCP operation
and needs no model. See [the exact proposal contract](mainframe/carddemo-zos-tower.md#request-contracts-and-decisions).
A file labelled “proposed by agent” does not satisfy that authentication.

Howard opens the normalization in **Work queue**, reviews the exact run hashes,
field/pattern and still-caught mutant, then approves or rejects using the
`normalization-approver` role. Enter the real accountable owner and a future
review date. Expiry is **00:00 UTC at the start of that date**. The CardDemo owner
is `howard-weale`; reasons/notes are retained only as hash commitments. Keep the
readable explanation privately; never put record values in the form.

Obtain the signed register from `GET /api/tower/rules` using an authenticated
local client, or an explicit verified decision bundle. The operator must supply
the independently trusted Tower public key and current journal head. Retain the
approved file locally as `$Rules`; do not derive trust from the bundle itself.
No rules means exact comparison. The old normalization ledger is never applied.

**Choose the verdict path before running it.** Existing verdicts are immutable.
Do not first run an exact verdict and then overwrite it with an approved one.
If a proposal is pending, complete review before the first verdict, or deliberately
retain an exact divergent verdict. Later changes need a new admitted run, with
all earlier outcomes preserved.

## 6. Run INTCALC and replay

Use the unchanged built JAR and explicit processing clock parameters from the
submitted metadata/notes. Hidden after-images must never supply candidate inputs.

```powershell
& $Python -m lightyear_mainframe prepare-intcalc-inputs $Run1 --public-key $IntakePublicKey --key $IntakeKey
& $Python -m lightyear_mainframe run-intcalc $Run1 --jar $Jar --public-key $IntakePublicKey --key $IntakeKey
# Choose ONE first-verdict command:
& $Python -m lightyear_mainframe verdict-intcalc $Run1 --public-key $IntakePublicKey --key $IntakeKey
# OR, only with reviewed rules and independently established trust:
# & $Python -m lightyear_mainframe verdict-intcalc $Run1 --public-key $IntakePublicKey --key $IntakeKey --normalizations $Rules --tower-public-key $TowerPublicKey --tower-head $TrustedTowerHead
& $Python -m lightyear_mainframe replay-intcalc $Run1 --public-key $IntakePublicKey
# For the approved-rule path, also supply --tower-public-key $TowerPublicKey to replay.
```

Check each exit code before proceeding. Java runs at most five minutes. `equivalent`,
`divergent` and `indeterminate` are honest measurement outcomes. A successful CLI
exit is not an equivalent verdict. Offline replay recomputes comparison from
retained bytes/signatures; it does not rerun Java or observe current z/OS state.
A historical approved proof establishes authorization at its recorded head/time.

## 7. Disposition and release are separate decisions

A divergent verdict produces a `difference-disposition` request. Howard's
workload-scoped `business-owner` role can record `defect`, `intended-change` or
`needs-information`. That decision changes neither the verdict nor the rule.
Investigate any needed implementation/rule change separately.

To share, select only the closed safe intake/difference review JSON files:

```powershell
& $Python -m lightyear_mainframe request-evidence-release --members $IntakeReviewFile $DifferenceReviewFile
```

Open the request in **Work queue**. A distinct customer `customer-sponsor` and
Howard as `campaign-authorizer` must each approve the exact bundle. One person
cannot fill both slots. After both approvals the authenticated export endpoint
`GET /api/tower/export?id=<request-id>` supplies a signed no-values bundle.
Save it locally and verify it before sharing:

```powershell
& $Python -m lightyear_control_tower verify-export --archive $ExportFile --trusted-public-key $TowerPublicKey
```

The bundle is not a raw archive release. Never upload arrival directories,
originals, records, logs, private keys or candidate outputs. Before any commit:

```powershell
git check-ignore -- (Join-Path $Arrival 'manifest.json')
git status --short -- work/mainframe/arrivals
git diff --cached --name-only
```

Expect ignored arrival data, no arrival status entries and only explicitly
reviewed safe files staged. Signed evidence is not automatically safe to publish.

## 8. Graph context and graph memory

Verify graph context is limited to the approved **public CardDemo reference**.
It is not an interface to Maintec files. Confidential mode redacts all literals;
field mode requires the separate public-overlap review. Neither allows a
protected-value leak. The graph review card lists required `source-literal:<hash>`
acknowledgments; approval without every exact token is refused. Acknowledge only
after inspecting the public source. Tokens are evidence bindings, not a suggested
business justification.

Set the review date with enough margin for the entire session. On expiry the
judge refuses submissions and graph tools disappear. A newly rejected decision
requires distributing a fresh verified head/proof; an offline archived proof
cannot detect later revocation automatically. Never edit signed records to refresh
approval. See [activation prerequisites](verify/graph-activation-checklist.md).

**Graph memory** contains separately reviewed annotations, not intake acceptance.
An annotation or “verified” label cannot override a raw comparison or make private
customer data eligible for a public projection. The optional toolkit currently
has 16 tools when approved (six graph tools), versus the original ten when off.
No model comparison or live model call is approved by a Tower graph decision.

## 9. If something looks wrong

| Symptom | Check / next action |
| --- | --- |
| Logged in, empty queue | Confirm scope, root passed to serve, request folder, filter and role. B06 credentials do not authorize CardDemo. |
| Invalid request | Preserve it. Inspect bound hashes and the service account's read access to the exact public review files. Do not broaden parent-folder ACLs or bypass path checks. |
| Read-only card | Check the required role and authenticated agent proposal. An agent never gets approving roles. |
| Stale decision conflict | Refresh and reopen the item; reassess changed evidence. Do not replay a stale POST. |
| Three repeated decisions | Inspect Decision history: repeated decisions for one subject are not three separately authorized runs. Latest applicable signed decision governs. |
| No graph tools | Pending/rejected/expired approval, missing trust or hash mismatch means baseline tools only. Do not bypass the gate. |
| Different/unknown dataset format | Request a corrected delivery; preserve the original. |
| Equivalence changed after rule review | Preserve both outcomes and explain distinct run/rule bindings; never rewrite history. |

For complete contracts see [CardDemo Tower](mainframe/carddemo-zos-tower.md),
[the intake runbook](mainframe/monday-runbook.md), and
[Decision Console administration](control-tower-decision-console.md).
