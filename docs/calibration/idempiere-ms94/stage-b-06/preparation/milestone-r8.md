# B06 Tower admission and HTTP transport — milestone r8

October 6, 2026. Operator review; not independent attestation.
PRs [#265](https://github.com/howardweale/lightyear-carddemo-modernization/pull/265)
and [#266](https://github.com/howardweale/lightyear-carddemo-modernization/pull/266)
separate Tower setup/smoke binding from builder transport preparation.

## Result

The three-slot J1 smoke has a publicly verified plan and Howard's exact Tower
approval. This is preparation and authorization, not a successful native smoke
or measurement. Zero model calls, Docker commands and native pairs ran in r8.

| Binding | SHA-256 or public commit |
| --- | --- |
| Exact public plan commit | `ec639ba6f56940e235e04b41c1cb3f013c25e568` |
| Executable group content | `df303eb18db2294d5bbc2d912ba4d704b4c25fc6e2a1ae52ebdf645546400bfa` |
| Unchanged r7 snapshot, 2,106 files | `cc2f9522d3be2d7a527780f98de42391ede4d3c7438ddce0dee6cd64fa38b77b` |
| Confirmed Tower public PEM | `65bcec7f9fb46d5a618cd61b8bcd0a74497b9a0c360738781e269ef2d87a6240` |
| Latest operator decision | `2dd8fc24cb7f550c778b83411c1b15943f7a0d433af6c8410eaf078b0f19774d` |
| Setup audit | `e4e51cedfaba112cac85b4c45f5a8f545e560b76dc053ecab93318ce92f99896` |
| Data-root migration record | `5e506124bf67792ed245f935f883f86ed67102fda2cbe2cb106685c8ae805b9d` |

All 11 files at the exact plan commit were fetched and compared byte-for-byte.
The three signed operator decisions authorize the same group; the latest
supersedes the earlier two. The group contains a retained reference, a duplicate
invoice-line mutant and a candidate null dereference with direct diagnostic
delivery. Its window is October 7, 03:00–09:00 UTC (October 6, 8 PM through
October 7, 2 AM PDT). Each slot must have its full 7,190-second budget remaining.
No extensions, replacements or model calls are authorized.

## Tower deployment and preserved failures

The explicitly approved non-admin `lyb06tower` authority is separate from the
agent and builder. Actual private-key read-open attempts under both identities
returned Windows error 5; public controls succeeded and missing-file controls
returned error 2. No key bytes were exported. The Tower account positive control
succeeded. Role-event signature and all 598 installed runtime files were verified.
Administrators remain trusted; this is not protection from a malicious admin.

The initial profile-hosted inbox failed the Tower account's ancestor-metadata
check. The repaired data root is `C:\ProgramData\Lightyear\B06TowerData-r8`.
Six ownership/request/evidence files and the four-event journal were preserved
and verified during migration; the original root remains historical. No authority,
key, credential, runtime or public-plan identity changed. The actual Tower-account
reader now verifies the request as pending, and Howard subsequently decided it.

The earlier provisioning failure, two denial-probe failures and interrupted ACL
repair remain recorded locally. A broader ACL retry was rejected by automatic
approval review; the dedicated data-root repair avoided that access expansion
and removed the unused metadata grant. Details are in [Tower setup](tower-setup-r8.md).
Raw machine SIDs, credentials, captures and private inputs stay local.

## Transport delivered and validation

The host-owned loopback HTTP broker exposes the existing five-tool boundary,
uses a fresh 256-bit bearer token per invocation, checks every method and session,
serializes/deduplicates requests, enforces budgets, and records a replayable
hash chain. Terminal delivery replay binds the host receipt's head/count and
checks actual CLI tool results. Backend failures revoke access with empty output.
The native backend must still enforce its own process deadline and cleanup.

The exec argument builder explicitly chooses the file credential store. The
supervised login helper starts the pinned native executable as `lyb06builder`,
without script-policy changes, batch-logon grants or copied operator credentials.
It has not yet completed a supervised sign-in.

- Full B06 offline suite: 139 tests passed on Windows in 29.881 seconds.
- After the data-root repair: five smoke-trust/decision tests passed in 0.061 seconds;
  the startup helper parsed successfully and the real Tower-account inbox probe passed.
- Real MCP SDK loopback tests passed without a model or native backend.
- The initial #265 macOS CI failure was a CloudBank worker process-cleanup error;
  the equivalent #266 job passed. Final updated-commit CI is required before merge.

See the PR check histories for final commit-specific CI results. No CI retry is a
native qualification retry. Merge does not update the already pinned Tower runtime
or frozen smoke snapshot.

## Remaining against core-status items 1–5

1. Native J2/J3 adapters exist; retained and mutant groups remain natively unqualified.
2. Posting-origin collector/replay exists; full native control qualification remains.
3. Smoke executable inputs, exact public plan and Tower authorization are prepared.
   Obtain a fresh signed Tower journal and satisfy frozen controller checks in-window.
   Full J1/J2/J3 qualification groups remain unrun.
4. Broker implementation exists; actual builder sign-in and the six-step
   account/WFP/pinned-client transport probe remain required. No measurement launcher
   is admitted by offline HTTP tests.
5. Immutable per-journey zero-model preflight and final measurement freeze remain.

B05 frozen evidence, `work/ms94`, template-r1, J1 predicates and existing signed
transport-proof source files remain unchanged. No measurement launch is authorized.
