# Control Tower user manual

Revision November 5, 2026. Operator guide; not independent attestation.

Changelog: replaces the obsolete 8765 description; adds Discovery navigation,
reference-estate licences and empty-state guidance; reconciles Factory backfill,
APPL overlap, threshold evidence, T2 constants and ordered-release prerequisites.
The numbered intake sections remain stable for existing links.

The Control Tower front page is `http://127.0.0.1:8765/`, opened by
`./graph-explorer.sh --no-browser`. Its workspaces are **Work queue**, **The run**,
**Convergence** and **Discovery**, with **Campaigns and decisions** and
**Sign in to decide** in the navigation. Discovery is one workspace of this
front page, not a separate legacy product. The scoped Decision Consoles below
remain distinct authorities. Source baseline: `57a80c41513c4206205b010fe675e9a021144c12`.

> **Release status.** Factory decisions, Programs, Business rules, Status and
> Unresolved are in main; the October 11 deliveries and October 12 port correction
> are no longer pending merge. See commits [1e3d4c04](https://github.com/howardweale/lightyear-carddemo-modernization/commit/1e3d4c04),
> [4c9144bd](https://github.com/howardweale/lightyear-carddemo-modernization/commit/4c9144bd),
> [903c8323](https://github.com/howardweale/lightyear-carddemo-modernization/commit/903c8323)
> and [643adda8](https://github.com/howardweale/lightyear-carddemo-modernization/commit/643adda8).
> Code availability is separate from local authority, evidence-index trust,
> current journal trust, effective decisions and release prerequisites.
> The historical seven-record backfill has later evidence corrections (section 13);
> it does not establish today's installation or permission for another run.
> Not yet established by this guide: current production signing interoperability,
> native qualification, customer equivalence or release authority.

## 1. Open the correct Tower

| Work | Scope | Where to open it |
| --- | --- | --- |
| Estate context, run history and Discovery | Selected reference estate; local decision service only when configured | Control Tower front page, `http://127.0.0.1:8765/` |
| Incoming Maintec files | `carddemo-zos` | Intake Console, normally `http://127.0.0.1:8767/` |
| B06 (documentation only) | `ms94-b06` | Port 8768 is reserved; do not start, stop or alter it for this guide |
| Public Verify graph | Separately provisioned Verify scope | Its configured Console; no automatic activation |
| Factory evidence: programs, scenarios, mutation, twin, keep-or-fix, model-spend approvals | `factory` | Factory Console, port 8769. See section 10 |

Signing in to B06 does not expose CardDemo or Verify requests. Selecting a graph
or workload in Discovery does not switch the authority. Use a separate data root,
authority and journal for each engagement. Reuse the existing Factory root;
do not create a second Factory root or use a OneDrive checkout for run-bound work.
The Console records decisions; it does not run Java, Docker, models or z/OS jobs.

On 8765, the server enables its decision service when
`work/control-tower/authority.json` exists, or when an explicit `--decision-config`
names an existing authority. It requires loopback binding and individual sign-in.
Without authority, **Sign in to decide** is disabled and the queue explains that
the decision service is not configured. The **Campaigns and decisions** link
points to the standalone console on 8766 by default; it does not provision that
service or replace the explicitly scoped 8767/8769 consoles. See
[front-page server](../src/lightyear_knowledge_graph/explorer.py) and
[navigation markup](../knowledge/viewer/index.html).

Before delivery, have an administrator complete the
[CardDemo workspace and identity setup](mainframe/carddemo-zos-tower.md#workspace-and-identities).
Do not create another authority if one already exists. Confirm the public key
fingerprint through a trusted channel. Keep keys outside the engine-writable
intake root; keep individual credentials with their owners. An intake signing
key, Tower decision authority and an agent credential are different things.

For an already configured intake, use a separate PowerShell terminal and actual
installed paths (the example checkout path is not proof it exists):

```powershell
$IntakeRoot = '<existing-reviewed-local-intake-root>'
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
the scope and operator identity, then select **Work queue**. The tabs are
Campaigns, Work queue, Catalogue, Customer workspace, Decision history, Graph
memory and Business rules. In the CardDemo intake scope, Graph memory and Business
rules are deliberately empty: that scope accepts only intake acceptance,
normalization, difference disposition and evidence release. The Factory scope adds
Programs, Status and Unresolved (section 10). CardDemo's **Customer workspace**
is the read-only arrivals view.
Never paste a private key, dataset, SYSOUT or record value into any login or note.

## 1A. Explore the estate in Discovery

### Header and evidence boundary

Open **Estate** to choose **Company** and **Business problem**. The companies are
**CardDemo Reference Estate**, **iDempiere Reference Estate (Large)** and
**CloudBank Reference Estate**. They are reference evidence, not customer estates.
The header then narrows **Workload**, **Technology scope** and **Operator lens**.
CardDemo's account-and-card-servicing context offers interest calculation and
CICS/VSAM account view; the workload choices depend on the estate and problem.

Technology scope offers **Unified estate**, **Mainframe** and **Database
modernization**. It changes emphasis without deleting explanatory cross-platform
dependencies. **SAP estate · planned** is disabled. Operator lens offers
**Dependencies**, **Data flow**, **Modernization**, **Runtime evidence** and
**Qualification evidence**. **Security vulnerabilities · planned** is disabled.

Read **DISCOVERY VIEW · NOT LIVE EQUIVALENCE** before interpreting the graph.
The snapshot/entities/relationships/rules/extensions strip describes the selected
projection. Counts are snapshot-specific, not production activity or equivalence
measurements; the separate live graph binding may include additional graph nodes.
The projection combines discovery and development evidence without promoting a
live-mainframe or production claim.

### Left rail and readable graph

The current CardDemo **Perspective** presets are:

- INTCALC workload; Monthly-interest rule; INTCALC job lineage.
- Account data contract; Final-account behavior; AUTHFRDS data lineage.
- CICS/VSAM account view; IMS authorization purge; HLASM date service.
- PL/I authorization-risk lineage.

**Depth** selects 1–4 hops. **Implementer** applies the public/implementer evidence
boundary. **Verifier** opens a session-token challenge before verifier-audience
evidence, including verifier-private artifacts and holdout output, becomes
available. Selecting the label alone does not grant access. Keep that token out
of documents and screenshots; this guide requires no verifier unlock.
**Search selected estate** finds programs, fields and rules; `/` focuses search.

**Evidence planes** shows the Knowledge Graph identity and Factory, Portfolio,
Recovery, Quality, Memory, Data, Runtime and Audit signals. **unavailable · no
signal** means the corresponding evidence source has no observed signal in this
view. It does not mean a successful check, zero defects or zero activity, and
does not erase separately retained snapshots. A live graph connection alone
does not establish live evidence in every plane.

The readable limit is **70 nodes**. Above it, the UI may collapse implementation
packages automatically when that brings the selection under the limit. Otherwise
the reduction dialog offers **Collapse implementation packages**, **Rules and
proof only**, **Legacy ↔ modern paths**, or **Render all nodes anyway**. Use
**Restore selection** to undo a reduction and **Fit** to frame the graph. Rendering
all nodes is a picture option, not additional evidence. A narrower perspective,
lower depth or focused entity is usually easier to read.

### Inspect, Trace and Ask

**Inspect** shows an entity's properties, source-linked evidence, **Runtime
truth**, and incoming/outgoing relationships. Select a relationship to inspect
its own evidence. **STATIC ONLY**, zero observations and **No runtime evidence
attached** must remain static claims; a displayed trust percentage is not a
qualification verdict. **Focus subgraph** and **Set as trace start** operate on
the selected entity.

**Trace** distinguishes **Directed flow**, following source-to-target edges,
from **Related evidence**, which may traverse either direction and is not a
transaction path. The current proven example chips are:

| Example | What the static path means |
| --- | --- |
| COBOL → DB2 update | COPAUS2C paragraph containment, SQL issuance and WRITES_TABLE to CARDDEMO.AUTHFRDS |
| COBOL → IMS dependency | CBPAUP0C through PSB/PCB to DBD; dependency alone does not prove an update |
| COBOL → IMS delete | CBPAUP0C DLI DLET to the PSB-bound PAUTDTL1 segment |
| PL/I → DB2 read | ACCTPL1 SQL read path to CARDDEMO.AUTHFRDS |
| PL/I → DB2 write · reference | AUTHUPD1 non-customer reference fixture and its UPDATE extraction |

A result reports hops, platform sequence and static-evidence limits. Missing
fragments, integration edges or mutation edges produce an evidence gap, not an
invented route. Oracle nodes in a composite projection do not by themselves
establish an Oracle-to-IMS update; SAP ASE and other absent paths need their own
governed fragments and integration evidence. Read the coverage badges and the
result's actual boundary, not just a platform name.

**Ask** offers **Grounded local**, a deterministic answer assembled from visible
graph facts, and **OpenAI high-quality**, which makes model calls and requires
`OPENAI_API_KEY`. **Do not use OpenAI mode without Howard's explicit spend
approval.** The UI disables it without the key, but selects it automatically when
available; check the provider before submitting a question. A configured key is
not spend permission. Answers remain limited to the selected audience and
retrieved evidence. No key belongs in this guide or a screenshot.

### Alert and empty states

The header **1 alert · The latest release promotion decision is blocked** comes
from the audit trust posture. The inspected posture has open gaps
`hardened-execution-enforcement` and `mainframe-equivalence`. It is a release
promotion block, not proof that every graph relationship is wrong. The policy
requires the corresponding execution-enforcement and mainframe evidence; hiding
an alert or selecting another lens cannot close a gap.
Open the **Audit** evidence plane to inspect this posture. The alert button itself
opens the read-only Recovery panel; it does not clear the release-promotion block.
The Audit panel labels its scope **GLOBAL EVIDENCE PLANE · NOT ESTATE-FILTERED**.

With no CardDemo run adapter, **The run** says **No run adapter is recorded for
this estate**. **Convergence** says **No completed runs recorded yet**, with the
explicit limit that no indexed runs is not a measurement of zero activity.
The run selector may instead report history unavailable or a fetch failure;
no history totals should be inferred from that error. **Work queue** without
authority says the decision service is not configured and disables sign-in.
Its zero badge and empty normalization list do not close scientific reviews.
Historical proof runs belong to the headless engine; viewing this page does not
start execution or issue a qualification receipt.

Source references: [viewer controls](../knowledge/viewer/index.html),
[viewer behavior](../knowledge/viewer/app.js),
[operator context](../knowledge/viewer/context.js),
[audit policy](../src/lightyear_audit/policy.py), and
[licence scope](../LICENSES/README.md). The [front page](control-tower-screenshots/front-page.jpg),
[estate selector](control-tower-screenshots/estate-selector.jpg),
[Inspect](control-tower-screenshots/discovery-inspect.jpg),
[Trace](control-tower-screenshots/discovery-trace.jpg),
[Ask](control-tower-screenshots/discovery-ask.jpg),
[audit posture](control-tower-screenshots/audit-posture.jpg),
[The run](control-tower-screenshots/run-empty.jpg) and
[Convergence](control-tower-screenshots/convergence-empty.jpg) screenshots show a
local reference-only view without operator authority, not a production run.

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

The governed Verify graph adapter is limited to **public CardDemo reference**
context. This adapter is distinct from the three-estate Discovery selector in
section 1A; selecting an estate there does not expand a Verify grant. Neither
interface admits private customer files. Confidential mode redacts all literals;
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
| Programs page shows "pending" after you approved something | Check Decision history for the signed event. The page reads signed decisions and the latest receipts only; a decision given in chat does not count. |
| Equivalence arguments marked "invalidated" | A keep-or-fix decision they depend on changed (section 12). Re-disposition them; the threshold check refuses until you do. |
| Model-spend request refused at dispatch | The plan hash in the request must equal the hash you approved. Any amendment is a new request. |
| Factory tab empty | You are in the CardDemo intake or B06 scope. Factory evidence lives only in the `factory` scope. |



## 10. Factory scope: open it and find your way

The Factory scope shows the public development evidence the factory produces for
each converted program, and records the decisions that govern it. It uses only
public CardDemo sources, public data and generated scenarios. It never shows
Maintec arrivals or customer values; those stay in the CardDemo intake scope.

```powershell
& $Python -m lightyear_control_tower serve --root $FactoryRoot --authority $FactoryAuthority --port 8769
```

Use the Factory data root and authority provisioned for it, never the intake or
B06 root. Sign in with your individual credential. The Factory tabs are:

| Tab | What it is for |
| --- | --- |
| **Programs** | One page per converted program: is it releasable, and why (section 11) |
| **Status** | Pinned program evidence, historical campaign states and the current scoped queue; read its source commit and time |
| **Unresolved** | Recorded differences, twin limits, survivors and reviews in the scoped evidence; not an exhaustive inventory of unknown gaps |
| **Work queue** | Factory decisions waiting on you (section 12) |
| **Business rules** | Rules with evidence strength and scenario adequacy |
| **Decision history** | Events in this Factory journal, including any backfill actually present there; dated repository narratives alone do not populate it |

## 11. Programs: read a program's evidence

The refreshed [INTCALC](control-tower-screenshots/INTCALC.png),
[POSTTRAN](control-tower-screenshots/POSTTRAN.png),
[Status](control-tower-screenshots/status.png) and
[Unresolved](control-tower-screenshots/unresolved.png) images use the existing
disposable public browser fixture. Their historical evidence values illustrate
the interface; they are not new run measurements or a live authority journal.

Select **Programs**, then a program, for example POSTTRAN (CBTRN02C). The page
header distinguishes the experiment head from the imported evidence commit.
Source hashes and compiler scope appear in evidence panels. The banner states
**Not releasable** for the current provisional programs; the checklist lists
each criterion as met, pending, failed or not reported. A pending decision is not
a measured failure, and a passing rate is not release approval.

| Panel | What to check |
| --- | --- |
| **Releasability checklist** | Each threshold criterion with its measured value. Expand the source links to inspect the display policy and signed overlays. The historical CI policy is not an effective Factory approval. |
| **Scenarios** | Business-logic and I/O-handling coverage, separately; outcomes added by fault injection; accepted exceptions; listed gaps with reasons |
| **Mutation** | Raw kills (failure and divergent), argued equivalents grouped by class, survivors, compiler refusals; each class shows how it is resolved: compiler-proven, class proof or individual review |
| **Answer key** | `oracle_class` (for example `executable-twin (provisional)`), z/OS confirmation, and the twin limits that apply to this program |
| **Keep or fix** | Legacy behaviours the conversion must reproduce, with your decision and any equivalence arguments that depend on it |

Raw figures are always shown beside figures after exclusions. A percentage is
never shown without its denominator. Nothing on this page changes evidence;
decisions are made only in **Work queue**.

## 12. Factory decisions

Factory decision consumers use their isolated journal authority and require
cryptographic proof bound to exact hashes and current external trust. A chat
instruction alone is not a substitute for a consumer's required Tower proof.

| Decision | What you approve | Role |
| --- | --- | --- |
| `scenario-threshold-approval` | A threshold policy version (criteria, minimum set sizes, what may be excluded) | `qualification-approver` |
| `io-exception-acceptance` | One I/O outcome left unobserved, bound to source hash, line and argument | `qualification-approver` |
| `equivalence-review` | Accept or reject a review packet: per mutant, or a class proof | `qualification-approver` |
| `legacy-behaviour-disposition` | Keep or fix a registered legacy behaviour (for example REWRITE-109) | `business-owner` |
| `twin-human-review` | Accept, reject or investigate each record of a twin review sheet | `qualification-approver` |
| `model-spend-approval` | One plan hash: calls, tokens, hours, dollar cap, transport, client | `campaign-authorizer` |
| `engineering-run-approval` | One executable commit, request seal and window for an engineering run | `campaign-authorizer` |

How to decide:

1. Open the item in **Work queue**. Read the bound evidence and hashes; the card
   lists exactly what the decision covers and what it does not.
2. Choose the outcome, give a reason, an accountable owner and a review date
   where asked, then click **Record decision** once.
3. Confirm the signed event in **Decision history**. The Programs page updates
   from the signed record.

Points to watch:

- **Model spend.** You approve a plan hash, not a description. If the plan is
  amended, even only its labels, it comes back as a new request.
- **Keep or fix.** Changing a behaviour from keep to fix invalidates every
  equivalence argument that depends on it. The page lists them before you
  confirm.
- **Equivalence review.** An AI-assisted review is labelled as such. Accepting it
  is an operator decision, not independent attestation.
- **Engineering runs.** Approval names one commit and one window. A later commit
  or a missed window needs a new request.

## 13. Historical backfill and current prerequisites

Preserve the dated `docs/factory/howard-decisions-*.json` sources and original
conditions. The October 14 importer binds the complete dated inventory, original
record contents and dates, exact byte hashes and **one source commit**. The
historical seven-record source commit in the October 17 correction is
`5e36903a162c032179be2c97e6cc0cd88e6dcfb3`; the publication snapshot is a different
identity. Do not substitute one for the other.

Both `tower-backfill-request-2026-10-12.json` and
`tower-backfill-request-2026-10-14.json` are retired. The first has the earlier
two-record inventory; the second mixes two source commits and fails current
single-commit validation. Do not re-import or sign either. See the
[supersession clarification](factory/tower-backfill-supersession-clarification-2026-10-18.md)
and [import validation](../src/lightyear_control_tower/factory_import.py).

The October 21 [MS-106 evidence correction](factory/first-install-2026-10-21/ms106-correction.md)
supersedes treating the October 14/17 activation narratives as substantiated
installation, backfill-signature or consumer-enforcement deployment facts. A historical
JSON field or decision hash is not a current cryptographic proof. The correction
does not assert that no installation ever existed elsewhere.

Not yet established by those historical records: a current installation, new
seven-record proof at an independently trusted current journal head, or current
consumer trust configuration. A future operator review must preserve original
dates and conditions while recording the actual new action time. It must not
backdate signing, renew spend, lift a new merge hold or permit B06 activity.
Use the existing deployment only after its separate installation and trust
prerequisites are evidenced; this manual does not create another Factory root.

## 14. What the Factory scope does not do

- It does not run the factory, start campaigns, call models or run the twin.
- It does not show customer data, Maintec arrivals or decoded values.
- A Factory "releasable" result is about the public reference programs. It is not
  z/OS confirmation and not a customer release; those remain separate evidence
  and separate decisions.

For complete contracts see [CardDemo Tower](mainframe/carddemo-zos-tower.md),
[the intake runbook](mainframe/monday-runbook.md),
[Decision Console administration](control-tower-decision-console.md) and
[Factory scope administration](control-tower-factory-scope.md).


## Factory administration and evidence prerequisites

See [Factory scope administration](control-tower-factory-scope.md). The seven
Factory kinds are joined by `factory-decision-backfill` for the one-time dated
record inventory. It requires qualification-approver, campaign-authorizer and
business-owner together. Its signature records historical intent; it does not
turn past conditional approval into a new run or model-spend authorization.

For backfill, use a newly reviewed complete single-commit inventory, subject to
the retired-request checks in section 13. Each source document must retain its
original date, complete content and byte hash. The unsigned POSTTRAN review is a
separate `twin-human-review` request;
its suggested outcomes and reasons remain unsigned until confirmed in the queue.
MCP `propose_factory_decision` annotates a Factory request; it cannot approve.

Consumers use `LIGHTYEAR_FACTORY_AUTHORITY` only after the signed backfill is
installed. An invalid configured trust file is an error, never a fallback to
chat. The public key and fresh journal head come from the operator, not the
request. Refresh every proof to that head. Conditional threshold approval stays
pending until an explicit effective policy approval; no conditional text is
automatically treated as satisfied. Existing frozen plans remain historical and
must be amended and approved before using changed verifier bytes.


### APPL overlap, thresholds and ordered release

APPL-RESULT intake checks every intersecting `equivalence-review` item set for
the same program, including subsets, supersets and partial overlaps. It compares
the current public selection, live requests and latest decisions against a
verified Factory journal. A renamed request does not escape that check. A
version-2 supersession record must bind **all** predecessors, their live/selected/
decided states, request and normalized contract hashes, decision hashes where
applicable, and the exact successor. The old version-1 exact-set form works only
for its sole matching predecessor, never partial or multiple overlaps. Source:
[supersession contract](../src/lightyear_control_tower/factory_supersessions.py).

Threshold/2 has four typed conditions: B1 compiler/class evidence and targeted
attempts; remaining individual reviews; a fresh current-head compiled campaign;
and keep-or-fix register dependencies. An effective policy needs every condition
met with the exact evidence source. Hash shape alone is insufficient: evidence
must have the right schema, program, head, population and scope. Nested review
proofs must cover the exact required item set and remain valid against current
external trust; later replacements or keep-to-fix changes can invalidate them.
An empty condition list cannot turn a conditional policy into an effective one.
Sources: [conditions](../src/lightyear_control_tower/threshold_conditions.py) and
[typed evidence](../src/lightyear_control_tower/threshold_evidence.py).

Threshold/3 permits only the seven exact INTCALC constant-field diversity
exemptions. It retains the other policy criteria and binds field, source path,
source hash, source line and line hash. Each constant still needs observed
comparison, complete mutant evidence and at least one caught mutant. The T2
correction adds constant-output mutations for the three merchant fields whose
deletion mutants did not establish a caught value change; fresh measured outcomes
are necessary before credit. A refusal, timeout or argued equivalent is not a
kill. Sources: [constant exemption validator](../src/lightyear_factory/threshold3.py),
[constant evidence builder](../src/lightyear_mainframe/constant_evidence.py) and
[T2 correction](factory/intcalc-constant-evidence-correction-2026-10-17.md).

The INTCALC ordered packet has six steps: loader-domain disposition; APPL-RESULT
class review; individual/compiler reviews; threshold/3 policy; line-189 I/O
exception; effective threshold last. Later steps bind the immediately preceding
decision, same packet and program, correct outcome and unsuperseded journal
sequence. Intake, decision recording and consumption all enforce the chain.
The published sixth template has unmet typed conditions; a predecessor hash
alone cannot make it signable. The binding tool checks the complete packet before
producing output. Rounds 2–6 require new public request bytes and the separate
review/merge process described in the [ordered runbook](factory/intcalc-ordered-signing-runbook.md).
No ordered signature sequence alone grants release or POSTTRAN Phase 2 execution.
See [order validator](../src/lightyear_control_tower/factory_order.py),
[packet](factory/intcalc-signing-order-2026-10-17.json) and
[release evidence requirements](factory/release-grade-evidence-2026-10-18.md).

### Programs evidence display

The Programs tab uses `/api/tower/programs` and `/api/tower/program?id=INTCALC`
(or POSTTRAN). An administrator imports a public Git snapshot and pins its index
hash outside the engine root. Without that pin the tab reports unavailable.
Experiment head and evidence-import commit are shown separately. The current
compact receipts come from public CI run 38198096890 on 2dd7876, not a new run on
the Tower code. Raw counts include denominators; twin and z/OS-facing assessments
are separate. Evidence gaps overlap proof categories. Green CI is not a release.

Expand Evidence sources and SHA-256 in any panel to inspect the exact committed
artifact. Measurements, historical policy assessments and signed overlays remain
separate. Not reported means absent in the installed evidence; pending means a
review/decision is outstanding; failed means a measured criterion is unmet.
Waiting on you opens the Work queue. No request is created by merely viewing a
program. Business rules displays rule evidence strength plus scenario adequacy
and reasons without hiding the original rule-evidence classification.


## Status and Unresolved

Status uses `/api/tower/status` and the `factory_status.status` model. The
committed `docs/factory/current-status.md` has its own generator and input records;
do not assume it is a live mirror of this Console or that their counts share a
denominator. The Console uses its pinned evidence index and scoped queue: zero
queue items does not mean all scientific reviews are complete. It adds decision
overlays and queue
ages. Old requests without timestamps show “not reported”; no age is invented.
B06 hold and B07 planning are historical receipt states, not execution permission.

Unresolved uses `/api/tower/unresolved?program=POSTTRAN&kind=evidence-gap`.
Filters include survivors, evidence gaps, twin limits, pending reviews,
invalidated arguments, disagreements and divergences. Only recorded evidence
creates rows. Cross-scope repetitions are labelled; the row count is not a
mutation adequacy denominator. Empty filters do not prove the absence of defects.
Every row includes its source hash. Signed keep-to-fix changes append invalidation
overlays while preserving raw arguments. Programs and these two routes are
unavailable outside Factory. The original Console tabs remain present; views
without an installed adapter say unavailable rather than showing another scope.

Future pages are designs only: [dual-run monitor](factory/tower-dual-run-plan.md),
[ZD&T calibration](factory/tower-zdt-plan.md) and [B07 campaigns](factory/tower-b07-plan.md).
No dispatch, native run or new decision kind is enabled by those pages.

## Closed API and vocabulary reference

Routes require authentication except session establishment. Mutating routes use
the existing CSRF/session controls; this list grants no role or execution power.
A route can report unavailable in a scope. Factory-only routes are programs,
program, status and unresolved; intake also leaves knowledge and business-rules
unavailable. Session uses POST; reads use GET and the four write routes use POST.

- `/api/tower/arrivals`
- `/api/tower/business-rules`
- `/api/tower/campaign`
- `/api/tower/campaigns`
- `/api/tower/catalogue`
- `/api/tower/decide`
- `/api/tower/events`
- `/api/tower/export`
- `/api/tower/history`
- `/api/tower/item`
- `/api/tower/knowledge`
- `/api/tower/logout`
- `/api/tower/program`
- `/api/tower/programs`
- `/api/tower/proof`
- `/api/tower/propose`
- `/api/tower/queue`
- `/api/tower/review`
- `/api/tower/rules`
- `/api/tower/session`
- `/api/tower/status`
- `/api/tower/unresolved`
- `/api/tower/validation`
- `/api/tower/workspace`

Navigation identifiers and labels:

- `status`: Status
- `unresolved`: Unresolved
- `programs`: Programs
- `campaigns`: Campaigns
- `queue`: Work queue
- `catalogue`: Catalogue
- `workspace`: Customer workspace
- `history`: Decision history
- `knowledge`: Graph memory
- `businessRules`: Business rules

The eight Factory kinds are listed in section 12 and the migration section.
The following is the complete registry vocabulary across installed scopes; it
does not make default/B06 kinds available in Factory. Intake retains only
intake-acceptance, normalization, difference-disposition and evidence-release.

- `b06-pause`
- `b06-qualification-group`
- `business-rule-disposition`
- `campaign-authorization`
- `classification-acceptance`
- `difference-disposition`
- `embedding-provider-approval`
- `engineering-run-approval`
- `equivalence-review`
- `evidence-release`
- `factory-decision-backfill`
- `freeze-approval`
- `graph-annotation`
- `graph-annotation-verified`
- `graph-search-labels`
- `intake-acceptance`
- `io-exception-acceptance`
- `legacy-behaviour-disposition`
- `measurement-validity`
- `model-routing-policy`
- `model-spend-approval`
- `normalization`
- `partner-share`
- `pilot-slice-approval`
- `procedure-equivalence-policy`
- `qualification-acceptance`
- `reference-approval`
- `requalification-request`
- `resume`
- `rule-approval`
- `rule-retirement`
- `rule-technical-review`
- `scenario-threshold-approval`
- `twin-human-review`
- `verify-attempt-review`
- `verify-budget-increase`
- `verify-graph-projection`
- `verify-normalization`
