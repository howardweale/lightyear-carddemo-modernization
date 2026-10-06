#Requires -RunAsAdministrator
param([Parameter(Mandatory=$true)][string]$Repository,
      [Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference='Stop'
$account=Get-LocalUser -Name 'lyb06builder'
if ($account.Enabled) { throw 'Expected disabled dedicated builder' }
if (Test-Path -LiteralPath $OutputDirectory) { throw 'Fresh output directory required' }
$sid=$account.SID.Value
$authDirectory='C:\ProgramData\Lightyear\B06Auth\0.160.0'
$out=New-Item -ItemType Directory -Path $OutputDirectory
$operatorSid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
& icacls.exe $out.FullName /inheritance:r /grant:r '*S-1-5-32-544:(OI)(CI)F' "*$($operatorSid):(OI)(CI)F" "*$($sid):(OI)(CI)M" | Out-Null
if ($LASTEXITCODE) { throw 'Output ACL failed' }
# This folder is authentication state only: never copy another account's auth.json.
if (!(Test-Path -LiteralPath $authDirectory)) { New-Item -ItemType Directory -Path $authDirectory -Force|Out-Null }
if ((Get-Item -LiteralPath $authDirectory).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Auth path must not be a link' }
if (Test-Path -LiteralPath (Join-Path $authDirectory 'config.toml')) { throw 'Dedicated login home must not contain user configuration' }
& icacls.exe $authDirectory /inheritance:r /grant:r '*S-1-5-32-544:(OI)(CI)F' "*$($sid):(OI)(CI)F" | Out-Null
if ($LASTEXITCODE) { throw 'Authentication ACL failed' }
$allowed=@('S-1-5-32-544',$sid)
foreach ($target in @($authDirectory,(Join-Path $authDirectory 'auth.json'))) {
    if (!(Test-Path -LiteralPath $target)) { continue }
    if ((Get-Item -LiteralPath $target).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Authentication path must not be a link' }
    foreach ($rule in (Get-Acl -LiteralPath $target).Access) {
        if ($rule.AccessControlType -eq 'Allow' -and $rule.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value -notin $allowed) {
            throw 'Unexpected authentication reader; correct ACL before supervised sign-in'
        }
    }
}
$cli='C:\Program Files\Lightyear\Codex\0.160.0\codex.exe'
if ((Get-FileHash -LiteralPath $cli -Algorithm SHA256).Hash.ToLowerInvariant() -ne '4b01d5920e6785614727443bbecf343f4dedbb7347052b72ba805aab6353ef01') { throw 'Pinned client differs' }
$password=Read-Host 'Choose a fresh temporary lyb06builder password' -AsSecureString
$login=$null;$statusProcess=$null
try {
    Set-LocalUser -Name 'lyb06builder' -Password $password
    Enable-LocalUser -Name 'lyb06builder'
    # CreateProcessWithLogonW runs the native executable directly, never a .ps1
    # under the builder. The supervised login window is intentionally visible.
    $start=New-Object Diagnostics.ProcessStartInfo
    $start.FileName=$cli;$start.Arguments='-c cli_auth_credentials_store=\"file\" login --device-auth'
    $start.WorkingDirectory=$authDirectory;$start.UseShellExecute=$false;$start.CreateNoWindow=$false
    $start.UserName='lyb06builder';$start.Domain=$env:COMPUTERNAME;$start.Password=$password;$start.LoadUserProfile=$true
    $start.EnvironmentVariables['CODEX_HOME']=$authDirectory
    foreach ($name in @('OPENAI_API_KEY','AZURE_OPENAI_API_KEY','CODEX_API_KEY','CODEX_AUTH_JSON','CODEX_ACCESS_TOKEN')) { $start.EnvironmentVariables.Remove($name) }
    $login=New-Object Diagnostics.Process;$login.StartInfo=$start
    if (!$login.Start()) { throw 'Supervised builder login did not start' }
    if (!$login.WaitForExit(600000)) { throw 'Supervised login exceeded ten minutes' }
    if ($login.ExitCode -ne 0) { throw 'Builder login did not complete' }
    $start.Arguments='-c cli_auth_credentials_store=\"file\" login status'
    $start.CreateNoWindow=$true;$start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true
    $statusProcess=New-Object Diagnostics.Process;$statusProcess.StartInfo=$start
    if (!$statusProcess.Start()) { throw 'Builder status did not start' }
    $stdout=$statusProcess.StandardOutput.ReadToEndAsync();$stderr=$statusProcess.StandardError.ReadToEndAsync()
    if (!$statusProcess.WaitForExit(20000)) { throw 'Builder login status deadline exceeded' }
    $text=$stdout.Result+"`n"+$stderr.Result
    $classification='unrecognized'
    if ($statusProcess.ExitCode -eq 0 -and $text -match '(?m)^Logged in using ChatGPT') { $classification='logged-in-chatgpt' }
    elseif ($statusProcess.ExitCode -eq 0 -and $text -match '(?m)^Logged in using an API key') { $classification='logged-in-api-key' }
    if ($classification -eq 'unrecognized') { throw 'Recognized successful login status required' }
    # Never save raw status or device-login output.
    @{artifact_type='ms94-b06-supervised-login/1';account_sid=$sid;codex_path=$cli;
      credential_store='file';codex_home=$authDirectory;status=$classification;model_calls=0;
      credentials_copied=$false;real_utc=[DateTime]::UtcNow.ToString('o')}|ConvertTo-Json|
      Set-Content -LiteralPath (Join-Path $out.FullName 'status.json') -Encoding UTF8
    $authFile=Join-Path $authDirectory 'auth.json'
    if (!(Test-Path -LiteralPath $authFile)) { throw 'File authentication missing' }
    & icacls.exe $authFile /inheritance:r /grant:r '*S-1-5-32-544:F' "*$($sid):F" | Out-Null
    if ($LASTEXITCODE) { throw 'Credential file ACL failed' }
    $acl=Get-Acl -LiteralPath $authFile
    foreach ($rule in $acl.Access) {
        if ($rule.AccessControlType -eq 'Allow' -and $rule.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value -notin $allowed) {
            throw 'Unexpected credential reader; no login admission'
        }
    }
    Write-Host 'Builder login status recorded. No model call was made.'
} finally {
    Disable-LocalUser -Name 'lyb06builder'
    $owned=@(Get-CimInstance Win32_Process|Where-Object {
        (Invoke-CimMethod -InputObject $_ -MethodName GetOwnerSid -ErrorAction SilentlyContinue).Sid -eq $sid
    })
    foreach ($p in $owned) { & taskkill.exe /PID $p.ProcessId /T /F|Out-Null }
    foreach ($process in @($login,$statusProcess)) { if($process){$process.Dispose()} }
    $remaining=@(Get-CimInstance Win32_Process|Where-Object {
        (Invoke-CimMethod -InputObject $_ -MethodName GetOwnerSid -ErrorAction SilentlyContinue).Sid -eq $sid
    })
    @{account_disabled=(!(Get-LocalUser -Name 'lyb06builder').Enabled);owned_processes_absent=($remaining.Count -eq 0);
      credential_store='file';credentials_copied=$false;model_calls=0;docker_commands=0;
      real_utc=[DateTime]::UtcNow.ToString('o')}|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $out.FullName 'cleanup.json') -Encoding UTF8
    if ($remaining.Count) { throw 'Builder process cleanup failed' }
}
