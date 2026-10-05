# B06 Windows builder denial preparation — October 5

Operator review; not independent attestation. Zero model calls, native pairs and
Docker runs in this increment. This is a host boundary probe, not complete B06
measurement admission or a native qualification result.

Attempt 8 passed on October 5, 2026, from 16:44:35.182 UTC to 16:44:38.289 UTC
(about 3.107 seconds). Built-in Windows PowerShell launched five processes under
one dedicated, non-admin local account. Both existing protected-file reads
returned Win32 `ERROR_ACCESS_DENIED` (native code 5). The public positive control
opened; a deliberately missing public path returned `ObjectNotFound`, not access
denied. All five processes exited 0. A subsequent read-only check confirmed that
the account was disabled and all five owned processes were absent.

The [signed public summary](preparation-summary.json) binds the exact launcher,
command factory, PowerShell runtime, policy and command manifest hashes. Its file
SHA-256 is `b187004f8bcc510e22d00ebc00766c6a4414a76810a8d8a7dac8311dd4be032a`.
The signed local denial record is
`47181285efa707969a8a8541137ba81b0351b7a6aeb787213ffc6b4dff031313`;
its verification record is
`2b7fcb4242a69274c32ffbb400fa284d334e79db0f69f5496a77e7fd02ba2912`.
Raw account identities, ACLs, paths, observations and private controls stay local.
No keys, private source files or captures are published.

## Admission and scope

The version 2 denial record binds the tested SID, exact tools/private paths,
existing target hashes, limited group membership, runtime, launcher and command
bytes. Admission verifies its signature and file hash. Win32 exceptions require
`NativeErrorCode == 5`; managed `UnauthorizedAccessException` requires HRESULT
`0x80070005`. A generic HRESULT, an error category alone, a missing target or an
unverified boolean cannot admit the builder. The measurement and preflight gates
require this evidence; zero-model judge qualification has no builder and is
independent of the probe (PR #252).

This demonstrates the two tested directory boundaries for this local identity.
It does not establish confinement for another checkout, private directory or
execution identity. The eventual executable must bind and use the admitted
transport. Full measurement preflight remains outstanding.

## Preserved failures and corrections

All existing failure and observation records are unchanged and hash-bound in
the summary. Earlier attempts failed on an overlong account description,
unstarted scheduled tasks, the dedicated account's script execution policy,
Windows credentialed-command length, unavailable process exit metadata and the
incorrect exception field. The scripts now use short built-in commands, retain
the process handle before reading its actual exit status, and capture the native
error separately from HRESULT. No security exclusion or execution-policy change
was made. Attempt 7 remains failed: it did not capture the native error code and
has not been retrospectively reclassified.

## Validation and remaining work

Five focused tests cover signed evidence admission and tampering, observed-record
binding, actual Windows PowerShell short commands, positive/missing controls,
real exception properties and redirected nonzero process exits. These public
fixtures are regression tests, not host qualification evidence.

The offline observer compilation and class catalog are recorded separately in
[PR #253's preparation report](../offline-catalog-r4/README.md). Native
mutation/evidence-boundary integration, posting-cause delivery/replay,
qualification finalization and exact J1/J2/J3 executable plan assembly remain.
Native qualification still requires approval of each journey's plan and Docker
window. B05, work/ms94, template-r1 and J1 business predicates are unchanged.
