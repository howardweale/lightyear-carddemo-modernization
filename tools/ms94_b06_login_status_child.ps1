param([Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference='Stop'
$cli='C:\Program Files\Lightyear\Codex\0.160.0\codex.exe'
if ((Get-FileHash -LiteralPath $cli -Algorithm SHA256).Hash.ToLowerInvariant() -ne '4b01d5920e6785614727443bbecf343f4dedbb7347052b72ba805aab6353ef01') { throw 'Client hash differs' }
$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
$profile=[Environment]::GetFolderPath('UserProfile')
if (!$profile -or $identity.Name -notmatch '\\lyb06builder$') { throw 'Wrong identity/profile' }
$env:CODEX_HOME=Join-Path $profile '.codex'
foreach ($variable in @('OPENAI_API_KEY','AZURE_OPENAI_API_KEY','CODEX_API_KEY','CODEX_AUTH_JSON','CODEX_ACCESS_TOKEN')) {
    [Environment]::SetEnvironmentVariable($variable,$null,'Process')
}
$rows=@()
foreach ($arguments in @('login status','login status --ignore-user-config','login -c cli_auth_credentials_store="file" status','exec --ignore-user-config --help')) {
    $p=New-Object Diagnostics.Process
    $s=New-Object Diagnostics.ProcessStartInfo
    $s.FileName=$cli;$s.Arguments=$arguments;$s.UseShellExecute=$false;$s.CreateNoWindow=$true
    $s.RedirectStandardOutput=$true;$s.RedirectStandardError=$true;$s.RedirectStandardInput=$true
    $p.StartInfo=$s
    try {
        if (!$p.Start()) { throw 'Status process did not start' }
        $p.StandardInput.Close()
        $stdout=$p.StandardOutput.ReadToEndAsync();$stderr=$p.StandardError.ReadToEndAsync()
        if (!$p.WaitForExit(20000)) { throw 'Status process timeout' }
        $text=$stdout.Result+"`n"+$stderr.Result
        $classification='unrecognized-status'
        if ($text -match '(?m)^Not logged in\s*$') {$classification='not-logged-in'}
        elseif ($text -match '(?m)^Logged in using ChatGPT') {$classification='logged-in-chatgpt'}
        elseif ($text -match '(?m)^Logged in using an API key') {$classification='logged-in-api-key'}
        elseif ($text -match "unexpected argument '--ignore-user-config'") {$classification='flag-not-supported-by-login'}
        elseif ($arguments -like 'exec *' -and $p.ExitCode -eq 0 -and $text -match 'auth still uses') {$classification='exec-help-auth-home-confirmed'}
        # Never persist stdout/stderr: login status may include credential/account details.
        $rows+=@{arguments=$arguments;exit_code=$p.ExitCode;classification=$classification;stdin_bytes=0}
    } finally {
        if ($p.Id -and !$p.HasExited) { & taskkill.exe /PID $p.Id /T /F|Out-Null }
        $p.Dispose()
    }
}
@{artifact_type='ms94-b06-account-login-status/1';account_sid=$identity.User.Value;profile=$profile;
  codex_home=$env:CODEX_HOME;auth_file_exists=(Test-Path -LiteralPath (Join-Path $env:CODEX_HOME 'auth.json'));
  checks=$rows;model_calls=0;docker_commands=0;credentials_copied=$false;credentials_printed=$false;
  logon_type='scheduled-task-S4U';keyring_password_logon_equivalence_proven=$false;real_utc=[DateTime]::UtcNow.ToString('o')} |
  ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $OutputDirectory 'status.json')
