# B06 dedicated-account Codex probe r5

Operator review; not independent attestation. Zero Docker and model calls.
**Attempt 4 passed the actual Codex process proof and the local admission check.
No measurement transport is admitted.** This branch is separate from the native
qualification integration.

`admit_transport` now requires both a signed v2 Windows denial record and a
signed Codex process proof. They must bind the same account SID and tools/private
target hashes. The Codex executable, host protocol code and launcher are also
hash-bound. Missing proof, changed identity, a read outside the Codex process
tree, a generic error instead of access denied, a missing positive control or a
model RPC fail admission.

The probe starts `codex.exe` directly as `lyb06builder`. A trusted host drives
`initialize`, `initialized` and four `command/exec` requests: a public positive
control, a nonexistent file, the existing tools target and the existing private
control. Child PowerShell executes built-in commands and emits no file values.
Each child records its SID and its Codex parent PID/name/SID. No thread, turn,
prompt, login or model request is sent. The fresh Codex home contains no copied
settings or credentials. A temporary Windows Firewall rule blocks this copied
CLI's outbound traffic; the wrapper removes that rule and disables the account
in its finally block. No execution policy, antivirus exclusion or system-wide
firewall setting is changed. `externalSandbox` denotes the existing account/ACL
boundary for these fixed host-issued commands, not a model-facing capability.

The tested protocol shape is from the installed desktop CLI **0.160.0**. Its
app-server does not accept the exec transport's `--ignore-user-config` switch;
the corrected probe uses a fresh empty configuration directory. This does not
approve changing the frozen builder capability arguments or a measurement CLI.

## Preserved attempts

1. The account's PowerShell policy rejected a script file before Codex started.
   The corrected host launches the executable directly, without changing policy.
2. Codex rejected `--ignore-user-config` before an RPC response. The account was
   disabled and the temporary firewall removed after both failed attempts.
3. Windows returned “operation canceled” for the UAC launch; no probe directory
   was created.
4. The accepted UAC launch ran from 18:48:44.1398382 to 18:49:00.3708707 UTC
   on October 5, 2026. All four PowerShell children had the dedicated account's
   SID and the same Codex parent PID/SID. The public read succeeded, the missing
   file returned `ObjectNotFound`, and both existing protected targets returned
   native Windows error 5 (`ERROR_ACCESS_DENIED`). Codex exited 0. Read-only
   checks confirmed the account disabled, the temporary firewall rule absent,
   and all owned processes absent. No prompt, turn or model call was sent.

The signed, hash-only [failure summary](failure-summary.json) has content hash
`3bf808f123073f187fd9672c08af05b4f8c6fd32259aa7f22d0a9c79209919b9`.
Raw observations, account identifiers and logs remain local. No passed record is
manufactured from these failures.

The new signed [success summary](success-summary.json) has content hash
`1d4f3dd36728dde0dec2915817ef816b08c605012eecc121d814d4bb7091804c`.
It binds the local signed v2 denial file
`016ac7c3097c9d0ab28e9e69bf63a26c46e295ca3c23e02a967b2edd616130c3`
and signed process file
`3947c8fff0109bd4d3e78b906ec368549396ffaf6015bc74af3aa722b8152984`.
The host recorder verified and signed both, read them back, and passed the real
`admit_transport` check against the current files and executable. This verifies
the preparation boundary, not a measurement launch or model-facing transport.

## Validation and next step

The branch's 98 B06 offline tests passed, including the full synthetic recorder
test (3 dedicated transport tests). Both PowerShell
scripts parse. Synthetic fixtures exercise record signing and both admission
gates; they grant no native or OS qualification credit. The separate actual
attempt above supplies OS evidence. CI is tracked on PR #256.

Run `tools/ms94_b06_codex_account_probe.ps1` in Windows PowerShell 5.1 with an
accepted Administrator/UAC prompt, supplying `Repository`, `PrivateTarget`,
`Codex`, a new `OutputDirectory`, and the exact existing `AccountSid`. Never reuse
an attempted directory. After success, the trusted host recorder
`tools.ms94_b06_codex_probe_record.record` verifies the observations and writes
new signed denial/process records outside any frozen campaign. It must use the
existing signing authority in place. Re-probe the final executable tree after
any relevant file, runtime, account or ACL change. In particular, this edit to
the builder boundary deliberately makes the earlier target hash stale.

No B05, work/ms94, template-r1 or J1 predicate changes. B06 remains unqualified;
model networking and the complete measurement preflight remain separate gates.
