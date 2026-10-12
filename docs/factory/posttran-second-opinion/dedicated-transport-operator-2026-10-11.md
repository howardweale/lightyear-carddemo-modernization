# Dedicated POSTTRAN Phase 1 transport — October 11, 2026

This is a local, operator-run amendment. No API request, real credential read,
model generation or compilation was performed during preparation. The old
plan and approval remain preserved; these commands explicitly select the new
plan. Phase 2 remains blocked. No Docker or native work is authorized.

- Transport SHA256: `41b0df0367194599a892f7596254d9eba94fb28ee9593e16ca0c9a9651e6243f`
- Amended plan content SHA256: `bb53fd6de1afed29fc1064f986c6c2dadc5d709b93c9732c50a67077aaeb2919`
- Plan file SHA256: `380eeedac982d0a0334456366dc205e102e9dd08a46a18d0fe03d6cc370f046a`
- Previous plan: `bb91aad8d0533118ecf8270348ac509435fc22bec4dbf18611a6b696d89f3bd5`

The exact unified diff is `dedicated-transport-plan-2026-10-11.diff`;
`dedicated-transport-amendment-2026-10-11.json` contains before/after values.
The 16-file public packet, work order, model and budgets are unchanged.
The new standard-library module replaces the old broker/helper dispatch.
Only `LIGHTYEAR_POSTTRAN_OPENAI_KEY` is read, inside the HTTP worker at call
time. There is no generic-key fallback. The commands below prompt securely
and remove the dedicated environment variable after each operation.

Preflight is outside the reservation ledger and does not start the phase
clock or consume an attempt. It writes a separate sealed token-count receipt.
Attempt 1 requires the exact completed receipt, no older than one hour, and
reserves $11.05 / 250,000 input / 64,000 output tokens before generation.
One generation is implemented; no compilation or attempts 2/3 are automatic.
The overall ceilings remain 3 attempts, 750,000 input, 192,000 output,
two hours and $36. Every failed generation consumes its reservation.

TLS certificate and hostname verification are mandatory. No redirects,
proxy-environment handling or retries. Connect timeout: 30 seconds. Total
wall limits: 120 seconds for count, 1,800 seconds for generation. A local
timeout cannot prove server cancellation; do not rerun it. Requests have
`store: false` and `max_output_tokens: 64000` on generation. Responses must
be completed with integer usage within caps; input usage must match count.
Errors are fixed codes, never exception text or server bodies. Request and
raw-response hashes are recorded; a response hash is null if no bytes arrive.

## Run in your own PowerShell terminal

Paste this setup once. It does not request or read a key until you invoke
the function. These paths point to the prepared local worktree, not a new
checkout. The transport is not yet published or live-tested.

```powershell
$posttranRoot = 'C:\Users\howar\.codex\worktrees\oct11-decisions-next\lightyear-carddemo-modernization'
$posttranPython = 'C:\Users\howar\OneDrive\Documents\ChatGPT\lightyear-carddemo-modernization\work\idempiere-runtime-evidence\work\native-venv\Scripts\python.exe'
$posttranTransport = Join-Path $posttranRoot 'src\lightyear_factory\posttran_phase1_transport.py'
$posttranPlan = Join-Path $posttranRoot 'docs\factory\posttran-second-opinion\dedicated-transport-plan-2026-10-11.json'
$posttranGo = 'go POSTTRAN bb53fd6de1afed29fc1064f986c6c2dadc5d709b93c9732c50a67077aaeb2919'

function Invoke-PosttranPhase1 {
    param([ValidateSet('preflight', 'attempt-1')][string]$Operation)
    if ((Get-FileHash -LiteralPath $posttranTransport -Algorithm SHA256).Hash.ToLowerInvariant() -ne '41b0df0367194599a892f7596254d9eba94fb28ee9593e16ca0c9a9651e6243f') { throw 'Transport hash mismatch; stop.' }
    if ((Get-FileHash -LiteralPath $posttranPlan -Algorithm SHA256).Hash.ToLowerInvariant() -ne '380eeedac982d0a0334456366dc205e102e9dd08a46a18d0fe03d6cc370f046a') { throw 'Plan file hash mismatch; stop.' }
    $posttranSecure = Read-Host 'Dedicated POSTTRAN API key (hidden)' -AsSecureString
    $posttranPointer = [IntPtr]::Zero
    try {
        $posttranPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($posttranSecure)
        $env:LIGHTYEAR_POSTTRAN_OPENAI_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($posttranPointer)
        & $posttranPython -B $posttranTransport $Operation --plan $posttranPlan --go $posttranGo
        if ($LASTEXITCODE -ne 0) { throw 'POSTTRAN refused or failed. Preserve receipts; do not retry.' }
    }
    finally {
        Remove-Item Env:LIGHTYEAR_POSTTRAN_OPENAI_KEY -ErrorAction SilentlyContinue
        if ($posttranPointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($posttranPointer) }
        $posttranSecure.Dispose()
    }
}
```

Run token-count preflight (one count request, zero generation reservations):

```powershell
Invoke-PosttranPhase1 -Operation preflight
```

Only after `preflight-completed`, run attempt 1 within one hour. This command
makes the one approved generation request and saves its response locally:

```powershell
Invoke-PosttranPhase1 -Operation attempt-1
```

Do not rerun either command after a failure or interruption. Preserve
`work/posttran-dedicated-phase1/` for review. The fixed ledger is
`work/posttran-dedicated-phase1/phase1-ledger.json`; receipts and successful
response JSON are under its plan-hash subdirectory. No candidate compilation
or execution is performed by these commands. Request/response hashes alone
do not establish a successful or correct candidate.
