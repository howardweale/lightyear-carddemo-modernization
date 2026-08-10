$ErrorActionPreference = "Stop"

$ProjectDir = $PSScriptRoot
$env:PYTHONPATH = Join-Path $ProjectDir "src"
Set-Location $ProjectDir
& py -3.11 -m lightyear_knowledge_graph serve @args
exit $LASTEXITCODE
