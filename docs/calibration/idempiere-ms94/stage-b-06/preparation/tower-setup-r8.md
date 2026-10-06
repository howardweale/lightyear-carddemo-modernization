# B06 Tower setup and confirmed smoke binding — r8

Operator review; not independent attestation. October 6, 2026.
Zero model calls, Docker commands and native pairs.

Howard approved the new authority and confirmed its public PEM fingerprint:
`65bcec7f9fb46d5a618cd61b8bcd0a74497b9a0c360738781e269ef2d87a6240`.
The private authority remains in `C:\ProgramData\Lightyear\B06TowerAuthority`,
readable by `lyb06tower` and Administrators. The non-admin Tower identity is
separate from the Codex host and `lyb06builder` identities. Howard has the
scope-specific operator and campaign-authorizer roles; no group was authorized.

## Verified evidence

- [Hash-only setup audit](tower-setup-audit-r8.json):
  `e4e51cedfaba112cac85b4c45f5a8f545e560b76dc053ecab93318ce92f99896`.
- [Public verification key](tower-r8.public.pem). The existing campaign key is distinct.
- One Tower role event, signature verified offline through a read-only SQLite
  connection: `906fab7cc6a603e2cb6eb3b71049cb7ad27bbe6441e9ba1ec3fa199e130a4ef7`.
- Tower positive read-open succeeded. Codex and builder private-key read-open
  failed with Windows error 5; public controls succeeded, missing controls
  returned error 2. All probes read zero key bytes.
- Installed isolated runtime: 598 files independently rehashed. Manifest
  `fa8138477e00142e31de5455a7b8f3d6e85a273695ba17110d0708acd5ddf6e0`,
  Tower source commit `bf3f72ea9085b676680575a841c9d48507c50912`.
  Python 3.12.10 AMD64 embeddable runtime came from python.org; archive SHA-256
  `4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3`.
  Only public code and libraries were staged; no private key or user profile.
- Both local accounts were confirmed disabled after cleanup. Tower is not serving.

These ACL checks establish separation from the non-elevated agent and builder.
Administrators remain trusted; this is not resistance to a malicious administrator.
Raw local observations include machine SIDs and stay local. The public audit binds
those observations by file hash and does not claim its own independent signature.

## Preserved failures

Provisioning attempt 1 failed before key creation because the account could not
start the profile-hosted runtime. Attempt 2 used the isolated public runtime
and generated the only authority. The retry refused a nonempty authority folder.
Builder denial attempt 1 stopped at Restricted PowerShell script policy. Attempt 2
failed process creation with an overlong credential-process command line.
Attempt 3 used three short built-in commands and passed. No execution-policy
change, encoded command, Defender exception or key replacement was used.
Every failure and cleanup record remains local under its original attempt name.

## Exact smoke gate

[Executable group](j1-smoke-executable-r8.json) content hash:
`df303eb18db2294d5bbc2d912ba4d704b4c25fc6e2a1ae52ebdf645546400bfa`.
It binds the unchanged r7 snapshot
`cc2f9522d3be2d7a527780f98de42391ede4d3c7438ddce0dee6cd64fa38b77b`
and the confirmed Tower key. Conversion ran with imports from that frozen root,
verifying all 2,106 files and the three private input closures. No frozen file changed.

Three J1 slots: retained reference, duplicate-invoice-line mutant, candidate null
dereference with direct diagnostic delivery. Window: October 7, 03:00–09:00 UTC
(October 6, 20:00–02:00 PDT). Expected about one hour; each maximum is 7,190 seconds.
Full remaining slot budget must fit; no extensions, replacements or models.

Publication of the exact group, byte verification at the public commit, and
Howard's exact `b06-qualification-group` Tower decision are still required.
Confirming the key did not authorize the smoke. No decision is fabricated here.

## Public request and console

The plan was published at `ec639ba6f56940e235e04b41c1cb3f013c25e568`.
`git ls-remote`, a fresh fetch and direct blob comparisons verified all 11 files.
The exact request is
`b06-q-a46318812b318df1f29a82bf409352638e1fe0a4675c37fbf0dbdd0d0600c16b`.
Its evidence binds this public commit; later documentation commits do not change it.

The pinned Tower service was started under `lyb06tower` at
2026-10-06T21:09:30Z on `http://127.0.0.1:8766/`, PID 45340. Its Windows owner
SID was verified. The account was disabled for new logons after startup;
the existing service process remains running. All 598 runtime files were checked
again immediately before startup. No login or operator decision was performed
by Codex. The launch record stays local.

Howard can view his credential in his own Administrator PowerShell console:

```powershell
Get-Content -LiteralPath 'C:\ProgramData\Lightyear\B06TowerAuthority\authority.credential.txt'
```

Paste it directly into the local Tower login, never into chat or repository files.
Review the request, its three slots, exact public commit and October 7 window,
then choose the Tower outcome. Only an `authorized` decision admits the group.
The console is decision-only and does not itself dispatch the smoke run.
`tools/ms94_b06_tower_start.ps1` refuses an occupied port and a changed runtime
or confirmed key; it must not be rerun while this service is active.

## Inbox repair, October 6 21:25 UTC

The initial service marked the request invalid because its path-confinement
reader could not inspect profile-ancestor metadata under lyb06tower. Host-account
validation had missed this identity-specific deployment failure. A slow metadata
ACL repair was stopped; automatic approval review rejected a broader retry.
The single unused metadata grant was subsequently removed.

The safer repair copied six ownership/request/evidence files and the four-event
journal into `C:\ProgramData\Lightyear\B06TowerData-r8`. Bytes, signatures,
sequence and journal head were verified. The original data root is preserved.
The authority, credentials, pinned runtime, plan and request hashes are unchanged.
No private key or credential was copied. The unchanged Tower restarted under
PID 42344. Existing UI sessions require sign-in again. The actual Tower-account
reader now verifies the request as **pending**.

See [migration record](tower-data-migration-r8.json). The startup helper now uses
the dedicated ProgramData root. Future requests must be written there; the old
root is historical and must not be used to start a second writer. No group
decision, Docker command or model call was issued by this repair.

## Operator decision received

Howard recorded three `authorized` decisions for the same request. Their
signatures, journal chain, actor and exact request/plan/snapshot/window/public
commit bindings were verified. The latest superseding decision is
`2dd8fc24cb7f550c778b83411c1b15943f7a0d433af6c8410eaf078b0f19774d`.
This authorizes one three-slot J1 smoke group in the declared October 7
03:00–09:00 UTC window. It does not authorize three groups, a measurement,
replacement slots or model calls. No smoke has run as of this update.
Admission must still obtain a fresh Tower journal and pass the frozen controller's
remaining launch checks inside that window. Operator review; not independent.
