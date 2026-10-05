# Pure command construction: no launches, ACL changes or credentials.
function Get-B06ProbeCommands {
    $loadPolicy = '$ErrorActionPreference=''Stop'';$p=Get-Content -Raw -LiteralPath ''policy.json''|ConvertFrom-Json;'
    $identity = '$i=[Security.Principal.WindowsIdentity]::GetCurrent();$a=(New-Object Security.Principal.WindowsPrincipal($i)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator);'
    $commands = @()
    $commands += $loadPolicy + $identity + '@{identity_sid=$i.User.Value;identity_name=$i.Name;administrator=$a;group_sids=@($i.Groups|ForEach-Object {$_.Value})}|ConvertTo-Json|Set-Content -Encoding UTF8 -LiteralPath (Join-Path $p.results_directory ''identity.json'')'
    for ($index=0; $index -lt 4; $index++) {
        $commands += $loadPolicy + $identity + '$r=@{identity_sid=$i.User.Value;administrator=$a};try{$null=Get-Content -Raw -ErrorAction Stop -LiteralPath $p.read_targets['+$index+'];$r.opened=$true;$r.error=0}catch{$e=$_.Exception;while($e.InnerException){$e=$e.InnerException};$r.opened=$false;$r.hresult=$e.HResult;$r.native_error=$e.NativeErrorCode;$r.error=if($e -is [ComponentModel.Win32Exception]){$e.NativeErrorCode}else{$e.HResult -band 65535};$r.exception_type=$e.GetType().FullName;$r.category=$_.CategoryInfo.Category.ToString()};$r|ConvertTo-Json|Set-Content -Encoding UTF8 -LiteralPath (Join-Path $p.results_directory ''read-'+$index+'.json'')'
    }
    return $commands
}

function Invoke-B06ReadCommand {
    param([string]$Runtime,[string]$Command,[string]$WorkingDirectory,
          [string]$OutputLog,[string]$ErrorLog,[int]$Index,
          [Management.Automation.PSCredential]$Credential)
    if ($Command.Contains('"')) { throw 'Unexpected native command quoting' }
    $arguments='-NoProfile -NonInteractive -Command "'+$Command+'"'
    $fullLength=$Runtime.Length+$arguments.Length+4
    if ($fullLength -gt 1024) { throw 'Credentialed probe command exceeds Windows limit' }
    $launchParameters=@{FilePath=$Runtime;WindowStyle='Hidden';ArgumentList=$arguments;
        WorkingDirectory=$WorkingDirectory;RedirectStandardOutput=$OutputLog;
        RedirectStandardError=$ErrorLog;PassThru=$true;ErrorAction='Stop'}
    if ($Credential) { $launchParameters.Credential=$Credential; $launchParameters.LoadUserProfile=$true }
    $process=Start-Process @launchParameters
    try {
        # Windows PowerShell's redirected Start-Process can lose exit status
        # unless the handle is retained before waiting. Never assume null is 0.
        $retainedHandle=$process.Handle
        if ($retainedHandle -eq [IntPtr]::Zero) { throw 'Owned probe process handle unavailable' }
        if (!$process.WaitForExit(30000)) { $process.Kill(); $process.WaitForExit(); throw 'Owned read probe timed out' }
        $observedExit=$process.ExitCode
        if ($null -eq $observedExit) { throw 'Owned probe exit code unavailable' }
        return @{index=$Index;process_id=$process.Id;exit_code=$observedExit;command_characters=$fullLength}
    } finally { $process.Dispose() }
}
