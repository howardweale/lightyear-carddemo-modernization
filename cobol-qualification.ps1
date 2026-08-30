param(
  [ValidateSet("build", "verify")][string]$Command = "verify"
)
$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ProjectDir "python-runtime.ps1")
$env:PYTHONPATH = Join-Path $ProjectDir "src"
Invoke-FactoryDarkPython -m lightyear_readiness.cobol $Command --project-root $ProjectDir
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
