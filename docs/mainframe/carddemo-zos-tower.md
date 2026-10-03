# CardDemo z/OS intake in Control Tower v2

The `carddemo-zos` workspace is separate from campaign workspaces. Its authority
selects a mandatory `carddemo-zos-no-values/1` policy; request files cannot disable
it. The Workspace tab and `GET /api/tower/arrivals` show arrival hashes, file/run/
finding counts and status. They are read-only. There is no job dispatch, record
viewer, filesystem browser or campaign observer in this workspace.

## Disclosure boundary

Original datasets, decoded records, keys, filenames from deliveries, SYSOUT,
logs and candidate inputs/outputs remain in ignored local arrival directories.
The Tower reads only closed review records under
`work/mainframe/review/carddemo-zos/<sha256>.json`. Unknown or nested extra fields
are refused. Untrusted request summaries, author labels and timestamps are not
reflected. Invalid request filenames appear only as hash commitments.

The allowed vocabulary is fixed status labels, pinned copybook field names,
counts, evidence hashes, authenticated identity metadata and review expiry.
Hashes commit to complete artifacts, not individual record values. Free-text
notes and reasons are hashed **before signing** and the text is not stored in the
journal. Keep readable sensitive explanations in the private local intake record.
The UI explains this when reviewing a CardDemo request.

HTTP, SSE and the seven existing read/draft MCP tools share this policy. Generic
campaign, estate and catalogue adapters cannot expose data through this scope.
Signed journal records are verified before reading or exporting; old journals
without this disclosure contract are refused rather than redacted and re-signed.

## Workspace and identities

Use the intake clone as `$IntakeRoot`, not a running campaign's data root. Set
`$TowerAuthority` to a new path outside the engine-writable intake clone, for
example a sibling private authority directory. These commands create no approval:

```powershell
$IntakeRoot = (Get-Location).Path
$TowerAuthority = Join-Path (Split-Path $IntakeRoot) 'carddemo-zos-authority/authority.json'
.\.venv\Scripts\python.exe -m lightyear_control_tower init-carddemo-workspace --root $IntakeRoot
.\.venv\Scripts\python.exe -m lightyear_control_tower provision --authority $TowerAuthority --scope carddemo-zos --operator-id howard-weale --operator-name 'Howard Weale'
.\.venv\Scripts\python.exe -m lightyear_control_tower grant-roles --root $IntakeRoot --authority $TowerAuthority --operator-id howard-weale --roles operator qualification-approver normalization-approver business-owner campaign-authorizer --workloads workload:carddemo-intcalc --reason 'Howard administers the CardDemo intake review'
.\.venv\Scripts\python.exe -m lightyear_control_tower add-identity --root $IntakeRoot --authority $TowerAuthority --operator-id zos-intake --operator-name 'Intake agent' --identity-kind agent --credential-output (Join-Path (Split-Path $TowerAuthority) 'agent.credential.txt')
.\.venv\Scripts\python.exe -m lightyear_control_tower grant-roles --root $IntakeRoot --authority $TowerAuthority --operator-id zos-intake --roles agent --reason 'Intake draft proposals only'
.\.venv\Scripts\python.exe -m lightyear_control_tower serve --root $IntakeRoot --authority $TowerAuthority --port 8767
```

Keep each credential with its designated person/process. Do not copy keys into
the intake data root or grant an agent an approving role. Opening the Console
and recording a decision requires Howard's credential. A public rehearsal uses
disposable test identities; it is not an actual Howard approval.

For evidence release, a distinct customer identity `release-sponsor` (display
name `Release sponsor`, kind `customer`) needs the `customer-sponsor` role.
Provision that person's credential using the same local-only administration
commands. Howard occupies the other `campaign-authorizer` slot. No single
identity can provide both release approvals.

## Request contracts and decisions

All requests use `tower-request/1`, scope `carddemo-zos`, and the existing inbox
`work/control-tower/requests/carddemo-zos/`. IDs are the kind plus a SHA-256 of
the evidence bindings. The request envelope and exact evidence bytes are bound
to each review. Evidence changes require another review in the same session.

