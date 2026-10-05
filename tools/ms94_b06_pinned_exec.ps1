# Shared process construction for the pinned B06 exec transport and its EOF smoke.
# Constructing a process conveys no model-call authority. Caller owns the account,
# WFP policy, deadline, credentials, stdin and cleanup.
function Test-B06OtherProgramEgress {
param([Management.Automation.PSCredential]$Credential,[string]$Runtime)
    $observations=@()
    foreach ($address in @('127.0.0.1','::1')) {
        $ip=[Net.IPAddress]::Parse($address)
        $listener=New-Object Net.Sockets.TcpListener($ip,0)
        $process=New-Object Diagnostics.Process
        try {
            $listener.Start();$port=$listener.LocalEndpoint.Port
            $positive=New-Object Net.Sockets.TcpClient($ip.AddressFamily)
            try { $positive.Connect($ip,$port);$accepted=$listener.AcceptTcpClient();$accepted.Dispose() }
            finally { $positive.Dispose() }
            $command='$i=[Security.Principal.WindowsIdentity]::GetCurrent();$ip=[Net.IPAddress]::Parse('''+$address+''');$c=New-Object Net.Sockets.TcpClient($ip.AddressFamily);$r=@{identity_sid=$i.User.Value;address='''+$address+''';connected=$false};try{$c.Connect($ip,'+$port+');$r.connected=$true}catch{$e=$_.Exception;while($e.InnerException){$e=$e.InnerException};$r.error=$e.NativeErrorCode}finally{$c.Dispose()};$r|ConvertTo-Json -Compress'
            $start=New-Object Diagnostics.ProcessStartInfo
            $start.FileName=$Runtime;$start.Arguments='-NoProfile -NonInteractive -Command '+$command
            $start.UseShellExecute=$false;$start.CreateNoWindow=$true;$start.WindowStyle='Hidden'
            $identity=$Credential.GetNetworkCredential()
            $start.UserName=$identity.UserName;$start.Domain=$identity.Domain;$start.Password=$Credential.Password
            $start.LoadUserProfile=$true;$start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true
            $process.StartInfo=$start
            if (!$process.Start()) { throw 'Network negative probe did not start' }
            $stdout=$process.StandardOutput.ReadToEndAsync();$stderr=$process.StandardError.ReadToEndAsync()
            if (!$process.WaitForExit(10000)) { throw 'Network negative probe timeout' }
            if ($process.ExitCode -ne 0) { throw ('Network negative probe failed: '+$stderr.Result) }
            $observation=$stdout.Result|ConvertFrom-Json
            if ($observation.connected -or $observation.error -ne 10013) { throw 'Other program egress was not denied with WSAEACCES' }
            $observations+=@{address=$address;identity_sid=$observation.identity_sid;error=$observation.error;connected=$false;host_positive_connected=$true}
        } finally {
            if ($process.Id -and !$process.HasExited) { & taskkill.exe /PID $process.Id /T /F|Out-Null }
            $process.Dispose();$listener.Stop()
        }
    }
    return $observations
}

function New-B06PinnedExecStartInfo {
param([Parameter(Mandatory=$true)]$Policy,
      [Parameter(Mandatory=$true)][Management.Automation.PSCredential]$Credential,
      [Parameter(Mandatory=$true)][string]$WorkingDirectory,
      [Parameter(Mandatory=$true)][string]$CodexHome)
    if ($Policy.codex_path -ne 'C:\Program Files\Lightyear\Codex\0.160.0\codex.exe' -or
        $Policy.codex_sha256 -ne '4b01d5920e6785614727443bbecf343f4dedbb7347052b72ba805aab6353ef01' -or
        (Get-FileHash -LiteralPath $Policy.codex_path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Policy.codex_sha256) {
        throw 'Pinned Codex path or bytes differ'
    }
    $start=New-Object Diagnostics.ProcessStartInfo
    $start.FileName=$Policy.codex_path
    $start.Arguments='exec --ignore-user-config --disable shell_tool --disable apps --disable multi_agent --config web_search="disabled" --config approval_policy="never" --json --ephemeral --skip-git-repo-check --sandbox read-only -'
    $start.WorkingDirectory=$WorkingDirectory
    $start.UseShellExecute=$false
    $identity=$Credential.GetNetworkCredential()
    $start.UserName=$identity.UserName;$start.Domain=$identity.Domain;$start.Password=$Credential.Password
    $start.LoadUserProfile=$true;$start.CreateNoWindow=$true;$start.WindowStyle='Hidden'
    $start.RedirectStandardInput=$true;$start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true
    $start.EnvironmentVariables['CODEX_HOME']=$CodexHome
    foreach ($name in @('OPENAI_API_KEY','AZURE_OPENAI_API_KEY','CODEX_API_KEY','CODEX_AUTH_JSON')) {
        $start.EnvironmentVariables.Remove($name)
    }
    return $start
}

function Invoke-B06PinnedExecEof {
param($Policy,[Management.Automation.PSCredential]$Credential,[string]$Directory,[string]$Results)
    $probeCodexHome=Join-Path $Results 'exec-home'
    if (Test-Path -LiteralPath $probeCodexHome) { throw 'Fresh exec home required' }
    $process=New-Object Diagnostics.Process
    $process.StartInfo=New-B06PinnedExecStartInfo -Policy $Policy -Credential $Credential -WorkingDirectory $Directory -CodexHome $probeCodexHome
    try {
        [IO.Directory]::CreateDirectory($probeCodexHome)|Out-Null
        if (!$process.Start()) { throw 'Exec did not start' }
        $stdout=$process.StandardOutput.ReadToEndAsync();$stderr=$process.StandardError.ReadToEndAsync()
        # Deliberately no bytes, prompt, model request or auth. Firewall additionally
        # blocks this binary during the complete probe.
        $process.StandardInput.Close()
        if (!$process.WaitForExit(30000)) { throw 'Empty-stdin exec timeout' }
        $output=$stdout.Result;$errorText=$stderr.Result
        [IO.File]::WriteAllText((Join-Path $Results 'exec-stdout.log'),$output)
        [IO.File]::WriteAllText((Join-Path $Results 'exec-stderr.log'),$errorText)
        @{exit_code=$process.ExitCode;stdin_bytes=0;stdout_bytes=[Text.Encoding]::UTF8.GetByteCount($output);
          arguments=$process.StartInfo.Arguments}|ConvertTo-Json|Set-Content -Encoding UTF8 -LiteralPath (Join-Path $Results 'exec-exit.json')
        if ($process.ExitCode -ne 1 -or $output -ne '' -or $errorText -notmatch '(?m)^No prompt provided via stdin\.\r?$') {
            throw 'Exec did not reject missing prompt before model protocol'
        }
        return @{artifact_type='ms94-b06-exec-eof/1';codex_path=$Policy.codex_path;codex_sha256=$Policy.codex_sha256;
            account_sid=$Policy.account_sid;pid=$process.Id;arguments=$process.StartInfo.Arguments;
            stdin_bytes=0;stdout_bytes=[Text.Encoding]::UTF8.GetByteCount($output);exit_code=$process.ExitCode;
            missing_prompt_rejected=$true;model_calls=0;prompt_sent=$false}
    } finally {
        if ($process.Id -and !$process.HasExited) { & taskkill.exe /PID $process.Id /T /F|Out-Null }
        $process.Dispose()
    }
}
