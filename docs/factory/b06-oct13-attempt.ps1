# DEFERRED: exactly one authorized attempt per invocation, never automatic attempt 2.
param(
 [Parameter(Mandatory=$true)][string]$ExecutionCheckout,
 [Parameter(Mandatory=$true)][string]$EngineeringAuthority
)
$ErrorActionPreference='Stop'
$Now=[DateTimeOffset]::UtcNow
if ($Now -lt [DateTimeOffset]::Parse('2026-10-13T16:00:00Z') -or $Now -ge [DateTimeOffset]::Parse('2026-10-13T19:00:00Z')) { throw 'Outside exact B06 window' }
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
