param(
    [ValidateSet("build", "verify")]
    [string]$Command = "verify"
)

$ErrorActionPreference = "Stop"
$ProjectDir = $PSScriptRoot
. (Join-Path $ProjectDir "python-runtime.ps1")
$Arguments = @((Join-Path $ProjectDir "tools/generate_milestone_documentation.py"), $Command)
Invoke-FactoryDarkPython @Arguments
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
