param([Parameter(Mandatory=$true)][string]$PrivateKey,
      [Parameter(Mandatory=$true)][string]$PublicFile)
$ErrorActionPreference='Stop'
$rows=@()
foreach($item in @(@{name='private';path=$PrivateKey},@{name='public';path=$PublicFile},@{name='missing';path=($PublicFile+'.definitely-missing')})) {
    $opened=$false;$errorCode=$null;$stream=$null
    try {
        $stream=[IO.File]::Open($item.path,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
        $opened=$true
        # Intentionally no Read call: never export even one byte of the key.
    } catch {
        $exception=$_.Exception
        while($exception.InnerException){$exception=$exception.InnerException}
        $errorCode=$exception.HResult -band 0xffff
    } finally {if($stream){$stream.Dispose()}}
    $rows+=@{name=$item.name;read_open_succeeded=$opened;native_error=$errorCode;bytes_read=0}
}
@{account_sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value;observations=$rows;
  passed=(!$rows[0].read_open_succeeded -and $rows[0].native_error -eq 5 -and $rows[1].read_open_succeeded -and $rows[2].native_error -eq 2);
  model_calls=0;docker_commands=0;real_utc=[DateTime]::UtcNow.ToString('o')}|ConvertTo-Json -Depth 5
