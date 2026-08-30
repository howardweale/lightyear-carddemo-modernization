param(
  [ValidateSet("build", "verify")][string]$Command = "verify"
)
$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ProjectDir "python-runtime.ps1")
$Python = Resolve-LightyearPython
$env:PYTHONPATH = Join-Path $ProjectDir "src"
& $Python -m lightyear_readiness.cobol $Command --project-root $ProjectDir
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
