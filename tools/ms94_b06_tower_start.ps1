#Requires -RunAsAdministrator
param([Parameter(Mandatory=$true)][string]$Repository,
      [Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference='Stop'
$runtime='C:\ProgramData\Lightyear\B06TowerRuntime-r8'
$authority='C:\ProgramData\Lightyear\B06TowerAuthority\authority.json'
$root='C:\ProgramData\Lightyear\B06TowerData-r8'
if(Test-Path -LiteralPath $OutputDirectory){throw 'Fresh output required'}
if(Get-NetTCPConnection -LocalPort 8766 -State Listen -ErrorAction SilentlyContinue){throw 'Port 8766 is already occupied; do not replace another Tower'}
$account=Get-LocalUser lyb06tower
if($account.Enabled){throw 'Expected disabled Tower account'}
$manifestPath=Join-Path $runtime 'manifest.json'
if((Get-FileHash $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne 'fa8138477e00142e31de5455a7b8f3d6e85a273695ba17110d0708acd5ddf6e0'){throw 'Runtime manifest differs'}
$manifest=Get-Content -LiteralPath $manifestPath -Raw|ConvertFrom-Json
foreach($p in $manifest.files_sha256.PSObject.Properties){
    if((Get-FileHash -LiteralPath (Join-Path $runtime $p.Name) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $p.Value){throw 'Runtime file differs'}
}
if((Get-FileHash 'C:\ProgramData\Lightyear\B06TowerAuthority\authority.public.pem' -Algorithm SHA256).Hash.ToLowerInvariant() -ne '65bcec7f9fb46d5a618cd61b8bcd0a74497b9a0c360738781e269ef2d87a6240'){throw 'Confirmed Tower key differs'}
$out=New-Item -ItemType Directory -Path $OutputDirectory
$bytes=New-Object byte[] 40;$rng=[Security.Cryptography.RandomNumberGenerator]::Create();$rng.GetBytes($bytes);$rng.Dispose()
$password=ConvertTo-SecureString ([Convert]::ToBase64String($bytes)+'!aA9') -AsPlainText -Force
$process=$null;$ready=$false
try{
    Set-LocalUser lyb06tower -Password $password
    Enable-LocalUser lyb06tower
    $start=New-Object Diagnostics.ProcessStartInfo
    $start.FileName=Join-Path $runtime 'python/python.exe'
    $start.Arguments='-m lightyear_control_tower serve --root "'+$root+'" --authority "'+$authority+'" --port 8766'
    $start.WorkingDirectory=Join-Path $runtime 'app';$start.UseShellExecute=$false;$start.CreateNoWindow=$true;$start.WindowStyle='Hidden'
    $start.UserName='lyb06tower';$start.Domain=$env:COMPUTERNAME;$start.Password=$password;$start.LoadUserProfile=$true
    $start.EnvironmentVariables['PYTHONDONTWRITEBYTECODE']='1';$start.EnvironmentVariables['PYTHONUTF8']='1'
    $process=New-Object Diagnostics.Process;$process.StartInfo=$start
    if(!$process.Start()){throw 'Tower did not start'}
    $deadline=[DateTime]::UtcNow.AddSeconds(30)
    while([DateTime]::UtcNow -lt $deadline -and !$process.HasExited){
        $listener=Get-NetTCPConnection -LocalPort 8766 -State Listen -ErrorAction SilentlyContinue
        if($listener -and $listener.OwningProcess -eq $process.Id -and $listener.LocalAddress -eq '127.0.0.1'){$ready=$true;break}
        Start-Sleep -Milliseconds 500
    }
    if(!$ready){throw 'Tower did not bind the expected loopback listener'}
    $actual=Get-CimInstance Win32_Process -Filter ('ProcessId='+$process.Id)
    if((Invoke-CimMethod -InputObject $actual -MethodName GetOwnerSid).Sid -ne $account.SID.Value){$ready=$false;throw 'Tower process identity differs'}
    @{pid=$process.Id;scope='ms94-b06';public_key_sha256='65bcec7f9fb46d5a618cd61b8bcd0a74497b9a0c360738781e269ef2d87a6240';
      runtime_manifest_sha256='fa8138477e00142e31de5455a7b8f3d6e85a273695ba17110d0708acd5ddf6e0';
      real_utc=[DateTime]::UtcNow.ToString('o');model_calls=0;docker_commands=0;group_decisions_issued=0;loopback_only=$true}|
      ConvertTo-Json|Set-Content -LiteralPath (Join-Path $out.FullName 'start.json') -Encoding UTF8
}catch{
    @{message=$_.Exception.Message;model_calls=0;docker_commands=0}|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $out.FullName 'failure.json') -Encoding UTF8
    throw
}finally{
    Disable-LocalUser lyb06tower
    if($process){if(!$ready -and $process.Id -and !$process.HasExited){& taskkill.exe /PID $process.Id /T /F|Out-Null};$process.Dispose()}
    @{account_disabled=(!(Get-LocalUser lyb06tower).Enabled);listener_left_running=$ready}|
      ConvertTo-Json|Set-Content -LiteralPath (Join-Path $out.FullName 'account-state.json') -Encoding UTF8
}
