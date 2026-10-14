# B06 - October 13 afternoon replacement: NOT READY

The 9 AM-noon window is cancelled; no attempt was consumed. The previous r3 go is not valid for this replacement. Howard's same-day replacement instruction and subsequent authority-pin approval govern this preparation. No operational signing, native attempt, model call or merge has occurred.

Primary window: **2-5 PM PDT** (21:00Z-00:00Z); latest strict start **2:40**, latest diagnostic start **3:50**. Fallback: **4-7 PM**, latest starts **4:40 / 5:50**, only if Howard explicitly selects it and the window is changed and request re-sealed before a new exact go. No automatic fallback, retry or third attempt.

## Current prerequisites (R4 delivered 9:18:49 AM PDT; machine inventory 9:11 AM)

| Prerequisite | Result | Evidence / remaining action |
| --- | --- | --- |
| Exact classes and observer | PASS | All 14 class hashes equal r3; observer 6420e836... and helper 1f3de745... unchanged. Compilation only; no observer execution. |
| Recovered assets | PASS for original r5 | 111,311 files; template bd0ade82... unchanged; index c0f23e40...; 308.969 seconds rebuild including 64.422 seconds final verification. |
| Replacement execution checkout | PASS | Locked clean branch codex/b06-oct13-pm at ac9f533822576170ac2f1b6bf25f66ce22a25033. Exactly three production-line changes, test constants and requested authority tests. |
| Replacement authority | PASS offline | Fingerprint 6d4083d20e5d17e5d3be07dd660621f913cfd50da60c68a361fe628565f7aa7f. Public identity accepted; old identity, wrong folder, qualification admission and campaign-key substitution rejected. |
| Old authority | REVOKED for engineering | 4ce00cfa... recorded lost, unrecoverable and never used. No trust if it reappears. Old public records remain historical. |
| R4 template binding | PASS | Howard approved exactly the two Python-file hash updates. New template d9e10a3f...; final index b5314039...; existing template() at ac9f5338 verified all 111,311 files in 58.015 seconds. Original r5 remains documented separately. |
| R4 / new exact go | REQUEST PASS; GO PENDING | R4 delivered 9:18:49 AM PDT, seal 7e5270c1...; exact request verified. Howard has not sent the new go. Do not use the old request or morning wrapper. |
| Four-hour review interval | UNCHANGED | Complete R4 delivery must be by 10 AM for 2 PM, or noon for 4 PM. R4 was delivered at 9:18:49 AM, meeting the 2 PM interval. The 1 PM delivery constant does not override this guard. |
| Docker images / overlap | UNKNOWN - blocking | Both permitted inventory calls failed: dockerDesktopLinuxEngine pipe not found. No Docker startup or setting change performed. Howard must restore availability before fresh read-only inventory. |
| Disk | PASS | 627.84 GiB free; minimum 60 GiB. |
| Free host memory | FAIL | 5.95 GiB at 9:11 AM; launch requires at least 30 GiB immediately before start. Howard closes heavy apps and quits OneDrive only after sync. |
| Offline tests | PASS within offline scope | 538 discovered: 491 passed, 47 host/evidence tests skipped. Ten initial loopback-audit errors passed targeted rerun. No native/model execution or operational key reads. |

[Exact R3/R4 binding review](b06-oct13-r4-binding-review.md), [preparation receipt](b06-afternoon-preparation-2026-10-13.json) and [one-page sheet](b06-oct13-one-page-runbook.pdf). Prior readiness receipts stay unchanged and describe their historical checks only. The old b06-oct13-attempt.ps1 is a cancelled-morning artifact: **do not invoke it**.

## Paths and read-only checkpoint

All new inputs are outside Codex-managed worktrees. Keep recovered and new worktrees locked until cleanup is sealed. At 1:15 PM, use these paths and a separately delivered, verified R4 file hash. If R4 is absent or a check fails, stop without signing or starting an attempt.

