# B06 - Tuesday October 13, 9 AM-noon PDT

Readiness assessed using Howard's supplied `codex-b06-readiness-gaps-2026-10-12.md` (SHA-256 `48afcfc5107f83c3882432018b589fc0498405dbcc81478964e83dee7b367367`). The new instruction resolves the earlier uncertainty about VM thresholds and the Tower dependency. [Final readiness receipt](b06-readiness-instruction-2026-10-12.json); [preliminary evidence](b06-readiness-evening-2026-10-12.json) and [original dry run](b06-dry-run-2026-10-12.json) remain unchanged.

| Prerequisite | Ready? | Evidence | Action needed (by whom) |
| --- | --- | --- | --- |
| Execution worktree | Yes | Separate detached clean HEAD 62eafdaf29dce1d40603d38c3a394f150b98f686. | Codex: keep pinned; recheck at 8:30. |
| Line endings and hashes | Yes | 873 tracked files match the asset index; observer/helper are LF by attributes and match bound hashes; 14 compiled classes verified in existing assets. | None; no autocrlf change or compilation. |
| Offline preflight from worktree | Yes | All 111,311 files and seals passed from exact checkout in 118.797s. | Codex: repeat read-only command at 8:30. |
| Engineering authority | Yes | Existing public fingerprint matches 4ce00cfa...367be9f0; engineering read_public accepts; qualification replay_entry/replay_clocks reject it. | Use existing path below; no key creation or pre-window signing. |
| 8768 Tower | Yes - not required | Exact engineering path uses local supervisor/worker, local cancellation, signed ledger handoff and cleanup; no Tower service or decision polling. | Leave 8768 stopped. |
| Docker memory and CPUs | Yes | 31.04 GiB / 24 CPUs exceeds 28 GiB / 11; 24 GiB container caps leave 7.04 GiB nominal VM margin. No .wslconfig exists. | No Docker/WSL change or restart needed. |
| Host free memory | Morning step | 12.17 GiB free of 63.39 GiB; process inventory below. This is not a free-VM measurement. | Howard at 8:00: close unnecessary apps normally; recheck host memory. |
| Python | Yes | Runbook native-venv runs Python 3.12.10; satisfies repository >=3.11. Request has no separate exact Python-version pin. | Use the exact interpreter path below. |
| Request and assets | Yes | Request file 663fa537...344fc9, seal107c2073...7900f35, template/index and full asset inventory verified unchanged. | Repeat morning preflight; no asset edits. |
| Output root | Yes | Absent/fresh; parent exists with Howard FullControl; no active.lock, request session or prior attempts; 611.59 GiB free. Ledger.lock creates it during launch. | Do not pre-create it tonight; guarded entry point creates it. |
| No overlap | Yes - registered checks | Six bound windows closed; all related B06/J1 monitors paused; no matching native worker process; excluded windows end Oct10. Live Docker overlap was not queried tonight. | Codex: mandatory launch no_overlap/image/lease checks still apply; refuse if changed. |
| Go line | Yes | Howard supplied exact go for62eafdaf /107c2073 in this chat. No attempts consumed. | 8:45 go/no-go; separate review before attempt2. |

## Why the Tower can remain stopped

At the exact pinned commit, [oct13_run.main](../../tools/ms94_b06_oct13_run.py) validates the exact go and delegates directly to [engineering_run.main](../../tools/ms94_b06_engineering_run.py), not the Tower controller. `OracleEngineeringRunner.check_cancel` in [engineering_native](../../tools/ms94_b06_engineering_native.py) checks the local cancellation file, calendar and limits; it does not poll Tower pause decisions. The supervisor imports `verify_envelope` as a local cryptographic function, not an HTTP service. Attempt 2 is a separate invocation admitted by `Ledger.verify_prior_runs`; [engineering_evidence.verify_prior](../../tools/ms94_b06_engineering_evidence.py) authenticates terminal, handoff, artifact and complete/actual-absence cleanup records. Cleanup is executed and signed by the local supervisor/worker, with Howard reviewing between attempts. No running 8768 Tower is required for pause/decision, handoff or cleanup on this engineering path. No Tower startup command is needed or authorized tonight.

## Host memory and morning actions

Host free memory was **12.17 GiB** at `2026-10-12T23:54:44.0227518+00:00`. Docker reported **31.04 GiB / 24 CPUs** in the single authorized call; it meets the instruction's **28 GiB / 11 CPU** minimum. The four container limits total 24 GiB; nominal VM overhead margin is 7.04 GiB. No `.wslconfig` exists, so no explicit `memory=` or `processors=` override was found. **No WSL or Docker setting change/restart is needed under the supplied criterion.**

