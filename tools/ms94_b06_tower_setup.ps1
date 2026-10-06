#Requires -RunAsAdministrator
param([Parameter(Mandatory=$true)][string]$Repository,
      [Parameter(Mandatory=$true)][string]$Python,
      [Parameter(Mandatory=$true)][string]$OutputDirectory,
      [string]$RuntimeStage,[string]$RuntimeManifestSHA256,
      [switch]$ReuseUnprovisionedAccount)
$ErrorActionPreference='Stop'
$name='lyb06tower'
$authorityDirectory='C:\ProgramData\Lightyear\B06TowerAuthority'
$dataRoot=Join-Path $Repository 'work/b06-tower-r8'
$existing=Get-LocalUser -Name $name -ErrorAction SilentlyContinue
if (Test-Path -LiteralPath $OutputDirectory) { throw 'Fresh output directory required' }
if ($ReuseUnprovisionedAccount) {
    if (!$existing -or $existing.Enabled -or !(Test-Path -LiteralPath $authorityDirectory) -or @(Get-ChildItem -LiteralPath $authorityDirectory -Force).Count -ne 0) {
        throw 'Reuse requires the disabled setup account and an EMPTY authority directory; never replace keys'
    }
} elseif ($existing -or (Test-Path -LiteralPath $authorityDirectory) -or (Test-Path -LiteralPath $dataRoot)) {
    throw 'Fresh Tower account, authority, data root and output required; preserve previous attempts'
}
$out=New-Item -ItemType Directory -Path $OutputDirectory
$bytes=New-Object byte[] 40
$rng=[Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($bytes);$rng.Dispose()
$password=ConvertTo-SecureString ([Convert]::ToBase64String($bytes)+'!aA9') -AsPlainText -Force
$account=$null;$process=$null
try {
    if ($ReuseUnprovisionedAccount) {
        $account=$existing
        Set-LocalUser -Name $name -Password $password
        Enable-LocalUser -Name $name
    } else {
        $account=New-LocalUser -Name $name -Password $password -Description 'B06 Tower signing host; no builder/model role' -AccountNeverExpires
        Add-LocalGroupMember -SID 'S-1-5-32-545' -Member $name
    }
    $sid=$account.SID.Value
    $operatorSid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    if (!(Test-Path -LiteralPath $authorityDirectory)) { New-Item -ItemType Directory -Path $authorityDirectory|Out-Null }
    & icacls.exe $authorityDirectory /inheritance:r /grant:r '*S-1-5-32-544:(OI)(CI)F' "*$($sid):(OI)(CI)F"|Out-Null
    if ($LASTEXITCODE) { throw 'Authority ACL failed' }
    if (!(Test-Path -LiteralPath $dataRoot)) { New-Item -ItemType Directory -Path $dataRoot|Out-Null }
    & icacls.exe $dataRoot /grant "*$($sid):(OI)(CI)M"|Out-Null
    if ($LASTEXITCODE) { throw 'Tower data ACL failed' }
    & icacls.exe $out.FullName /grant "*$($sid):(OI)(CI)M"|Out-Null
    if ($LASTEXITCODE) { throw 'Public output ACL failed' }
    $working=$out.FullName
    if ($RuntimeStage) {
        $runtime='C:\ProgramData\Lightyear\B06TowerRuntime-r8'
        if (Test-Path -LiteralPath $runtime) { throw 'Fresh runtime install required' }
        $manifestPath=Join-Path $RuntimeStage 'manifest.json'
        if ((Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $RuntimeManifestSHA256) { throw 'Runtime manifest changed' }
        $manifest=Get-Content -LiteralPath $manifestPath -Raw|ConvertFrom-Json
        foreach($property in $manifest.files_sha256.PSObject.Properties) {
            $source=[IO.Path]::GetFullPath((Join-Path $RuntimeStage $property.Name))
            $target=[IO.Path]::GetFullPath((Join-Path $runtime $property.Name))
            if (!$source.StartsWith([IO.Path]::GetFullPath($RuntimeStage)+[IO.Path]::DirectorySeparatorChar) -or !$target.StartsWith($runtime+'\')) { throw 'Runtime path escapes' }
            if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant() -ne $property.Value) { throw 'Runtime source changed' }
            [IO.Directory]::CreateDirectory((Split-Path $target))|Out-Null
            Copy-Item -LiteralPath $source -Destination $target
            if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant() -ne $property.Value) { throw 'Runtime copy differs' }
        }
        Copy-Item -LiteralPath $manifestPath -Destination (Join-Path $runtime 'manifest.json')
        & icacls.exe $runtime /inheritance:r /grant:r '*S-1-5-32-544:(OI)(CI)F' "*$($sid):(OI)(CI)RX" "*$($operatorSid):(OI)(CI)RX"|Out-Null
        if ($LASTEXITCODE) { throw 'Runtime ACL failed' }
        & icacls.exe $runtime /setowner '*S-1-5-32-544' /T /Q|Out-Null
        if ($LASTEXITCODE) { throw 'Runtime owner failed' }
        $Python=Join-Path $runtime 'python/python.exe'
        $working=Join-Path $runtime 'app'
    }
    $start=New-Object Diagnostics.ProcessStartInfo
    $start.FileName=$Python
    $start.Arguments='-m tools.ms94_b06_tower_provision --authority "'+(Join-Path $authorityDirectory 'authority.json')+'" --root "'+$dataRoot+'" --output "'+$out.FullName+'"'
    $start.WorkingDirectory=[IO.Path]::GetFullPath($working);$start.UseShellExecute=$false;$start.CreateNoWindow=$true;$start.WindowStyle='Hidden'
    $start.UserName=$name;$start.Domain=$env:COMPUTERNAME;$start.Password=$password;$start.LoadUserProfile=$true
    $start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true
    $start.EnvironmentVariables['PYTHONPATH']=(Join-Path $Repository 'src')+';'+$Repository
    $start.EnvironmentVariables['PYTHONDONTWRITEBYTECODE']='1';$start.EnvironmentVariables['PYTHONUTF8']='1'
    $process=New-Object Diagnostics.Process;$process.StartInfo=$start
    if (!$process.Start()) { throw 'Tower provisioning child did not start' }
    $stdout=$process.StandardOutput.ReadToEndAsync();$stderr=$process.StandardError.ReadToEndAsync()
    if (!$process.WaitForExit(60000)) { throw 'Tower provisioning timed out' }
    # Provisioner never prints credentials or private key contents.
    [IO.File]::WriteAllText((Join-Path $out.FullName 'child.stderr.log'),$stderr.Result)
    if ($process.ExitCode -ne 0) { throw 'Tower provisioning child failed; inspect local stderr' }
    $public=Get-Content -LiteralPath (Join-Path $out.FullName 'provisioning.json') -Raw|ConvertFrom-Json
    if (!$public.tower_key_read_open_succeeded -or $public.scope -ne 'ms94-b06') { throw 'Provisioning observation incomplete' }
    @{account_sid=$sid;host_operator_sid=$operatorSid;private_key_path=(Join-Path $authorityDirectory 'authority.key.pem');
      authority=$authorityDirectory;data_root=$dataRoot;public_key_sha256=$public.public_key_sha256;
      account_non_admin=($sid -notin @((Get-LocalGroupMember -SID 'S-1-5-32-544').SID.Value));
      model_calls=0;docker_commands=0;real_utc=[DateTime]::UtcNow.ToString('o')}|ConvertTo-Json|
      Set-Content -LiteralPath (Join-Path $out.FullName 'host.json') -Encoding UTF8
} catch {
    @{error_type=$_.Exception.GetType().FullName;message=$_.Exception.Message;model_calls=0;docker_commands=0}|
      ConvertTo-Json|Set-Content -LiteralPath (Join-Path $out.FullName 'failure.json') -Encoding UTF8
    throw
} finally {
    if ($process) {
        if ($process.Id -and !$process.HasExited) { & taskkill.exe /PID $process.Id /T /F|Out-Null }
        $process.Dispose()
    }
    if ($account) { Disable-LocalUser -Name $name }
    @{account_disabled=(!$account -or !(Get-LocalUser -Name $name).Enabled);model_calls=0;docker_commands=0;
      real_utc=[DateTime]::UtcNow.ToString('o')}|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $out.FullName 'cleanup.json') -Encoding UTF8
}
