#Requires -RunAsAdministrator
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$Repository,
      [Parameter(Mandatory=$true)][string]$PrivateTarget,
      [Parameter(Mandatory=$true)][string]$Codex,
      [Parameter(Mandatory=$true)][string]$OutputDirectory,
      [Parameter(Mandatory=$true)][string]$AccountSid)
$ErrorActionPreference='Stop'
$repo=(Resolve-Path -LiteralPath $Repository).Path
$private=(Resolve-Path -LiteralPath $PrivateTarget).Path
if ($private -match '[\\/]work[\\/]ms94([\\/]|$)') { throw 'Historical path prohibited' }
$account=Get-LocalUser -Name 'lyb06builder'
if ($account.SID.Value -ne $AccountSid -or $account.Enabled) { throw 'Exact disabled dedicated account required' }
$groups=@(Get-LocalGroup | ForEach-Object {
    $g=$_;if (@(Get-LocalGroupMember -Group $g -ErrorAction Stop|Where-Object {$_.SID.Value -eq $AccountSid}).Count) {$g.SID.Value}
})
if ($groups.Count -ne 1 -or $groups[0] -ne 'S-1-5-32-545') { throw 'Unexpected local group membership' }
if (Test-Path -LiteralPath $OutputDirectory) { throw 'Existing probe is immutable; choose new output' }
$out=New-Item -ItemType Directory -Path $OutputDirectory
$public=New-Item -ItemType Directory -Path (Join-Path $out.FullName 'public')
$results=New-Item -ItemType Directory -Path (Join-Path $out.FullName 'child-output')
$adminSid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
& icacls.exe $out.FullName /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' "*$($adminSid):(OI)(CI)F" "*$($AccountSid):RX"
if ($LASTEXITCODE) { throw 'Root ACL failed' }
& icacls.exe $public.FullName /grant "*$($AccountSid):(OI)(CI)RX"
if ($LASTEXITCODE) { throw 'Public ACL failed' }
& icacls.exe $results.FullName /grant "*$($AccountSid):(OI)(CI)M"
if ($LASTEXITCODE) { throw 'Output ACL failed' }
$toolsPath=Join-Path $repo 'tools'
$target=Join-Path $toolsPath 'ms94_b06_builder_boundary.py'
foreach ($folder in @($toolsPath,(Split-Path -Parent $private))) {
    & icacls.exe $folder /deny "*$($AccountSid):(OI)(CI)R"
    if ($LASTEXITCODE) { throw 'Protected ACL failed' }
}
$cli=Join-Path $public.FullName 'codex.exe'
Copy-Item -LiteralPath $Codex -Destination $cli
$sha=(Get-FileHash -LiteralPath $Codex -Algorithm SHA256).Hash.ToLowerInvariant()
if ((Get-FileHash -LiteralPath $cli -Algorithm SHA256).Hash.ToLowerInvariant() -ne $sha) { throw 'Codex copy changed' }
$childSource=Join-Path $toolsPath 'ms94_b06_codex_probe_child.ps1'
$child=Join-Path $public.FullName 'child.ps1'
Copy-Item -LiteralPath $childSource -Destination $child
$allowed=Join-Path $public.FullName 'allowed.txt'
[IO.File]::WriteAllText($allowed,'B06 public positive control')
$runtime=Join-Path $PSHOME 'powershell.exe'
if (!(Test-Path -LiteralPath $runtime)) { throw 'Windows PowerShell 5.1 required' }
$policy=@{account_sid=$AccountSid;codex_sha256=$sha;powershell=$runtime;results_directory=$results.FullName;
    read_targets=@($allowed,(Join-Path $public.FullName 'missing.txt'),$target,$private)}
$policyPath=Join-Path $public.FullName 'policy.json'
$policy|ConvertTo-Json -Depth 8|Set-Content -Encoding UTF8 -LiteralPath $policyPath
$before=@{}
foreach ($p in @($target,$private,$child,$policyPath,$runtime,$cli)) {$before[$p]=(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant()}
$rule='Lightyear-B06-ZeroModel-'+[Guid]::NewGuid().ToString('N')
$random=New-Object byte[] 36
$rng=[Security.Cryptography.RandomNumberGenerator]::Create();$rng.GetBytes($random);$rng.Dispose()
$secure=ConvertTo-SecureString ('Aa1!'+[Convert]::ToBase64String($random)) -AsPlainText -Force
$process=$null;$ruleCreated=$false;$enabled=$false
$started=[DateTime]::UtcNow.ToString('o')
try {
    New-NetFirewallRule -Name $rule -DisplayName $rule -Direction Outbound -Action Block -Program $cli -Profile Any|Out-Null
    $ruleCreated=$true
    Set-LocalUser -Name 'lyb06builder' -Password $secure
    Enable-LocalUser -Name 'lyb06builder';$enabled=$true
    $credential=New-Object Management.Automation.PSCredential("$env:COMPUTERNAME\lyb06builder",$secure)
    # Launch the executable directly: the builder's script policy is unchanged.
    . $childSource
    Invoke-B06CodexAccountProtocol -Directory $public.FullName -Credential $credential
    foreach ($p in $before.Keys) {
        if ((Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant() -ne $before[$p]) { throw 'Bound probe input changed' }
    }
    @{artifact_type='ms94-b06-codex-host-observation/1';started_utc=$started;ended_utc=[DateTime]::UtcNow.ToString('o');
      account_sid=$AccountSid;local_group_sids=$groups;input_sha256=$before;model_calls=0;docker_runs=0;
      firewall_rule=$rule;firewall_block_observed=(Get-NetFirewallRule -Name $rule).Action.ToString();
      child_exit_code=0;launcher_sha256=(Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
    }|ConvertTo-Json -Depth 10|Set-Content -Encoding UTF8 -LiteralPath (Join-Path $out.FullName 'host.json')
} catch {
    @{status='failed';exception_type=$_.Exception.GetType().FullName;message=$_.Exception.Message;real_utc=[DateTime]::UtcNow.ToString('o');model_calls=0;docker_runs=0}|ConvertTo-Json|Set-Content -Encoding UTF8 -LiteralPath (Join-Path $out.FullName 'failure.json')
    throw
} finally {
    if ($process -and !$process.HasExited) { & taskkill.exe /PID $process.Id /T /F|Out-Null }
    if ($enabled) { Disable-LocalUser -Name 'lyb06builder' }
    if ($ruleCreated) { Remove-NetFirewallRule -Name $rule }
    @{account_disabled=!(Get-LocalUser -Name 'lyb06builder').Enabled;firewall_rule_removed=!(Get-NetFirewallRule -Name $rule -ErrorAction SilentlyContinue);real_utc=[DateTime]::UtcNow.ToString('o')}|ConvertTo-Json|Set-Content -Encoding UTF8 -LiteralPath (Join-Path $out.FullName 'cleanup.json')
    if ($process) {$process.Dispose()}
    $secure.Dispose()
}