Largest process groups by working set: chrome 10.09 GiB, OneDrive 9.29 GiB, ChatGPT 3.21 GiB, claude 1.20 GiB. These working sets can share pages and are not additive physical-memory totals. Windows Memory Compression is 11.66 GiB; it is an OS component, not an app to close. Howard should save work and normally close unnecessary browser tabs/apps, and quit OneDrive only after checking sync completion. Do not stop Windows services, Memory Compression, WSL or Docker. No processes were closed.

## Morning checklist

- **8:00, Howard:** save work; close unnecessary apps; check host free memory. Do not change the pinned checkout or asset copy.
- **8:30, Codex:** run only the read-only preflight block below from the exact execution checkout. Recheck clean HEAD, hashes/seals, output/lease and registered windows. Do not invoke the native entry point before 9:00. Today's read-only `docker info` allowance is consumed; do not repeat it without authorization.
- **8:45, Howard and Codex:** go/no-go on fresh preflight and available window. Live image/overlap checks remain enforced by the exact entry point after 9:00; any failure refuses launch.
- **9:00:** separate attempt-1 invocation in strict mode; **latest start 9:40**. No automatic retry.
- **Between attempts:** show the evidence and authenticated cleanup listed below; Howard reviews before a separate invocation.
- **Attempt 2:** diagnostic unmatched-return cap 10, **latest start 10:50**; no third attempt.
- **By noon:** cleanup and evidence sealed. Only after authenticated cleanup is verified may the merge hold be lifted.

No known unresolved prerequisite requires a later window. If fresh checks or review cannot finish before 9:40, do not compress or skip them: refuse attempt 1 and propose a new window. Readiness is not a promise that the native target will complete.

[One-page printable runbook](b06-oct13-one-page-runbook.pdf) - [deferred one-attempt wrapper](b06-oct13-attempt.ps1). No native commands were executed tonight. One new worktree, one read-only docker info, zero private-key reads/signatures/model calls/pulls/containers/settings changes/merges.

## 8:30 - read-only preflight from the exact worktree

Use the two verified existing paths below. The 8:30 block performs only offline hashes/seals and machine inventory; it does not invoke the attempt or open a private key.

```powershell
$ExecutionCheckout = 'C:/Users/howar/.codex/worktrees/b06-oct13-pinned-readiness/lightyear-carddemo-modernization'
$EngineeringAuthority = 'C:/Users/howar/.codex/worktrees/b06-engineering-bindings/lightyear-carddemo-modernization/work/b06-engineering-authority'
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
```

## 9:00 - invoke attempt 1 only after go/no-go

Keep the verified variables and working directory above. This is the first command that can consume an attempt, open the private signing key and start native resources; it is deferred until the approved window.

```powershell
$Output = (Get-Content -Raw -LiteralPath $Request | ConvertFrom-Json).output_root
& $Python -B -m tools.ms94_b06_oct13_run --go $Go --request $Request --request-file-sha256 $RequestHash --assets $Assets --template "$Assets/templates/j1/plan.json" --output $Output --authority $EngineeringAuthority
```

The last command is **attempt 1 only**, strict mode. Its signed ledger selects the mode; no manual mode override. Exact go has already been supplied by Howard. The entry point enforces window, disk, pins, overlap, authority and remaining budget before native activity. **Latest first start 9:40 AM; latest second start 10:50 AM.** Hashing and manual review consume margin. Work 3,600s, cleanup 600s, candidate 1,800s per attempt; noon is absolute.

## Between attempts — show Howard, then separately invoke

Show signed terminal/owner/consumed attempt/mode, request/plan/source/artifact hashes; first unmatched sequence, lifecycle/class-prepare and application-phase records, genuine input-witness classifications, heap/guard/dump and output sizes; and signed cleanup plus actual owned-resource absence. Show elapsed time and remaining window. Verify prior ledger signatures and artifact seals. A failed attempt is consumed. Stop if cleanup, identity, evidence or time is uncertain. After Howard's review, repeat **only the final invocation command**, once: ledger selects diagnostic unmatched-return cap 10. No automatic continuation, retries, third attempt, guard increase or observer repair.

## Part 6 — report after cleanup

Fill [the bound JSON template](b06-oct13-part6-template.json): both attempt outcomes/consumption, generation entries, first unmatched sequence/count, ordinary/metadata counts and bytes, output/peak heap, guard/dump hashes, lifecycle/phase evidence, input-witness counts, signed terminal/archive hashes and verified cleanup. Cite criterion (a) an exact lifecycle/class-prepare explanation at the first unmatched return, or (b) the same operation near generation 12,400 in both attempts. Otherwise state **cause not identified**, stop repair, and let Howard choose an alternative. No qualification or measurement credit.


**READY** - only the listed morning steps and fresh guarded launch checks remain.
