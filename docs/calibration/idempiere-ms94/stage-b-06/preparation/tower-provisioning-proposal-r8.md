# B06 Tower authority setup proposal (approved and executed)

No existing B06 authority was located in the checked repository/worktree Tower
directories, matching ProgramData locations or LocalAppData locations. Howard
does not know its location. This does not prove one exists nowhere else.
No private key or operator credential was opened during that search.

Howard approved these boundaries and confirmed the resulting fingerprint on October 6:

| Item | Proposed setting |
| --- | --- |
| Windows host identity | New non-admin local account `lyb06tower`, distinct from `lyb06builder` and the Codex host account |
| Authority | `C:\ProgramData\Lightyear\B06TowerAuthority\authority.json` |
| Private material | Same authority directory, ACL restricted to `lyb06tower` and Administrators; no inherited user read grants |
| Data root | `work/b06-tower-r8` under the verify-smoke-kit checkout, outside the authority directory |
| Scope | `ms94-b06` |
| Human identity | `howard-weale`, display name `Howard Weale` |
| Roles | `operator`, `campaign-authorizer`, explicitly journaled for this scope |
| Listener | Loopback port 8766, only if unused; never replace another listener |
| Source | A committed, reviewed Tower implementation; record its exact commit and source hashes before use |

The human credential is delivered only in Howard's supervised console. Codex
does not read it, log it or use it to issue decisions. Generate the key under
the Tower account rather than generate it in the Codex process and move it.
Do not reuse the campaign signing key or copy another authority's private key.

After account/ACL setup, run the repository's existing `provision` command as
`lyb06tower`, with `--scope ms94-b06 --operator-id howard-weale --operator-name
"Howard Weale"`. It creates the identity with **no roles**. Only after the
explicit setup approval, use `grant-roles` for the above two roles, recording
the operator's reason. Provisioning grants no group or model-call permission.

Required checks before smoke-plan publication:

1. Record public PEM fingerprint and obtain Howard's confirmation.
2. Verify actual access denied (not missing file) for a read-open of the private
   key under the non-elevated Codex host identity and under `lyb06builder`.
   Do not read key bytes. A Tower-account positive control must succeed.
3. Verify the public-key identity differs from the campaign key and that the
   B06 journal/scope is fresh and belongs to this authority.
4. Bind the confirmed public key to the unchanged r7 smoke snapshot's new group
   plan, publish safe hashes only, verify public bytes and create the request.
5. Howard logs into Tower and explicitly decides `authorized` for that exact
   plan, snapshot, public commit and window. Only that decision may admit the
   conditional smoke. No decision is fabricated by this setup process.

This proposal does not enable an account, change an ACL, install a service,
create a key, grant a role, start Tower, run Docker or call a model. It does not
extend the conditional October 7 03:00–09:00 UTC smoke window.
