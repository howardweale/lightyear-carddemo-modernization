#Requires -Version 5.1
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$runtime = 'C:\ProgramData\Lightyear\FactoryRuntime-v1'
$authority = 'C:\ProgramData\Lightyear\FactoryAuthority\authority.json'
$root = 'C:\ProgramData\Lightyear\FactoryData-v1\snapshot'
foreach ($path in @($authority,(Join-Path (Split-Path $authority) 'factory-evidence-trust.json'),$root)) {
    if (!(Test-Path -LiteralPath $path)) { throw 'Howard must complete identity and public snapshot setup before starting Tower' }
}
Set-Location -LiteralPath $runtime
& (Join-Path $runtime 'python\python.exe') -I -B (Join-Path $runtime 'app\tools\factory_install\entry.py') tower serve --root $root --authority $authority --port 8769
if ($LASTEXITCODE -ne 0) { throw 'Factory Tower stopped with an error; inspect privately, do not auto-reprovision' }