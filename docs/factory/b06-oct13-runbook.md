# B06 — Tuesday October 13, 9 AM–noon PDT

**Dry run October 12:** all 111,311 asset hashes, request/index/template seals and 14 observer-class bindings passed (103 seconds). Three pinned image digests were present in the single authorized Docker listing. C: had 616.65 GiB free (minimum 60); host memory 63.39 GiB total / 17.28 GiB free. Container/VM memory readiness is not established. No listener was found on 8768, so a running Tower checkout/commit is unavailable. No service was changed. [Read-only receipt](b06-dry-run-2026-10-12.json).

**Before launch:** an operator must supply a clean execution checkout at `62eafdaf29dce1d40603d38c3a394f150b98f686` and the existing dedicated authority directory. The preparation checkout is `4659d591` (documentation HEAD), so it cannot execute this request. No registered checkout at the execution commit was found. Do not reset the preparation checkout, provision keys, change memory settings or restart 8768. Resolve these prerequisites before the window; otherwise stop.

## 9:00 — read-only preflight and first invocation

In PowerShell, set `$ExecutionCheckout` and `$EngineeringAuthority` to the operator-confirmed existing paths. The authority argument is the directory containing its public/key records; no key contents are displayed.

```powershell
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
