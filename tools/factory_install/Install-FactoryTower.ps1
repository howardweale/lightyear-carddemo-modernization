#Requires -Version 5.1
#Requires -RunAsAdministrator
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$RuntimeStage,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$ManifestSHA256,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{40}$')][string]$ApprovedCommit,
    [Parameter(Mandatory=$true)][string]$OperatorSid
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$runtime = 'C:\ProgramData\Lightyear\FactoryRuntime-v1'
$data = 'C:\ProgramData\Lightyear\FactoryData-v1'
$authority = 'C:\ProgramData\Lightyear\FactoryAuthority'
$task = 'Lightyear-FactoryTower-Howard'
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
if ($identity.User.Value -ne $OperatorSid -or $OperatorSid -in @('S-1-5-18','S-1-5-19','S-1-5-20')) {
    throw 'Run elevated as the same Howard account that will own the login task; never SYSTEM or a different administrator'
}
$sid = New-Object Security.Principal.SecurityIdentifier($OperatorSid)
$stage = [IO.Path]::GetFullPath($RuntimeStage).TrimEnd('\')
function Assert-NoLink([string]$Path) {
    $item = Get-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
    while ($item) {
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Reparse point refused' }
        $parent = Split-Path -Parent $item.FullName
        if (!$parent -or $parent -eq $item.FullName) { break }
        $item = Get-Item -LiteralPath $parent -Force
    }
}
foreach ($path in @($stage,$runtime,$data,$authority)) {
    Assert-NoLink $path
    $parent = Split-Path -Parent $path
    Assert-NoLink $parent
}
foreach ($path in @($runtime,$data,$authority)) {
    if (Test-Path -LiteralPath $path) { throw 'First install requires absent destinations; preserve an existing or partial installation' }
    if ($stage.StartsWith($path+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Stage overlaps installation' }
}
if (Get-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue) { throw 'Task already exists' }
# Enumerating listeners does not contact Tower and cannot sign a journal.
if (@(Get-NetTCPConnection -State Listen -ErrorAction Stop | Where-Object LocalPort -eq 8769).Count) {
    throw 'Port 8769 is occupied; identify its owner without stopping it'
}
$manifestPath = Join-Path $stage 'manifest.json'
Assert-NoLink $manifestPath
if ((Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ManifestSHA256) { throw 'Manifest digest differs' }
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if ($manifest.schema -ne 'factory-install-bundle/1' -or $manifest.source_commit -ne $ApprovedCommit) { throw 'Wrong reviewed source commit' }
$files = @($manifest.files)
if ($files.Count -lt 5 -or $files.Count -gt 30000) { throw 'Invalid inventory size' }
$names = New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
$total = [long]0
foreach ($file in $files) {
    $relative = [string]$file.path
    if ($relative -notmatch '^[a-zA-Z0-9_. /-]+$' -or $relative -match '(^|/)\.\.?(/|$)|//|(^|/)[^/]*[. ](/|$)' -or
        [IO.Path]::IsPathRooted($relative) -or !$names.Add($relative)) { throw 'Unsafe or duplicate inventory path' }
    foreach ($part in $relative.Split('/')) {
        if ($part -match '^(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\.|$)') { throw 'Reserved Windows path' }
    }
    if ($file.sha256 -notmatch '^[0-9a-f]{64}$' -or [long]$file.bytes -lt 0) { throw 'Invalid file identity' }
    $total += [long]$file.bytes
    if ($total -gt 2GB) { throw 'Bundle exceeds size limit' }
    $source = Join-Path $stage $relative
    Assert-NoLink $source
    if (!(Test-Path -LiteralPath $source -PathType Leaf) -or (Get-Item -LiteralPath $source).Length -ne $file.bytes -or
        (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant() -ne $file.sha256) { throw 'Bundle file differs' }
}
$actual = @(Get-ChildItem -LiteralPath $stage -Recurse -Force -File)
if ($actual.Count -ne $files.Count+1) { throw 'Unlisted bundle files' }
foreach ($item in Get-ChildItem -LiteralPath $stage -Recurse -Force) { Assert-NoLink $item.FullName }
foreach ($required in @('python/python.exe','app/tools/factory_install/entry.py','Start-FactoryTower.ps1',
    'app/src/lightyear_control_tower/server.py','app/knowledge/viewer/decision-console.html')) {
    if (!$names.Contains($required)) { throw 'Required runtime member missing' }
}
function Set-DirectoryAcl([string]$Path,[bool]$Runtime) {
    $acl = New-Object Security.AccessControl.DirectorySecurity
    $acl.SetAccessRuleProtection($true,$false)
    $owner = $sid
    if ($Runtime) { $owner = New-Object Security.Principal.SecurityIdentifier('S-1-5-32-544') }
    $acl.SetOwner($owner)
    $rights = [Security.AccessControl.FileSystemRights]::FullControl
    if ($Runtime) { $rights = [Security.AccessControl.FileSystemRights]::ReadAndExecute }
    $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($sid,$rights,'ContainerInherit,ObjectInherit','None','Allow')))
    if ($Runtime) {
        $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($owner,'FullControl','ContainerInherit,ObjectInherit','None','Allow')))
    }
    Set-Acl -LiteralPath $Path -AclObject $acl
}
# No provision, login, keys, evidence import, signing, consumer setting or start.
# Failure deliberately leaves a disabled, incomplete installation for inspection.
New-Item -ItemType Directory -Path $runtime | Out-Null
Set-DirectoryAcl $runtime $true
foreach ($file in $files) {
    $destination = Join-Path $runtime $file.path
    [IO.Directory]::CreateDirectory((Split-Path -Parent $destination)) | Out-Null
    Copy-Item -LiteralPath (Join-Path $stage $file.path) -Destination $destination
    if ((Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant() -ne $file.sha256) { throw 'Installed bytes differ' }
}
Copy-Item -LiteralPath $manifestPath -Destination (Join-Path $runtime 'manifest.json')
# Remove source ACLs/owners throughout: service user receives inherited RX only.
& icacls.exe ($runtime+'\*') /reset /T /Q | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Runtime inherited permissions failed' }
& icacls.exe $runtime /setowner '*S-1-5-32-544' /T /Q | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Runtime owner failed' }
foreach ($path in @($data,$authority)) {
    New-Item -ItemType Directory -Path $path | Out-Null
    Set-DirectoryAcl $path $false
}
$action = New-ScheduledTaskAction -Execute "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -Argument (
    '-NoProfile -NonInteractive -WindowStyle Hidden -File "'+(Join-Path $runtime 'Start-FactoryTower.ps1')+'"'
) -WorkingDirectory $runtime
$principal = New-ScheduledTaskPrincipal -UserId $OperatorSid -LogonType Interactive -RunLevel Limited
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $OperatorSid
$settings = New-ScheduledTaskSettingsSet -Disable -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName $task -Action $action -Principal $principal -Trigger $trigger -Settings $settings -Description 'Factory Tower; installed disabled. Howard provisions and enables separately.' | Out-Null
$registered = Get-ScheduledTask -TaskName $task
if ($registered.Settings.Enabled -or $registered.Principal.RunLevel -ne 'Limited' -or $registered.Principal.UserId -ne $OperatorSid) {
    Disable-ScheduledTask -TaskName $task | Out-Null
    throw 'Task principal or disabled state differs'
}
$receipt = @{
    schema='factory-install-receipt/1';source_commit=$ApprovedCommit;manifest_sha256=$ManifestSHA256
    runtime=$runtime;data=$data;authority=(Join-Path $authority 'authority.json')
    operator_sid=$OperatorSid;task=$task;task_enabled=$false;started=$false;keys_created=$false
    evidence_imported=$false;signed_backfill=$false;signed_only_activated=$false
    installed_at=[DateTime]::UtcNow.ToString('o')
}
[IO.File]::WriteAllText((Join-Path $data 'installation-receipt.json'),($receipt|ConvertTo-Json),[Text.UTF8Encoding]::new($false))
Write-Output 'Installed disabled. No identity, keys, evidence, signatures or activation created.'