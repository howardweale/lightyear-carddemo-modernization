# CI-only integration checks on an expendable Windows runner.
#Requires -RunAsAdministrator
param([Parameter(Mandatory=$true)][string]$Stage,[Parameter(Mandatory=$true)][string]$Commit)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$installer=Join-Path $PSScriptRoot 'Install-FactoryTower.ps1'
$sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$roots=@('C:\ProgramData\Lightyear\FactoryRuntime-v1','C:\ProgramData\Lightyear\FactoryData-v1','C:\ProgramData\Lightyear\FactoryAuthority')
$task='Lightyear-FactoryTower-Howard'
$hash=(Get-FileHash -LiteralPath (Join-Path $Stage 'manifest.json') -Algorithm SHA256).Hash.ToLowerInvariant()
function Assert([bool]$Condition,[string]$Message) { if (!$Condition) { throw $Message } }
function Refuses([scriptblock]$Operation) {
    $refused=$false
    try { & $Operation } catch { $refused=$true }
    Assert $refused 'Unsafe installation was accepted'
}
foreach($path in $roots) { Assert (!(Test-Path -LiteralPath $path)) 'Runner must be fresh' }
Refuses { & $installer -RuntimeStage $Stage -ManifestSHA256 ('0'*64) -ApprovedCommit $Commit -OperatorSid $sid }
Refuses { & $installer -RuntimeStage $Stage -ManifestSHA256 $hash -ApprovedCommit ('0'*40) -OperatorSid $sid }
Refuses { & $installer -RuntimeStage $Stage -ManifestSHA256 $hash -ApprovedCommit $Commit -OperatorSid 'S-1-5-18' }
foreach($path in $roots) { Assert (!(Test-Path -LiteralPath $path)) 'Rejected preflight mutated destinations' }
$bad=Join-Path $env:RUNNER_TEMP 'factory-bad-inventory'
New-Item -ItemType Directory -Path $bad | Out-Null
$malicious=@{schema='factory-install-bundle/1';source_commit=$Commit;files=@(
    @{path='../escape';bytes=0;sha256=('0'*64)},
    @{path='a';bytes=0;sha256=('0'*64)},@{path='b';bytes=0;sha256=('0'*64)},
    @{path='c';bytes=0;sha256=('0'*64)},@{path='d';bytes=0;sha256=('0'*64)}
)}
[IO.File]::WriteAllText((Join-Path $bad 'manifest.json'),($malicious|ConvertTo-Json -Depth 5),[Text.UTF8Encoding]::new($false))
$badHash=(Get-FileHash (Join-Path $bad 'manifest.json') -Algorithm SHA256).Hash.ToLowerInvariant()
Refuses { & $installer -RuntimeStage $bad -ManifestSHA256 $badHash -ApprovedCommit $Commit -OperatorSid $sid }
foreach($path in $roots) { Assert (!(Test-Path -LiteralPath $path)) 'Path escape mutated destinations' }
& $installer -RuntimeStage $Stage -ManifestSHA256 $hash -ApprovedCommit $Commit -OperatorSid $sid
$t=Get-ScheduledTask -TaskName $task
Assert (!$t.Settings.Enabled) 'Task enabled unexpectedly'
Assert ($t.Principal.UserId -eq $sid -and $t.Principal.RunLevel -eq 'Limited' -and $t.Principal.LogonType -eq 'Interactive') 'Wrong task identity'
Assert ($t.Actions.Execute -eq "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe") 'Unexpected executable'
Assert ($t.Triggers.UserId -eq $sid) 'Wrong login trigger'
foreach($path in Get-ChildItem -LiteralPath $roots[0] -Recurse -Force) {
    $acl=Get-Acl -LiteralPath $path.FullName
    Assert ($acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -eq 'S-1-5-32-544') 'Runtime owner differs'
    foreach($ace in $acl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])) {
        if ($ace.IdentityReference.Value -eq $sid) {
            Assert ($ace.AccessControlType -eq 'Allow') 'Unexpected runtime deny rule'
            Assert (($ace.FileSystemRights -band [Security.AccessControl.FileSystemRights]::Write) -eq 0) 'Service can write runtime'
            Assert (($ace.FileSystemRights -band [Security.AccessControl.FileSystemRights]::ChangePermissions) -eq 0) 'Service can change runtime ACL'
        }
    }
}
$acl=Get-Acl -LiteralPath $roots[2]
Assert $acl.AreAccessRulesProtected 'Authority inherits broad access'
$rules=@($acl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier]))
Assert ($rules.Count -eq 1 -and $rules[0].IdentityReference.Value -eq $sid -and $rules[0].AccessControlType -eq 'Allow') 'Authority is not Howard-only'
Assert (@(Get-ChildItem -LiteralPath $roots[2] -Force).Count -eq 0) 'Installer created authority material'
Assert (!(Test-Path (Join-Path $roots[1] 'snapshot'))) 'Installer imported evidence'
Refuses { & (Join-Path $roots[0] 'Start-FactoryTower.ps1') }
Assert (@(Get-NetTCPConnection -State Listen | Where-Object LocalPort -eq 8769).Count -eq 0) 'Unexpected service start'
Refuses { & $installer -RuntimeStage $Stage -ManifestSHA256 $hash -ApprovedCommit $Commit -OperatorSid $sid }
Assert (@(Get-ChildItem -LiteralPath $roots[2] -Force).Count -eq 0) 'Repeat call changed authority'
& (Join-Path $roots[0] 'python/python.exe') -I -B (Join-Path $roots[0] 'app/tools/factory_install/entry.py') tower --help | Out-Null
Assert ($LASTEXITCODE -eq 0) 'Packaged runtime cannot load CLI'
Write-Output 'CI installer checks passed; no authority, signatures, activation or running service.'