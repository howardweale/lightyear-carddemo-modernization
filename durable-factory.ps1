param(
  [Parameter(Position=0)][string]$Command = "status",
  [Parameter(ValueFromRemainingArguments=$true)][string[]]$Rest
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = if ($env:PYTHON) { $env:PYTHON } else { "python" }
$env:PYTHONPATH = "$Root/src" + $(if ($env:PYTHONPATH) { ";$env:PYTHONPATH" } else { "" })
$Database = if ($env:LIGHTYEAR_DURABLE_DATABASE) { $env:LIGHTYEAR_DURABLE_DATABASE } else { "$Root/work/durable/control.sqlite3" }

if ($Command -eq "verify") {
  & $Python -m unittest tests.test_durable_factory -v
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  $Database = Join-Path $env:TEMP ("lightyear-durable-" + [guid]::NewGuid().ToString() + ".sqlite3")
  & $Python -m lightyear_factory durable-init --database $Database | Out-Null
  & $Python -m lightyear_factory durable-validate --database $Database
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  $Generated = Join-Path $env:TEMP "lightyear-durable-conformance.json"
  & $Python -m lightyear_factory durable-conformance --project-root $Root --output $Generated | Out-Null
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  $ExpectedHash = (Get-FileHash (Join-Path $Root "factory/durable/conformance.receipt.json") -Algorithm SHA256).Hash
  $ActualHash = (Get-FileHash $Generated -Algorithm SHA256).Hash
  if ($ExpectedHash -ne $ActualHash) { throw "Durable conformance receipt differs" }
  Remove-Item $Database, $Generated -Force -ErrorAction SilentlyContinue
  exit 0
}
if ($Command -eq "conformance") {
  & $Python -m lightyear_factory durable-conformance --project-root $Root @Rest
  exit $LASTEXITCODE
}
$Allowed = @("init", "submit", "lease", "start", "heartbeat", "complete", "fail", "recover", "status", "validate", "conformance")
if ($Allowed -notcontains $Command) {
  Write-Error "Usage: ./durable-factory.ps1 [init|submit|lease|start|heartbeat|complete|fail|recover|status|validate|verify] [options]"
}
& $Python -m lightyear_factory "durable-$Command" --database $Database @Rest
exit $LASTEXITCODE
