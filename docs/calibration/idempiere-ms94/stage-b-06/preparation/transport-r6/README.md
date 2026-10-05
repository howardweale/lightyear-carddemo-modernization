# B06 pinned-client transport preparation

**Passed on October 5, 2026:** the fresh attempt-5 zero-model probe and combined
`admit_transport` verification. The pinned plan is
`5785ec68eb60910bafae415933555dede2caa902b2701234db7fa340debdfe88`;
the signed pinned-exec proof is
`0b7d70d5bdb87143f73e52caad7229cfed45217ab2ebe8cc46784a431eccd548`.
The [signed safe summary](passed.json) binds local evidence by hash; the
[transport plan](pinned-plan.json) contains the public path, binary and code
bindings. Raw observations, SIDs and signed detailed proofs remain local.

Operator review; not independent attestation. Zero model calls and zero Docker
runs. The qualification changes are a separate PR (#257, commit
`159897376007c6d6b70fbac1bb96cd390b2bfb0f`). B05, `work/ms94`, template-r1 and
the J1 predicates are unchanged.

## Fixed client and process construction

Howard selected Codex 0.160.0. Its SHA-256 is
`4b01d5920e6785614727443bbecf343f4dedbb7347052b72ba805aab6353ef01`.
The installation target is
`C:\Program Files\Lightyear\Codex\0.160.0\codex.exe`, outside the desktop
application's update tree. Installation never replaces an existing binary with
different bytes. Administrator-owned ACLs give the builder and operator read and
execute access. The generated transport plan binds the path, bytes, account SID
hash, process arguments and implementation hashes. This is preparation, not a
measurement plan or model-call authorization.

`tools/ms94_b06_pinned_exec.ps1` constructs a direct credentialed `codex exec`
process under `lyb06builder`, with redirected stdin/stdout/stderr, an explicit
Codex home, disabled shell/apps/multi-agent/web capabilities and the existing
approval policy. Its EOF smoke writes **zero bytes** to stdin and requires a
missing-prompt rejection with no stdout/model protocol. It does not supply a
model, prompt, MCP broker or credentials. The complete B06 measurement adapter,
MCP broker connection, model configuration and end-to-end preflight remain gated.

The separate app-server probe uses the same installed executable and launches
four built-in PowerShell `Get-Content` operations inside its process tree: allowed
file, missing file, tools denial and private-folder denial. It checks the child
and parent SID, actual Codex parent PID and native access-denied code. This is an
OS boundary proof; it does not claim that empty-stdin `exec` generated tool calls.

## Network boundary

An ordinary allow rule for Codex would not restrict other programs on a host
whose default outbound policy is Allow. The new host policy instead uses Windows
Filtering Platform ALE connect filters for IPv4 and IPv6. They block connections
for the dedicated account when the application ID differs from the exact pinned
path. Read-back checks both condition values, layers and block actions. Other
accounts and host firewall profiles are unchanged. No Defender exclusion or
execution-policy bypass is used.

The zero-model probe adds a temporary outbound block for Codex itself, so it
cannot contact the service. For each IP family a host connection proves a local
listener is available; a PowerShell connection under the builder must fail with
WSAEACCES (10013). Both family results are required. No external network
connectivity or successful authenticated model transport is claimed by this test.

Persistent WFP filters survive a launcher crash. Their freshly generated keys
are saved before account enablement in the local `wfp-recovery.json`. Normal
cleanup first disables the dedicated account and ends its remaining processes,
then removes only those filters and the probe's Codex block. A failure is
preserved in its new attempt directory; it cannot produce a passing signed
transport record. No failed directory is reused. If cleanup fails, retain the
account disabled and use its recorded keys for administrator recovery.

## Evidence and current validation

`ms94_b06_pinned_transport.record` binds the actual EOF, network and process
observations to new signed records and a hash-bound transport plan. The ordinary
process proof and Windows denial record are retained separately. `admit_transport`
requires the additional signed pinned-exec proof; the earlier app-server-only
proof cannot admit the new transport. The controller core's older OS-only
`builder_gate` is not by itself full transport admission; the future executable
measurement adapter must call `admit_transport` before any model invocation.

After the successful probe: 116 B06 regression tests passed on Windows, including real
PowerShell syntax parsing and C# SDK structure-layout compilation. These tests
do not install filters, enable the account, run Docker or call models. Synthetic
admission mutants cover wrong client/path/SID, prompt input, unexpected stdout,
single-family evidence, connection refusal versus access denial, signature/file
binding, changed code and missing cleanup.

The first elevation request was canceled before the probe started. Attempt 2
failed before account enablement because the WFP weight range was incorrectly
255 (Windows permits 0–15); it is corrected to 15. Its filters and sublayer were
independently verified absent. Its unnecessarily broad cleanup scan was ended
after confirming the disabled account and absent filters; the new cleanup only
examines the dedicated account's processes if it was enabled.

Attempt 3 passed both IPv4/IPv6 network-denial tests, then failed before Codex
started because PowerShell's protected HOME variable was assigned. The helper
now uses `probeCodexHome`; a real Windows PowerShell test reaches the mocked
process-construction boundary and proves HOME remains unchanged. Seven focused
transport tests passed after the correction. Attempt 3's cleanup records removal
of the temporary Codex block and WFP filters and account disablement; WFP absence
and account disablement were also independently checked. Failed sources and
observations remain local.

Attempt 4 again passed both network checks but Codex rejected the misplaced
`--ignore-user-config` argument before prompt handling. Cleanup completed. The
argument now follows `exec`, as required by this pinned version; the helper also
creates its fresh Codex home before launching. The complete generated argument
string was tested against the actual pinned binary with `--help` and with empty
stdin under the operator identity in a credential-free home (local reject proxy
set for the latter). The latter returned exit 1, empty stdout and exactly
`No prompt provided via stdin.` This operator check is not the dedicated-account
proof. Eight focused tests passed, including the real PowerShell argument-builder
comparison.

Attempt 5 passed from 20:46:56.972 UTC through cleanup at 20:47:10.513 UTC
(13.541 seconds including cleanup). The exact pinned binary rejected empty stdin
with exit 1 and no stdout. All four app-server reads ran under the dedicated SID
with Codex as their parent: public opened, missing returned not-found, and tools
and private reads returned native access denied (5). Both network controls
returned WSAEACCES (10013), while the host's listener controls connected.

New signed denial, process and pinned-exec records passed combined transport
admission. Read-only inspection independently confirmed the disabled account,
absent recorded processes, absent WFP filters/sublayer and removed temporary
Codex block. All earlier failures remain preserved. Qualification and measurement
remain unlaunched; this probe conveys no model-call authorization.
