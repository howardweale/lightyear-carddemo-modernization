param(
  [ValidateSet("serve", "validate", "events", "verify")][string]$Command = "serve",
  [Parameter(ValueFromRemainingArguments=$true)][string[]]$Rest
)
$ErrorActionPreference = "Stop"
$ProjectDir = $PSScriptRoot
$env:PYTHONPATH = Join-Path $ProjectDir "src"
. (Join-Path $ProjectDir "python-runtime.ps1")
Set-Location $ProjectDir

if ($Command -eq "serve") {
  Invoke-FactoryDarkPython -m lightyear_knowledge_graph serve @Rest
} elseif ($Command -eq "verify") {
  Invoke-FactoryDarkPython -m unittest tests.test_live_control_tower -v
  if ($LASTEXITCODE -eq 0) {
    Invoke-FactoryDarkPython -m lightyear_control_tower validate --database (Join-Path $ProjectDir "work/control-tower/events.sqlite3")
  }
} else {
  Invoke-FactoryDarkPython -m lightyear_control_tower $Command @Rest
}
exit $LASTEXITCODE
