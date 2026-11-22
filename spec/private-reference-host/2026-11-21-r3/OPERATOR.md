# H1 operator checklist supplement — C06

For future sessions after review, use this complete section in place of the Windows custody section of the [H1-r2 checklist](../2026-11-21-r2/OPERATOR.md). Use H1-r2 for Linux preparation and all other admission requirements.

## Windows custody at both checkpoints

Use the separate Windows administrator account for service administration. The service name is `CodexSandboxService.OpenAI.Codex`. Its process image is `codex-windows-sandbox-service`. Service commands require the service name. Carry the observation under the existing `no_codex_background_or_autostart` key. The preflight and postflight checks each require it to be true. Preserve the independent process-visibility, stopped and continuity declarations. A later successful observation cannot establish uninterrupted custody retroactively.

### Read-only activity probe

Use elevated 64-bit Windows PowerShell. Load this function into the same shell used for each checkpoint or the separate positive self-test. An account, process or session query error stops the check. The function emits two booleans; keep raw inventory on the host.

~~~powershell
function Get-C06SandboxActivity {
    [CmdletBinding()]
    param()
    $expectedNames = @('CodexSandboxOffline', 'CodexSandboxOnline')
    $expectedSids = @()
    $qualifiedNames = @()
    $sessionMatch = $false
    foreach ($expectedName in $expectedNames) {
        $account = Get-LocalUser -Name $expectedName -ErrorAction Stop
        if ($account.Name -cne $expectedName -or -not $account.SID) {
            throw 'C06-sandbox-account-identity'
        }
        $sid = $account.SID.Value
        $expectedSids += $sid
        $qualifiedNames += $account.SID.Translate([System.Security.Principal.NTAccount]).Value
        $cimAccount = @(Get-CimInstance -ClassName Win32_UserAccount -Filter "LocalAccount = TRUE AND SID = '$sid'" -ErrorAction Stop)
        if ($cimAccount.Count -ne 1 -or $cimAccount[0].SID -ne $sid -or
            $cimAccount[0].Name -cne $expectedName) { throw 'C06-sandbox-account-identity' }
        $sessions = @(Get-CimAssociatedInstance -InputObject $cimAccount[0] -Association Win32_LoggedOnUser -ResultClassName Win32_LogonSession -ErrorAction Stop)
        if ($sessions.Count -gt 0) { $sessionMatch = $true }
    }
    if (@($expectedSids | Sort-Object -Unique).Count -ne 2) { throw 'C06-sandbox-account-identity' }

    $processes = @(Get-Process -IncludeUserName -ErrorAction Stop)
    if (-not $processes.Count -or $PID -notin $processes.Id) { throw 'C06-process-visibility' }
    $matchingProcesses = @($processes | Where-Object { $qualifiedNames -icontains $_.UserName })
    [pscustomobject]@{ VisibleOwner = ($matchingProcesses.Count -gt 0); LogonSession = $sessionMatch }
}
~~~

All process images and Windows sessions are in scope. A protected process may have a blank owner. The independent session query looks up both sandbox SIDs across all logon types and does not require opening such a process. A sandbox logon session alone refuses the private checkpoint, even if it outlives its last visible process. These checks observe two snapshots; the existing continuity and all-session visibility declarations still apply. [Microsoft Win32_LoggedOnUser association](https://learn.microsoft.com/en-us/windows/win32/cimwin32prov/win32-loggedonuser)

When separately authorized to open the private window, fully close Codex and its helpers. In elevated PowerShell disable startup first, then stop the service. Perform these commands only as the operator.

~~~powershell
$name = 'CodexSandboxService.OpenAI.Codex'
Set-Service -Name $name -StartupType Disabled -ErrorAction Stop
Stop-Service -Name $name -ErrorAction Stop
~~~

Run this read-only block **before any private step and again at postflight**. Use the existing all-session inventory to include known helpers whose image name does not identify Codex. Treat incomplete visibility, ambiguous service identity, another Codex service eligible for startup, or a process that respawns as a refusal. Retain raw observations locally and return only reviewed custody booleans. Do not print the raw service/process inventory in the public return.

~~~powershell
$services = @(Get-CimInstance Win32_Service -ErrorAction Stop)
$target = @($services | Where-Object Name -eq 'CodexSandboxService.OpenAI.Codex')
$related = @($services | Where-Object {
    $_.Name -match 'codex' -or $_.DisplayName -match 'codex' -or $_.PathName -match 'codex'
})
if ($target.Count -ne 1) { throw 'C06-service-identity' }
foreach ($service in $related) {
    if ($service.State -ne 'Stopped' -or $service.StartMode -ne 'Disabled') {
        throw 'C06-service-state'
    }
}
$running = @(Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object { $_.Name -match 'codex' })
if ($running.Count) { throw 'C06-process-running' }

$activity = Get-C06SandboxActivity -ErrorAction Stop
if ($activity.VisibleOwner) { throw 'C06-sandbox-process-running' }
if ($activity.LogonSession) { throw 'C06-sandbox-logon-session' }
~~~

Run the complete block at both checkpoints. Only a successful observation contributes to the existing C06 boolean. Keep SIDs, account translations, process information, session IDs and any query diagnostics local.

Close the private window and complete postflight before restoring the normal service configuration in elevated PowerShell. Restore the observed default for this named service and verify both settings.

~~~powershell
$name = 'CodexSandboxService.OpenAI.Codex'
Set-Service -Name $name -StartupType Automatic -ErrorAction Stop
Start-Service -Name $name -ErrorAction Stop
$state = Get-CimInstance Win32_Service -Filter "Name='CodexSandboxService.OpenAI.Codex'" -ErrorAction Stop
if ($state.State -ne 'Running' -or $state.StartMode -ne 'Auto') { throw 'service-restore-incomplete' }
~~~

## Positive control before the next private session

Outside any private window, with Codex running normally, Howard may load the function above and run only this read-only self-test in elevated 64-bit Windows PowerShell. Leave services and accounts in their normal state. Use an occasion when Codex is known to be using a sandbox account if available. The self-test is separate from either private checkpoint.

~~~powershell
$activity = Get-C06SandboxActivity -ErrorAction Stop
if ($activity.LogonSession -and $activity.VisibleOwner) {
    'C06-self-test-activity-detected-owner-and-session'
} elseif ($activity.LogonSession) {
    'C06-self-test-activity-detected-session'
} elseif ($activity.VisibleOwner) {
    'C06-self-test-activity-detected-session-unconfirmed'
} else {
    'C06-self-test-no-activity-observed'
}
~~~

Either session-positive result demonstrates detection on that host; an owner match alone detects activity but leaves the session path unproven. If a known sandbox workload is active and no session is detected, report the discrepancy for review before relying on the session path. An empty observation without a known active workload is inconclusive. Errors are failures to observe. Return only the fixed self-test result. A positive control cannot serve as a passing private C06 checkpoint.
