# Read-only inventory. Does not start an observer, application, container or run.
param([string]$EvidenceRoot = 'C:\Users\howar\lightyear-b06\oct13-pm')
$ErrorActionPreference = 'Stop'
$root = Get-Item -LiteralPath $EvidenceRoot
if (-not $root.PSIsContainer -or ($root.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
    throw 'Evidence root must be an existing regular directory'
}
$files = @(Get-ChildItem -LiteralPath $root.FullName -File -Force -Recurse | Sort-Object FullName)
$inventory = foreach ($file in $files) {
    if ($file.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Linked evidence refused' }
    [ordered]@{
        name = $file.FullName.Substring($root.FullName.Length).TrimStart('\')
        size = $file.Length
        sha256 = if ($file.Extension -eq '.json') { (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant() } else { $null }
    }
}
[ordered]@{
    schema = 'b06-read-only-evidence-inventory/1'
    directory = $root.FullName
    files = @($inventory)
    receipts_verified = $false
    native_runs = 0
    limitation = 'Names, sizes and JSON hashes only; signature verification is a separate read-only step.'
} | ConvertTo-Json -Depth 5