| Kind | Producer and evidence | Decision |
|---|---|---|
| `intake-acceptance` | `intake`; `zos-intake-review/1` counts and hashes | Howard, qualification-approver, accepted/rejected |
| `normalization` | `compare-runs`; `zos-tower-rule/1`, exact two run hashes, declared timestamp field, still-caught mutation | Authenticated agent proposal, then Howard, normalization-approver, approved/rejected |
| `difference-disposition` | Divergent `verdict-intcalc`; `zos-difference-review/1`, signed verdict/execution/run hashes and counts | Howard, workload business-owner, defect/intended-change/needs-information |
| `evidence-release` | `request-evidence-release`; a closed bundle of intake/difference review records | Separate customer-sponsor and Howard campaign-authorizer approvals |

The difference request's diagnostic/source/target/workload bindings all commit
to the complete closed review record, including both source and target hashes.
The scope fixes the workload. A disposition changes neither the verdict nor any
normalization rule. An intended change still needs its own rule proposal.

The agent reads the normalization item through MCP and invokes `propose_rule`
with `item_id`, the current `bound` object, a fresh UUID `request_id`, `text`, and
the exact `zos-tower-rule/1` object from `evidence_view.rule`. The service checks
the agent identity and rule bytes and appends a signed proposal. The item then
becomes decidable by Howard. Howard supplies a reason, owner `howard-weale` and
future review date. This is **operator review, not independent attestation**.
An agent cannot decide, and a proposer label in a request is not authentication.

## One normalization authority

`verdict-intcalc` performs exact decoded-field comparison by default, including
filler and trailing spaces. It no longer imports, validates or applies
`spec/comparison-normalizations.json`. Canonical numeric decoding remains exact;
there is no second source of comparison rules.

The only currently supported exception is a declared processing timestamp, for
the exact approved runs, matching the qualified timestamp pattern on both sides.
Supply either a `zos-approved-rules/1` decision bundle or the signed
`zos-rule-register/1` from `GET /api/tower/rules`. Both contain exact rule objects
and complete verified Tower proofs. The consumer checks the independently trusted
key and current journal head, scope, Howard identity, authenticated agent proposal,
approved outcome, expiry, supersession, field binding and still-caught condition.
There is no `ledger` member. Legacy bundles fail closed. Offline replay checks the
same archived head and approval time; it does not claim present-day authorization.

See the [Monday runbook](monday-runbook.md) for verdict and replay commands.
Preserve earlier signed rehearsals with their original implementation; this
change does not rewrite or re-sign historical results.

## Release only the closed review bundle

Choose the exact no-values review JSON files, not an arrival/archive directory:

```powershell
.\.venv\Scripts\python.exe -m lightyear_mainframe request-evidence-release --members $IntakeReviewFile $DifferenceReviewFile
```

After both people approve the bound bundle, `GET /api/tower/export?id=<request-id>`
returns a signed `zos-released-export/1` containing the closed bundle and both
decision proofs. Verify it offline with:

```powershell
.\.venv\Scripts\python.exe -m lightyear_control_tower verify-export --archive $ExportFile --trusted-public-key $TowerPublicKey
```

A missing approval, rejection, changed bundle or invalid signature refuses the
export. An archived export establishes the decisions at its signed journal head;
a later rejection prevents a fresh export. No raw evidence release is supported.

## Public-data rehearsal

The [intake fixture provenance](../../tests/mainframe/fixtures/PROVENANCE.json)
pins the public dataset bytes. Run the mainframe public rehearsal from the Monday
runbook and these regression suites:

```powershell
$env:PYTHONPATH = 'src;.'
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\python.exe -m unittest tests.test_carddemo_zos_tower tests.test_zos_intake -v
```

The disclosure test plants a canary into a public fixed-width EBCDIC record and
decodes it, then attacks notes, summaries, filenames and unrelated adapters. It
checks every HTTP read route, the actual SSE response, every write refusal path,
all seven MCP methods over the loopback HTTP client and a valid dual-approved
export. Other tests cover all four decision kinds, agent/Howard separation,
stale/tampered/expired/superseded approvals, exact filler/padding comparison and
live journal tampering. The fixtures are synthetic; this is not Maintec execution
or production review. No models, Docker or campaign operations are involved.
