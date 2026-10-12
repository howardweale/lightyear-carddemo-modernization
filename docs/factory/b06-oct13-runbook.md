# B06 - Tuesday October 13, 9 AM-noon PDT

**Evening verdict October12: NOT READY.** The exact execution checkout gap is closed. VM capacity is measured; the remaining readiness gaps below are unresolved. No native execution, model call, private-key read, image pull, container start, machine change or merge was performed.

[Evening evidence receipt](b06-readiness-evening-2026-10-12.json). The [original dry-run receipt](b06-dry-run-2026-10-12.json) remains unchanged. This is a readiness inventory, not a native pass or independent attestation.

| Prerequisite | Status | Evidence / required action |
| --- | --- | --- |
| Exact execution checkout | PASS | New separate clean checkout at 62eafdaf29dce1d40603d38c3a394f150b98f686. Existing B06 checkout/data unchanged. |
| Request, assets and seals | PASS | 111311 files and 14 observer-class bindings passed from the exact checkout; 118.797 seconds. |
| Free disk >=60 GiB | PASS | 610.08 GiB free on C: at 2026-10-12T23:24:57.8786698+00:00. Recheck before launch. |
| Docker VM resources | CAPACITY VERIFIED | 31.04 GiB and 24 CPUs reported by one read-only docker info. Four documented container limits total 24 GiB / 11 CPUs; nominal VM margin 7.04 GiB. Allocation is not free-memory or availability proof. |
| Host / combined memory | UNRESOLVED | 63.39 GiB total / 13.78 GiB free. No current VM usage/reservation or combined host headroom established; no settings changed. |
| Three pinned images | EARLIER CHECK PASSED | All three were present in the authorized October12 image listing. No new listing, pull or container start tonight; presence must be revalidated by the approved launch preflight. |
| Tower on 8768 | UNRESOLVED | No listener found. A running checkout/commit cannot be identified. No service start, restart or provisioning is authorized tonight. |
| Dedicated engineering authority | OPERATOR CONFIRMATION | Existing authority directory remains operator-supplied. Request binds public fingerprint 4ce00cfa28c13f74c12e6569b6aae010fe7e7185849accad8340c2fc367be9f0. No private keys read, no new identity or signature. |
| Historical cleanup / overlap | WINDOW RECHECK | Earlier six registry entries / 24 marker hashes passed. No current owned-resource absence or lease check was performed tonight. Existing launch gate must verify this in the authorized window. |
| Attached readiness instruction | MISSING | No new attachment/path was supplied or located. Requested its filename/path; do not infer its additional prerequisites. |

**Current 9:40 assessment:** Readiness by October13 09:40 PDT is not established. Tower absence cannot be resolved under the current no-service-change authority. Missing instruction, authority confirmation and combined memory readiness require operator resolution; no promised time or improvised substitute. If unresolved at 09:40, do not start attempt1. No alternate service, checkout, key, resource setting or launch sequence is substituted.

The sole new checkout is `C:/Users/howar/.codex/worktrees/b06-oct13-pinned-readiness/lightyear-carddemo-modernization`, clean at `62eafdaf29dce1d40603d38c3a394f150b98f686`. Leave it pinned and clean. Do not create a replacement.

[Updated one-page printable runbook](b06-oct13-one-page-runbook.pdf) - [deferred one-attempt command wrapper](b06-oct13-attempt.ps1). Commands below are for the authorized window only after all prerequisites resolve; none were executed tonight.

## 9:00 — read-only preflight and first invocation

Use the verified execution checkout below. Set `$EngineeringAuthority` only to the operator-confirmed existing directory; do not guess or provision it. The authority argument is the directory containing its public/key records; no key contents are displayed.

```powershell
$ExecutionCheckout = 'C:/Users/howar/.codex/worktrees/b06-oct13-pinned-readiness/lightyear-carddemo-modernization'
$Python = 'C:/Users/howar/OneDrive/Documents/ChatGPT/lightyear-carddemo-modernization/work/idempiere-runtime-evidence/work/native-venv/Scripts/python.exe'
$Preparation = 'C:/Users/howar/.codex/worktrees/b06-engineering-bindings/lightyear-carddemo-modernization'
$Request = "$Preparation/work/b06-oct13-proposal-r3/request.json"
$Assets = "$Preparation/work/b06-oct13-engineering-assets-r5"
$Go = 'go B06 62eafdaf29dce1d40603d38c3a394f150b98f686 107c20733d9bc7862461b6e13ba4c180cdf1dad160f51be410c5523587900f35'
$RequestHash = '663fa537b827dbdf71be14e27cce9a5f26155dea6c19671765e7fa7f5e344fc9'
Set-Location -LiteralPath $ExecutionCheckout
$env:PYTHONUTF8='1'; $env:PYTHONPATH='src;.'
& $Python -B -c "import sys; from pathlib import Path; from tools.ms94_b06_oct13_authorization import validate_request; from tools.ms94_b06_engineering_run import template,source_commit; from lightyear_calibration.contracts import read_json; from tools.ms94_b06_engineering import sha; r=read_json(Path(sys.argv[1])); assert sha(Path(sys.argv[1]))==sys.argv[3]; validate_request(r); assert source_commit(Path.cwd())==r['implementation_commit']; template(sys.argv[2],Path(sys.argv[2])/'templates/j1/plan.json',r); print('offline hashes/seals/exact checkout passed')" $Request $Assets $RequestHash
if ($LASTEXITCODE -ne 0) { throw 'Preflight refused' }
Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'" | Select-Object FreeSpace
Get-CimInstance Win32_OperatingSystem | Select-Object TotalVisibleMemorySize,FreePhysicalMemory
$Output = (Get-Content -Raw -LiteralPath $Request | ConvertFrom-Json).output_root
& $Python -B -m tools.ms94_b06_oct13_run --go $Go --request $Request --request-file-sha256 $RequestHash --assets $Assets --template "$Assets/templates/j1/plan.json" --output $Output --authority $EngineeringAuthority
```

The last command is **attempt 1 only**, strict mode. Its signed ledger selects the mode; no manual mode override. Exact go has already been supplied by Howard. The entry point enforces window, disk, pins, overlap, authority and remaining budget before native activity. **Latest first start 9:40 AM; latest second start 10:50 AM.** Hashing and manual review consume margin. Work 3,600s, cleanup 600s, candidate 1,800s per attempt; noon is absolute.

## Between attempts — show Howard, then separately invoke

Show signed terminal/owner/consumed attempt/mode, request/plan/source/artifact hashes; first unmatched sequence, lifecycle/class-prepare and application-phase records, genuine input-witness classifications, heap/guard/dump and output sizes; and signed cleanup plus actual owned-resource absence. Show elapsed time and remaining window. Verify prior ledger signatures and artifact seals. A failed attempt is consumed. Stop if cleanup, identity, evidence or time is uncertain. After Howard's review, repeat **only the final invocation command**, once: ledger selects diagnostic unmatched-return cap 10. No automatic continuation, retries, third attempt, guard increase or observer repair.

## Part 6 — report after cleanup

Fill [the bound JSON template](b06-oct13-part6-template.json): both attempt outcomes/consumption, generation entries, first unmatched sequence/count, ordinary/metadata counts and bytes, output/peak heap, guard/dump hashes, lifecycle/phase evidence, input-witness counts, signed terminal/archive hashes and verified cleanup. Cite criterion (a) an exact lifecycle/class-prepare explanation at the first unmatched return, or (b) the same operation near generation 12,400 in both attempts. Otherwise state **cause not identified**, stop repair, and let Howard choose an alternative. No qualification or measurement credit.
