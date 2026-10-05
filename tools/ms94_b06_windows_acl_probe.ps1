#Requires -RunAsAdministrator
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Repository,
    [Parameter(Mandatory=$true)][string]$PrivateDirectory,
    [Parameter(Mandatory=$true)][string]$OutputDirectory,
    [string]$AccountName = 'lyb06builder',
    [string]$ExistingAccountSid
)
$ErrorActionPreference = 'Stop'
# Built-in Windows tooling only. No execution-policy change, exclusions, custom
# native helper, model invocation or Docker operation.
$repo = (Resolve-Path -LiteralPath $Repository).Path
$private = (Resolve-Path -LiteralPath $PrivateDirectory).Path
$toolsPath = Join-Path $repo 'tools'
$target = Join-Path $toolsPath 'ms94_b06_builder_boundary.py'
if (!(Test-Path -LiteralPath $target -PathType Leaf)) { throw 'Existing tools target required' }
if ($private -match '[\\/]work[\\/]ms94([\\/]|$)') { throw 'Protected historical path' }
$existing = Get-LocalUser -Name $AccountName -ErrorAction SilentlyContinue
if ($existing -and (!$ExistingAccountSid -or $existing.SID.Value -ne $ExistingAccountSid -or $existing.Enabled)) {
    throw 'Only the exact disabled account from the previous owned probe may be reused'
}
if (!$existing -and $ExistingAccountSid) { throw 'Expected account missing' }
if (Test-Path -LiteralPath $OutputDirectory) { throw 'Probe output already exists' }
$out = New-Item -ItemType Directory -Path $OutputDirectory
$started = [DateTime]::UtcNow.ToString('o')
$runtime = Join-Path $PSHOME 'powershell.exe'
if (!(Test-Path -LiteralPath $runtime)) { throw 'Run under built-in Windows PowerShell 5.1' }
$taskName = 'Lightyear-B06-Probe-' + [Guid]::NewGuid().ToString('N')
$random = New-Object byte[] 36
$rng = [Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($random); $rng.Dispose()
$password = 'Aa1!' + [Convert]::ToBase64String($random)
$secure = ConvertTo-SecureString $password -AsPlainText -Force
$created = $false
$registered = $false
try {
    if ($existing) {
        Set-LocalUser -Name $AccountName -Password $secure
        Enable-LocalUser -Name $AccountName
        $account = Get-LocalUser -Name $AccountName
    } else {
        $account = New-LocalUser -Name $AccountName -Password $secure -Description 'B06 unprivileged builder' -AccountNeverExpires
    }
    $created = $true
    $sid = $account.SID.Value
    $users = Get-LocalGroup -SID 'S-1-5-32-545'
    if (!$existing) { Add-LocalGroupMember -Group $users -Member $account }
    $memberships = @(Get-LocalGroup | ForEach-Object {
        $group = $_
        if (@(Get-LocalGroupMember -Group $group -ErrorAction Stop | Where-Object { $_.SID.Value -eq $sid }).Count) { $group.SID.Value }
    })
    if ($memberships.Count -ne 1 -or $memberships[0] -ne 'S-1-5-32-545') { throw 'Account has unexpected group privileges' }
    $adminSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    & icacls.exe $out.FullName /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' "*$($adminSid):(OI)(CI)F"
    if ($LASTEXITCODE) { throw 'Output ACL setup failed' }
    $public = New-Item -ItemType Directory -Path (Join-Path $out.FullName 'public')
    $results = New-Item -ItemType Directory -Path (Join-Path $out.FullName 'child-output')
    & icacls.exe $out.FullName /grant "*$($sid):RX"
    if ($LASTEXITCODE) { throw 'Parent traversal ACL failed' }
    & icacls.exe $public.FullName /grant "*$($sid):(OI)(CI)RX"
    if ($LASTEXITCODE) { throw 'Public ACL failed' }
    & icacls.exe $results.FullName /grant "*$($sid):(OI)(CI)M"
    if ($LASTEXITCODE) { throw 'Result ACL failed' }
    foreach ($folder in @($toolsPath, $private)) {
        & icacls.exe $folder /deny "*$($sid):(OI)(CI)R"
        if ($LASTEXITCODE) { throw 'Protected ACL failed' }
    }
    $privateFile = Join-Path $private ('b06-denial-control-' + $taskName + '.txt')
    if (Test-Path -LiteralPath $privateFile) { throw 'Private probe control already exists' }
    [IO.File]::WriteAllText($privateFile, 'Private B06 denial control; never emitted by the child')
    $allowed = Join-Path $public.FullName 'allowed.txt'
    [IO.File]::WriteAllText($allowed, 'B06 public positive control')
    $policy = [ordered]@{
        artifact_type='ms94-b06-windows-acl-policy/1'; account_sid=$sid
        protected_directories=@($toolsPath,$private); protected_targets=@($target,$privateFile)
        allowed_file=$allowed; missing_file=(Join-Path $public.FullName 'never-created.txt')
        result_file=(Join-Path $results.FullName 'result.json'); required_error=5
        results_directory=$results.FullName; read_targets=@($target,$privateFile,$allowed,(Join-Path $public.FullName 'never-created.txt'))
    }
    $policyFile = Join-Path $public.FullName 'policy.json'
    $policy | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $policyFile -Encoding UTF8
    . (Join-Path $PSScriptRoot 'ms94_b06_windows_probe_commands.ps1')
    $commands=@(Get-B06ProbeCommands)
    $childFile=Join-Path $public.FullName 'probe-commands.json'
    $commands | ConvertTo-Json | Set-Content -LiteralPath $childFile -Encoding UTF8
    $credential=New-Object Management.Automation.PSCredential("$env:COMPUTERNAME\$AccountName",$secure)
    $launches=@()
    for ($index=0; $index -lt $commands.Count; $index++) {
        $launch=Invoke-B06ReadCommand -Runtime $runtime -Command $commands[$index] -WorkingDirectory $public.FullName -OutputLog (Join-Path $results.FullName ("stdout-$index.log")) -ErrorLog (Join-Path $results.FullName ("stderr-$index.log")) -Index $index -Credential $credential
        $launches+=@($launch)
        $launches | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $out.FullName 'launch-results.json') -Encoding UTF8
        if ($launch.exit_code -ne 0) { throw "Read probe $index exited with $($launch.exit_code); inspect its stderr log" }
    }
    $identity=Get-Content -LiteralPath (Join-Path $results.FullName 'identity.json') -Raw | ConvertFrom-Json
    $reads=@(0..3 | ForEach-Object {Get-Content -LiteralPath (Join-Path $results.FullName ("read-$_.json")) -Raw | ConvertFrom-Json})
    if ($identity.identity_sid -ne $sid -or $identity.administrator -or @($reads | Where-Object {$_.identity_sid -ne $sid -or $_.administrator}).Count) { throw 'Read probes used an unexpected identity' }
    $childResult=[ordered]@{identity_sid=$identity.identity_sid;identity_name=$identity.identity_name;administrator=$identity.administrator;group_sids=$identity.group_sids;denials=@($reads[0],$reads[1]);positive=$reads[2];missing=$reads[3]}
    $childResult | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $policy.result_file -Encoding UTF8
    $exitCode=0
    foreach ($denial in @($reads[0],$reads[1])) {
        $nativeDenied=$denial.exception_type -eq 'System.ComponentModel.Win32Exception' -and $denial.native_error -eq 5
        $managedDenied=$denial.exception_type -eq 'System.UnauthorizedAccessException' -and $denial.hresult -eq -2147024891
        if ($denial.opened -or $denial.error -ne 5 -or !($nativeDenied -or $managedDenied)) { $exitCode=1 }
    }
    if (!$reads[2].opened -or $reads[3].opened -or $reads[3].category -ne 'ObjectNotFound' -or $reads[3].error -eq 5) { $exitCode=1 }
    $record=[ordered]@{
        artifact_type='ms94-b06-windows-acl-observation/1'; started_utc=$started; ended_utc=[DateTime]::UtcNow.ToString('o')
        account_sid=$sid; account_name=$AccountName; local_group_sids=$memberships; launch_method='windows-runas-short-commands'; task_run_level='NotApplicable'
        launches=$launches; command_factory_sha256=(Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'ms94_b06_windows_probe_commands.ps1') -Algorithm SHA256).Hash.ToLower()
        launcher_sha256=(Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLower()
        child_script_sha256=(Get-FileHash -LiteralPath $childFile -Algorithm SHA256).Hash.ToLower()
        policy_sha256=(Get-FileHash -LiteralPath $policyFile -Algorithm SHA256).Hash.ToLower()
        runtime_path=$runtime; runtime_sha256=(Get-FileHash -LiteralPath $runtime -Algorithm SHA256).Hash.ToLower()
        target_sha256=(Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLower()
        private_target_sha256=(Get-FileHash -LiteralPath $privateFile -Algorithm SHA256).Hash.ToLower()
        target_existed_before=$true; private_target_existed_before=$true; child=$childResult
        child_exit_code=$exitCode; model_calls=0; native_pairs=0
        acls=@($toolsPath,$private,$public.FullName | ForEach-Object { @{path=$_; sddl=(Get-Acl -LiteralPath $_).Sddl} })
        status=$(if ($exitCode -eq 0) {'passed'} else {'failed'})
    }
    $record | ConvertTo-Json -Depth 15 | Set-Content -LiteralPath (Join-Path $out.FullName 'observation.json') -Encoding UTF8
    if ($record.status -ne 'passed') { throw 'OS denial probe failed; preserve observation' }
} catch {
    @{artifact_type='ms94-b06-windows-acl-probe-failure/1'; started_utc=$started;
      ended_utc=[DateTime]::UtcNow.ToString('o'); status='failed';
      exception_type=$_.Exception.GetType().FullName; failure_id=$_.FullyQualifiedErrorId;
      failure_message=$_.Exception.Message.Replace($password,'[redacted]');
      account_created=$created; model_calls=0; native_pairs=0} |
        ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $out.FullName 'failure.json') -Encoding UTF8
    throw
} finally {
    if ($registered) { Unregister-ScheduledTask -TaskName $taskName -Confirm:$false }
    # Preserve the exact account and ACLs; disable until an admitted launch uses
    # this identity. Do not delete a principal and leave reusable SID assumptions.
    if ($created) { Disable-LocalUser -Name $AccountName }
    $password=$null; $secure=$null
}
