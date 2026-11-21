# H1-r2 operator checklist

Session 2 stopped in Part A. Howard reports C01–C05 passed. C06 failed because the service was still running with automatic startup. Part B never started. There were no control files, approval, operation or private data. This account of Session 2 cannot serve as a later passing custody return.

## Windows custody at both checkpoints

Use the separate Windows administrator account for service administration. The service name is `CodexSandboxService.OpenAI.Codex`. Its process image is `codex-windows-sandbox-service`. Service commands require the service name. Carry the observation under the existing `no_codex_background_or_autostart` key. The preflight and postflight checks each require it to be true. Preserve the independent process-visibility, stopped and continuity declarations. A later successful observation cannot establish uninterrupted custody retroactively.

When separately authorized to open the private window, fully close Codex and its helpers. In elevated PowerShell disable startup first, then stop the service. Perform these commands only as the operator.

~~~powershell
$name = 'CodexSandboxService.OpenAI.Codex'
Set-Service -Name $name -StartupType Disabled -ErrorAction Stop
Stop-Service -Name $name -ErrorAction Stop
~~~

Run this read-only block **before any private step and again at postflight**. Use the existing all-session inventory to include known helpers whose image name does not identify Codex. Treat incomplete visibility, ambiguous service identity, another Codex service eligible for startup, or a process that respawns as a refusal. Retain raw observations locally and return only reviewed custody booleans. Do not print the raw service/process inventory in the public return.

~~~powershell
$services = @(Get-CimInstance Win32_Service -ErrorAction Stop)
$target = @($services | Where-Object Name -eq 'CodexSandboxService.OpenAI.Codex')
$related = @($services | Where-Object {
    $_.Name -match 'codex' -or $_.DisplayName -match 'codex' -or $_.PathName -match 'codex'
})
if ($target.Count -ne 1) { throw 'C06-service-identity' }
foreach ($service in $related) {
    if ($service.State -ne 'Stopped' -or $service.StartMode -ne 'Disabled') {
        throw 'C06-service-state'
    }
}
$running = @(Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object { $_.Name -match 'codex' })
if ($running.Count) { throw 'C06-process-running' }
~~~

Close the private window and complete postflight before restoring the normal service configuration in elevated PowerShell. Restore the observed default for this named service and verify both settings.

~~~powershell
$name = 'CodexSandboxService.OpenAI.Codex'
Set-Service -Name $name -StartupType Automatic -ErrorAction Stop
Start-Service -Name $name -ErrorAction Stop
$state = Get-CimInstance Win32_Service -Filter "Name='CodexSandboxService.OpenAI.Codex'" -ErrorAction Stop
if ($state.State -ne 'Running' -or $state.StartMode -ne 'Auto') { throw 'service-restore-incomplete' }
~~~

## Linux preparation for a separately approved operation

1. Use the standard operator in the account-specific WSL2 distro and the existing local Docker Engine. The distro needs the `acl` package for `getfacl`. Verify the operator already has attended, password-authenticated sudo access to the five fixed reads. Stop if policy or host configuration prevents one. Do not install packages or alter privilege policy as part of INSPECT.
2. Generate a fresh operation ID of exactly 64 lowercase hexadecimal characters. For example, `head -c 32 /dev/urandom | sha256sum | cut -d ' ' -f 1` emits a suitable ID. Use the same ID throughout that operation. A descriptive label will refuse.
3. Record the realpath of each profile binary using `readlink -f -- "$(command -v NAME)"` with NAME replaced by the reviewed utility. Hash those resolved bytes using SHA-256. H1-r2 adds sudo, readlink and sha256sum to the existing binary pins, including ss. Pin the actual dockerd digest separately. Keep all host values, pins, account data and local paths in private controls. Recompute the canonical profile commitment and obtain the appropriate fresh approval for the reviewed source and profile.
4. Choose the approval window before collecting custody evidence. The custody observation must fall at or after approval valid_from and at or before invocation; invocation must precede expires_at. Complete preflight before private steps. Approval commits to the actual custody-file bytes. Keep control files outside the clean source checkout.
5. Use `python3 -B -m tools.intcalc_private_reference_host` with the reviewed mode and its private control arguments. H1 uses `git ls-files --others`, which enumerates ignored untracked bytecode. The -B flag prevents creation of bytecode during this invocation. Check for existing untracked files first.
6. Attend each sudo prompt on the controlling terminal. Each Host.observe asks sudo to ignore cached credentials for five short, read-only commands. Use the normal interactive password prompt. Refuse a passwordless policy, missing prompt, unexpected command, terminal recording, time-out or incomplete facts. Do not supply passwords through arguments, environment, pipes or files. Leave ordinary Docker, custody and qualification checks with the non-root operator. The raw engine facts remain local.
