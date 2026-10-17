# Parse only. Never execute a fenced block.
$ErrorActionPreference = 'Stop'
$Files = @(Get-ChildItem -LiteralPath 'docs/factory' -Filter '*runbook*.md')
$Files += Get-Item -LiteralPath 'docs/factory/appl-result-signing-2026-10-16/README.md'
$Files += Get-Item -LiteralPath 'docs/factory/appl-result-signing-2026-10-17.md'
$Supersessions = Get-Content -LiteralPath 'docs/factory/runbook-supersessions-2026-10-17.json' -Raw | ConvertFrom-Json
$Failures = @()
foreach ($File in $Files) {
    $Historical = @($Supersessions.records | Where-Object { (Resolve-Path -LiteralPath $_.historical_path).Path -eq $File.FullName })
    if ($Historical.Count) {
        if ($Historical.Count -ne 1 -or (Get-FileHash -LiteralPath $File.FullName -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Historical[0].sha256 -or -not (Test-Path -LiteralPath $Historical[0].replacement_path)) { throw 'Historical runbook supersession mismatch' }
        Write-Output "Preserved historical runbook: $($File.Name); linting its replacement."
        continue
    }
    $Text = Get-Content -LiteralPath $File.FullName -Raw
    $Blocks = [regex]::Matches($Text, '(?ms)^```powershell\s*\r?\n(.*?)^```')
    $Index = 0
    foreach ($Block in $Blocks) {
        $Index++
        $Tokens = $null; $ParseErrors = $null
        $Ast = [System.Management.Automation.Language.Parser]::ParseInput($Block.Groups[1].Value, [ref]$Tokens, [ref]$ParseErrors)
        if ($ParseErrors.Count) { $Failures += "$($File.Name):$Index parse errors"; continue }
        $Assigned = @{}
        foreach ($Node in $Ast.FindAll({param($n) $n -is [System.Management.Automation.Language.AssignmentStatementAst]}, $true)) {
            foreach ($Variable in $Node.Left.FindAll({param($n) $n -is [System.Management.Automation.Language.VariableExpressionAst]}, $true)) { $Assigned[$Variable.VariablePath.UserPath] = $true }
        }
        foreach ($Node in $Ast.FindAll({param($n) $n -is [System.Management.Automation.Language.ForEachStatementAst]}, $true)) { $Assigned[$Node.Variable.VariablePath.UserPath] = $true }
        foreach ($Variable in $Ast.FindAll({param($n) $n -is [System.Management.Automation.Language.VariableExpressionAst]}, $true)) {
            $Name = $Variable.VariablePath.UserPath
            if ($Name -notin @('null','true','false','LASTEXITCODE','_','PSItem') -and -not $Assigned.ContainsKey($Name)) { $Failures += "$($File.Name):$Index unassigned variable $Name" }
        }
    }
}
if ($Failures.Count) { throw ($Failures | Sort-Object -Unique | Out-String) }
Write-Output 'All fenced PowerShell blocks are self-contained; none were executed.'