```powershell
$B06Root = 'C:/Users/howar/lightyear-b06/oct13-pm'
$ExecutionCheckout = "$B06Root/execution"
$EngineeringAuthority = "$B06Root/b06-engineering-authority"
$Request = "$B06Root/b06-oct13-proposal-r4/request.json"
$Assets = "$B06Root/assets"
$Python = 'C:/Users/howar/OneDrive/Documents/ChatGPT/lightyear-carddemo-modernization/work/idempiere-runtime-evidence/work/native-venv/Scripts/python.exe'
if (!(Test-Path -LiteralPath $Request)) { throw 'R4 not delivered; NOT READY' }
$RequestHash = '5fe273fcffe2c6c299cc3ff4fff1784ff56a5c0c3af7112fd27d844e4ef8b6c5'
Set-Location -LiteralPath $ExecutionCheckout
$env:PYTHONUTF8='1'; $env:PYTHONPATH='src;.'
& $Python -B -c "import sys; from pathlib import Path; from tools.ms94_b06_oct13_authorization import validate_request; from tools.ms94_b06_engineering_run import template,source_commit; from tools.ms94_b06_engineering_key import read_public; from lightyear_calibration.contracts import read_json; from tools.ms94_b06_engineering import sha; r=read_json(Path(sys.argv[1])); assert sha(Path(sys.argv[1]))==sys.argv[3]; validate_request(r); assert source_commit(Path.cwd())==r['implementation_commit']; read_public(sys.argv[4],r['engineering_key_sha256']); template(sys.argv[2],Path(sys.argv[2])/'templates/j1/plan.json',r); print('offline request/key/template/assets/checkout verified')" $Request $Assets $RequestHash $EngineeringAuthority
if ($LASTEXITCODE -ne 0) { throw 'Preflight refused' }
$B06Disk = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'"
$B06Memory = Get-CimInstance Win32_OperatingSystem
if ($B06Disk.FreeSpace -lt 60GB) { throw 'Disk below 60 GiB' }
if (([long]$B06Memory.FreePhysicalMemory * 1024) -lt 30GB) { throw 'Host free memory below 30 GiB' }
docker image ls --digests
if ($LASTEXITCODE -ne 0) { throw 'Image inventory unavailable' }
docker ps -a
if ($LASTEXITCODE -ne 0) { throw 'Overlap inventory unavailable' }
```

Verify all three exact pinned image identities and no live B06/J1 resources or workers, closed registered windows, a fresh output root and no lease before READY. A missing or ambiguous inventory is not a pass. This block never starts Docker. Do not read private key files. Leave Tower 8768 untouched; this engineering path uses the local supervisor and signed cleanup, not the Tower service.

## Exact request and deferred launch

R4 seal: `7e5270c1457aafbe5872df08b4d5ae1f80caba9c6b48ccae379adc6cd9062901`. Required future go line, **not yet received**:

```text
go B06 ac9f533822576170ac2f1b6bf25f66ce22a25033 7e5270c1457aafbe5872df08b4d5ae1f80caba9c6b48ccae379adc6cd9062901
```

Never launch without Howard's new exact go.

Only after R4 is validated, all fresh gates pass, the selected window opens, and Howard supplies the exact go in chat:

```powershell
$Go = Read-Host 'Paste Howard''s NEW exact go line from chat'
$Output = (Get-Content -Raw -LiteralPath $Request | ConvertFrom-Json).output_root
& $Python -B -m tools.ms94_b06_oct13_run --go $Go --request $Request --request-file-sha256 $RequestHash --assets $Assets --template "$Assets/templates/j1/plan.json" --output $Output --authority $EngineeringAuthority
```

That is one attempt only. Do not infer permission from this printed command. Immediately before invoking it, recheck at least 30 GiB free host memory and every readiness gate. The signed ledger selects strict first, then diagnostic unmatched-return cap 10. Work 3,600 seconds, cleanup 600 seconds, candidate timeout 1,800 seconds; these limits do not change. Manual review and verification consume margin before the latest starts.

## Between attempts and Part 6

Show Howard the signed terminal, attempt consumption/mode/owner, request/plan/source/artifact hashes, first unmatched sequence, lifecycle/class-prepare and application-phase records, genuine input-witness classifications, heap/guard/dump and output sizes, plus authenticated cleanup and actual absence of owned resources. Show elapsed and remaining time. A failed attempt is consumed. Stop for uncertain cleanup, identity, evidence or time. Attempt two requires a separate invocation after review; no automatic continuation.

The [R4-bound Part 6 template](b06-oct13-part6-template.json) records both outcomes, generation entries, first unmatched/count, ordinary and metadata counts/bytes, peak heap/output, guard/dump hashes, lifecycle/phase records, witness counts, signed terminal/archive hashes and verified cleanup. Apply unchanged criterion (a): exact lifecycle/class-prepare explanation at first unmatched return; or (b): the same application operation near generation 12,400 in both attempts. Otherwise: **cause not identified; stop observer repair; Howard selects the alternative**. No qualification or measurement credit.

Cleanup must be sealed by 5 PM, or 7 PM only for a separately selected and approved fallback. All merges remain held until authenticated cleanup is sealed. **Current verdict: NOT READY.**
