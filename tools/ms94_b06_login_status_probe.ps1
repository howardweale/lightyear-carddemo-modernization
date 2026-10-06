#Requires -RunAsAdministrator
param([Parameter(Mandatory=$true)][string]$Repository,[Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference='Stop'
$account=Get-LocalUser -Name 'lyb06builder'
if ($account.Enabled) { throw 'Expected disabled dedicated account' }
if (Test-Path -LiteralPath $OutputDirectory) { throw 'Preserve earlier attempt; new output required' }
$out=New-Item -ItemType Directory -Path $OutputDirectory
$public=New-Item -ItemType Directory -Path (Join-Path $out.FullName 'public')
$results=New-Item -ItemType Directory -Path (Join-Path $out.FullName 'results')
$sid=$account.SID.Value
$operatorSid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
& icacls.exe $out.FullName /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' "*$($operatorSid):(OI)(CI)F" "*$($sid):RX" | Out-Null
if ($LASTEXITCODE) { throw 'Output ACL failed' }
& icacls.exe $public.FullName /grant "*$($sid):(OI)(CI)RX" | Out-Null
if ($LASTEXITCODE) { throw 'Public ACL failed' }
& icacls.exe $results.FullName /grant "*$($sid):(OI)(CI)M" | Out-Null
if ($LASTEXITCODE) { throw 'Result ACL failed' }
$child=Join-Path $public.FullName 'status-child.ps1'
Copy-Item -LiteralPath (Join-Path $Repository 'tools/ms94_b06_login_status_child.ps1') -Destination $child
$cli='C:\Program Files\Lightyear\Codex\0.160.0\codex.exe'
if ((Get-FileHash -LiteralPath $cli -Algorithm SHA256).Hash.ToLowerInvariant() -ne '4b01d5920e6785614727443bbecf343f4dedbb7347052b72ba805aab6353ef01') { throw 'Client hash differs' }
$owned='Lightyear-B06-LoginStatus-'+[Guid]::NewGuid().ToString('N')
$taskCreated=$false;$ruleCreated=$false
$stage='network-block'
try {
    New-NetFirewallRule -Name $owned -DisplayName $owned -Direction Outbound -Action Block -Program $cli -Profile Any|Out-Null
    $ruleCreated=$true
    $stage='enable-account'
    Enable-LocalUser -Name 'lyb06builder'
    # S4U needs no password reset and cannot establish authenticated remote connections.
    $principal=New-ScheduledTaskPrincipal -UserId ($env:COMPUTERNAME+'\lyb06builder') -LogonType S4U -RunLevel Limited
    $arguments='-NoProfile -NonInteractive -File "'+$child+'" -OutputDirectory "'+$results.FullName+'"'
    $action=New-ScheduledTaskAction -Execute (Join-Path $PSHOME 'powershell.exe') -Argument $arguments
    $settings=New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 2) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    $stage='register-task'
    Register-ScheduledTask -TaskName $owned -Action $action -Principal $principal -Settings $settings|Out-Null
    $taskCreated=$true
    $stage='start-task'
    Start-ScheduledTask -TaskName $owned
    $deadline=[DateTime]::UtcNow.AddSeconds(120)
    while (!(Test-Path -LiteralPath (Join-Path $results.FullName 'status.json')) -and [DateTime]::UtcNow -lt $deadline) { Start-Sleep -Milliseconds 500 }
    if (!(Test-Path -LiteralPath (Join-Path $results.FullName 'status.json'))) {
        $info=Get-ScheduledTaskInfo -TaskName $owned
        throw ('No status record; scheduled task result '+$info.LastTaskResult)
    }
    $value=Get-Content -LiteralPath (Join-Path $results.FullName 'status.json') -Raw|ConvertFrom-Json
    if ($value.account_sid -ne $sid) { throw 'Wrong account result' }
    # Safe summary only; no auth.json, keyring values, raw output or token copied.
    $value | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $out.FullName 'observation.json')
} catch {
    @{error_type=$_.Exception.GetType().FullName;message=$_.Exception.Message;stage=$stage;position=$_.InvocationInfo.PositionMessage;stack=$_.ScriptStackTrace;model_calls=0;docker_commands=0}|
      ConvertTo-Json|Set-Content -Encoding UTF8 -LiteralPath (Join-Path $out.FullName 'failure.json')
    throw
} finally {
    Disable-LocalUser -Name 'lyb06builder'
    if ($taskCreated) { Stop-ScheduledTask -TaskName $owned -ErrorAction SilentlyContinue; Unregister-ScheduledTask -TaskName $owned -Confirm:$false }
    $remaining=@(Get-CimInstance Win32_Process -Filter "Name = 'codex.exe' OR Name = 'powershell.exe'"|Where-Object {
        (Invoke-CimMethod -InputObject $_ -MethodName GetOwnerSid -ErrorAction SilentlyContinue).Sid -eq $sid
    })
    foreach ($process in $remaining) { & taskkill.exe /PID $process.ProcessId /T /F|Out-Null }
    if ($ruleCreated) { Remove-NetFirewallRule -Name $owned }
    @{account_disabled=(!(Get-LocalUser -Name 'lyb06builder').Enabled);password_changed=$false;
      task_absent=(!(Get-ScheduledTask -TaskName $owned -ErrorAction SilentlyContinue));
      firewall_rule_absent=(!(Get-NetFirewallRule -Name $owned -ErrorAction SilentlyContinue));
      real_utc=[DateTime]::UtcNow.ToString('o');model_calls=0;docker_commands=0}|
      ConvertTo-Json|Set-Content -Encoding UTF8 -LiteralPath (Join-Path $out.FullName 'cleanup.json')
}
