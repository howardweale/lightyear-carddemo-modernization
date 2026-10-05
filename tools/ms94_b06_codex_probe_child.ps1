# Trusted host RPC client; Codex itself is launched under the supplied account.
function Invoke-B06CodexAccountProtocol {
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$Directory,
      [Parameter(Mandatory=$true)][Management.Automation.PSCredential]$Credential)
$ErrorActionPreference='Stop'
$policy=Get-Content -LiteralPath (Join-Path $Directory 'policy.json') -Raw|ConvertFrom-Json
$env:CODEX_HOME=Join-Path $policy.results_directory 'codex-home'
$env:OPENAI_API_KEY=$null
$env:AZURE_OPENAI_API_KEY=$null
$env:CODEX_API_KEY=$null
$env:CODEX_AUTH_JSON=$null
$cli=Join-Path $Directory 'codex.exe'
if ((Get-FileHash -LiteralPath $cli -Algorithm SHA256).Hash.ToLowerInvariant() -ne $policy.codex_sha256) { throw 'Codex bytes changed' }
$start=New-Object Diagnostics.ProcessStartInfo
$start.FileName=$cli
# app-server has no --ignore-user-config flag. A fresh, empty CODEX_HOME
# supplies no inherited settings or credentials; the exec transport is separate.
$start.Arguments='--disable shell_tool --disable apps --disable multi_agent -c web_search="disabled" -c approval_policy="never" app-server'
$start.WorkingDirectory=$Directory
$start.UseShellExecute=$false
$networkCredential=$Credential.GetNetworkCredential()
$start.UserName=$networkCredential.UserName
$start.Domain=$networkCredential.Domain
$start.Password=$Credential.Password
$start.LoadUserProfile=$true
$start.CreateNoWindow=$true
$start.WindowStyle=[Diagnostics.ProcessWindowStyle]::Hidden
$start.RedirectStandardInput=$true
$start.RedirectStandardOutput=$true
$start.RedirectStandardError=$true
$process=New-Object Diagnostics.Process
$process.StartInfo=$start
$messages=New-Object Collections.Generic.List[object]
$reads=New-Object Collections.Generic.List[object]
function Send-ProbeRequest($message) {
    if ($message.method -notin @('initialize','initialized','command/exec')) { throw 'Non-probe RPC refused' }
    $messages.Add($message)
    $process.StandardInput.WriteLine(($message|ConvertTo-Json -Depth 12 -Compress))
    $process.StandardInput.Flush()
    if ($message.method -eq 'initialized') { return }
    while ($true) {
        $pending=$process.StandardOutput.ReadLineAsync()
        if (!$pending.Wait(30000)) { throw 'Codex RPC timed out' }
        $line=$pending.Result
        if ($null -eq $line) { throw 'Codex exited before response' }
        $response=$line|ConvertFrom-Json
        if ($response.method -match 'turn|thread|item') { throw 'Unexpected model protocol event' }
        if ($null -ne $response.id -and $response.id -eq $message.id) {
            if ($response.error) { throw ('Codex RPC error '+$response.error.code) }
            return $response.result
        }
    }
}
try {
    if (!$process.Start()) { throw 'Codex did not start' }
    $stderr=$process.StandardError.ReadToEndAsync()
    $codexPid=$process.Id
    $initialized=Send-ProbeRequest @{id=1;method='initialize';params=@{clientInfo=@{name='b06-zero-model-probe';version='1.0'}}}
    Send-ProbeRequest @{method='initialized'}
    for ($index=0;$index -lt 4;$index++) {
        # Get-Content returns no record values, even if a denial fails.
        # Parent ancestry is collected inside the child while Codex is alive.
        $command='$ErrorActionPreference=''Stop'';$p=Get-Content -Raw -LiteralPath ''policy.json''|ConvertFrom-Json;$i=[Security.Principal.WindowsIdentity]::GetCurrent();$me=Get-CimInstance Win32_Process -Filter (''ProcessId=''+$PID);$parent=Get-CimInstance Win32_Process -Filter (''ProcessId=''+$me.ParentProcessId);$owner=Invoke-CimMethod -InputObject $parent -MethodName GetOwnerSid;$a=(New-Object Security.Principal.WindowsPrincipal($i)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator);$r=@{identity_sid=$i.User.Value;administrator=$a;group_sids=@($i.Groups|ForEach-Object {$_.Value});process_id=$PID;parent_pid=$parent.ProcessId;parent_name=$parent.Name;parent_sid=$owner.Sid};try{$null=Get-Content -Raw -ErrorAction Stop -LiteralPath $p.read_targets['+$index+'];$r.opened=$true;$r.error=0}catch{$e=$_.Exception;while($e.InnerException){$e=$e.InnerException};$r.opened=$false;$r.hresult=$e.HResult;$r.native_error=$e.NativeErrorCode;$r.error=if($e -is [ComponentModel.Win32Exception]){$e.NativeErrorCode}else{$e.HResult -band 65535};$r.exception_type=$e.GetType().FullName;$r.category=$_.CategoryInfo.Category.ToString()};$r|ConvertTo-Json -Compress'
        $result=Send-ProbeRequest @{id=($index+2);method='command/exec';params=@{
            command=@($policy.powershell,'-NoProfile','-NonInteractive','-Command',$command)
            cwd=$Directory;timeoutMs=15000;sandboxPolicy=@{type='externalSandbox';networkAccess='restricted'}}}
        if ($result.exitCode -ne 0) { throw ('Codex child read failed: '+$index) }
        $read=$result.stdout|ConvertFrom-Json
        if ($read.identity_sid -ne $policy.account_sid -or $read.parent_sid -ne $policy.account_sid -or
            $read.parent_pid -ne $codexPid -or $read.parent_name -ne 'codex.exe') { throw 'Read is not in admitted Codex process tree' }
        $reads.Add($read)
    }
    $process.StandardInput.Close()
    if (!$process.WaitForExit(10000)) { throw 'Codex did not exit after stdin EOF' }
    if ($process.ExitCode -ne 0) { throw 'Codex exited unsuccessfully' }
    @{artifact_type='ms94-b06-codex-process-observation/1';account_sid=$policy.account_sid;
      codex_pid=$codexPid;codex_sha256=$policy.codex_sha256;user_agent=$initialized.userAgent;reads=@($reads.ToArray());
      requests=@($messages.ToArray());exit_code=$process.ExitCode;model_calls=0;prompt_sent=$false;
      network_method='temporary Windows Firewall outbound block for this copied executable';
      measurement_transport_admitted=$false}|ConvertTo-Json -Depth 15|Set-Content -Encoding UTF8 -LiteralPath (Join-Path $policy.results_directory 'observation.json')
} finally {
    if ($process.Id -and !$process.HasExited) { & taskkill.exe /PID $process.Id /T /F | Out-Null }
    if ($stderr -and $stderr.IsCompleted) { $stderr.Result|Set-Content -Encoding UTF8 -LiteralPath (Join-Path $policy.results_directory 'codex-stderr.log') }
    @{requests=@($messages.ToArray());model_calls=0;prompt_sent=$false}|ConvertTo-Json -Depth 15|Set-Content -Encoding UTF8 -LiteralPath (Join-Path $policy.results_directory 'protocol.json')
    $process.Dispose()
}

}
