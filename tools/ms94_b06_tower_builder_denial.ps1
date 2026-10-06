#Requires -RunAsAdministrator
param([Parameter(Mandatory=$true)][string]$Repository,[Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference='Stop'
$account=Get-LocalUser -Name 'lyb06builder'
if ($account.Enabled -or (Test-Path -LiteralPath $OutputDirectory)) { throw 'Disabled builder and fresh output required' }
$out=New-Item -ItemType Directory -Path $OutputDirectory
$sid=$account.SID.Value
& icacls.exe $out.FullName /grant "*$($sid):(OI)(CI)RX"|Out-Null
if($LASTEXITCODE){throw 'Probe public directory ACL failed'}
$public=Join-Path $out.FullName 'public.txt'
Set-Content -LiteralPath $public -Value 'public positive control' -Encoding ASCII
$bytes=New-Object byte[] 40;$rng=[Security.Cryptography.RandomNumberGenerator]::Create();$rng.GetBytes($bytes);$rng.Dispose()
$password=ConvertTo-SecureString ([Convert]::ToBase64String($bytes)+'!aA9') -AsPlainText -Force
$process=$null
try {
    Set-LocalUser -Name 'lyb06builder' -Password $password
    Enable-LocalUser -Name 'lyb06builder'
    $rows=@()
    foreach($item in @(@{name='private';path='C:\ProgramData\Lightyear\B06TowerAuthority\authority.key.pem'},@{name='public';path=$public},@{name='missing';path=($public+'.definitely-missing')})) {
        $start=New-Object Diagnostics.ProcessStartInfo
        $start.FileName="$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
        # One short built-in command per read. CreateProcessWithLogonW limits
        # the command line to 1024 characters. No script-policy change.
        $command='$s=$null;$ok=$false;$code=$null;try{$s=[IO.File]::Open('''+$item.path+''',[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read);$ok=$true}catch{$e=$_.Exception;while($e.InnerException){$e=$e.InnerException};$code=$e.HResult -band 65535}finally{if($s){$s.Dispose()}};@{account_sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value;read_open_succeeded=$ok;native_error=$code;bytes_read=0}|ConvertTo-Json'
        $start.Arguments='-NoProfile -NonInteractive -Command '+$command
        if (($start.FileName.Length+$start.Arguments.Length+4) -ge 1024) { throw 'Credential process command exceeds Windows limit' }
        $start.WorkingDirectory=$out.FullName;$start.UseShellExecute=$false;$start.CreateNoWindow=$true;$start.WindowStyle='Hidden'
        $start.UserName='lyb06builder';$start.Domain=$env:COMPUTERNAME;$start.Password=$password;$start.LoadUserProfile=$true
        $start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true
        $process=New-Object Diagnostics.Process;$process.StartInfo=$start
        if(!$process.Start()){throw 'Builder denial child did not start'}
        $stdout=$process.StandardOutput.ReadToEndAsync();$stderr=$process.StandardError.ReadToEndAsync()
        if(!$process.WaitForExit(30000)){throw 'Builder denial timeout'}
        [IO.File]::WriteAllText((Join-Path $out.FullName ($item.name+'-stderr.log')),$stderr.Result)
        if($process.ExitCode -ne 0){throw 'Builder denial child failed'}
        $record=$stdout.Result|ConvertFrom-Json
        if($record.account_sid -ne $sid){throw 'Builder identity differs'}
        $rows+=@{name=$item.name;read_open_succeeded=$record.read_open_succeeded;native_error=$record.native_error;bytes_read=$record.bytes_read}
        $process.Dispose();$process=$null
    }
    $passed=(!$rows[0].read_open_succeeded -and $rows[0].native_error -eq 5 -and $rows[1].read_open_succeeded -and $rows[2].native_error -eq 2)
    @{account_sid=$sid;observations=$rows;passed=$passed;model_calls=0;docker_commands=0;real_utc=[DateTime]::UtcNow.ToString('o')}|ConvertTo-Json -Depth 5|
        Set-Content -LiteralPath (Join-Path $out.FullName 'observation.json') -Encoding UTF8
    if(!$passed){throw 'Private-key denial/positive/missing controls failed'}

} catch {
    @{message=$_.Exception.Message;model_calls=0;docker_commands=0}|ConvertTo-Json|
        Set-Content -LiteralPath (Join-Path $out.FullName 'failure.json') -Encoding UTF8
    throw
} finally {
    if($process){if($process.Id -and !$process.HasExited){& taskkill.exe /PID $process.Id /T /F|Out-Null};$process.Dispose()}
    Disable-LocalUser -Name 'lyb06builder'
    @{account_disabled=(!(Get-LocalUser -Name 'lyb06builder').Enabled);model_calls=0;docker_commands=0;
      real_utc=[DateTime]::UtcNow.ToString('o')}|ConvertTo-Json|
      Set-Content -LiteralPath (Join-Path $out.FullName 'cleanup.json') -Encoding UTF8
}
