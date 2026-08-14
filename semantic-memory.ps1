$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:PYTHONPATH = Join-Path $ProjectDir "src"
$Action = if ($args.Count -gt 0) { $args[0] } else { "validate" }
$MemoryRoot = if ($env:LIGHTYEAR_MEMORY_ROOT) { $env:LIGHTYEAR_MEMORY_ROOT } else { Join-Path $ProjectDir "factory/memory/store" }
$Policy = Join-Path $ProjectDir "factory/memory/policy.json"
$Python = if (Get-Command python3.13 -ErrorAction SilentlyContinue) { "python3.13" } else { "python" }

switch ($Action) {
  "validate" { & $Python -m lightyear_factory memory-validate --memory-root $MemoryRoot --memory-policy $Policy }
  "summary" { & $Python -m lightyear_factory memory-summary --memory-root $MemoryRoot --memory-policy $Policy }
  "query" {
    $WorkOrder = if ($args.Count -gt 1) { $args[1] } else { Join-Path $ProjectDir "factory/work-orders/intcalc-repair.example.json" }
    & $Python -m lightyear_factory memory-query --work-order $WorkOrder --source-root $ProjectDir --graph (Join-Path $ProjectDir "knowledge/graph.snapshot.json.gz") --evidence-pack (Join-Path $ProjectDir "knowledge/evidence/source.pack.json.gz") --memory-root $MemoryRoot --memory-policy $Policy
  }
  "ingest" {
    if ($args.Count -lt 2) { throw "Usage: ./semantic-memory.ps1 ingest <run-directory>" }
    & $Python -m lightyear_factory memory-ingest --run-dir $args[1] --memory-root $MemoryRoot --memory-policy $Policy
  }
  default { throw "Usage: ./semantic-memory.ps1 [validate|summary|query|ingest] [path]" }
}
exit $LASTEXITCODE
