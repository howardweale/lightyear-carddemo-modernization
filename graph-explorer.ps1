$ErrorActionPreference = "Stop"

$ProjectDir = $PSScriptRoot
$env:PYTHONPATH = Join-Path $ProjectDir "src"
. (Join-Path $ProjectDir "python-runtime.ps1")
Set-Location $ProjectDir
Invoke-FactoryDarkPython -m lightyear_knowledge_graph serve @args
exit $LASTEXITCODE
