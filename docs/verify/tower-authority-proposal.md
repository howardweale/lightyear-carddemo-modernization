# Proposed Verify Tower authority

Status: proposed, not provisioned. Howard confirmed no Verify authority exists.
This proposal grants no decision, model call or graph activation.

Use a dedicated non-admin Windows service account `lyverifytower`, scope
`verify-public-reference`, protected authority directory
`C:\ProgramData\Lightyear\VerifyTowerAuthority`, a separate data root and journal,
and loopback port 8768 after verifying that port is free. Do not reuse the B06 or
CardDemo authority, credentials, root, journal or port.

Assign Howard (`howard-weale`) the `operator` and `qualification-approver` roles
for public Verify projection review. The authority must be outside the
engine-writable root. Its private key is readable only by the Tower service
identity and designated administrators, not the builder or Codex account.
Individual login credentials belong to Howard; do not print them into chat.

Before provisioning, obtain Howard's approval of this account, directory, scope
and role assignment. Administrator elevation is required to create the account
and apply ACLs. Preserve existing identities and refuse to overwrite keys.
After provisioning, verify allowed access and denied private-key read-open under
the builder/Codex identity, then show only the public-key fingerprint for Howard
to confirm. This is operator review, not independent attestation.

Only then prepare the actual public INTCALC projection and lane-inventory leak
scan. Publish no private lane values. Present its exact hashes in this Tower;
Howard records the separate approved/rejected decision and expiry. That decision
authorizes public graph disclosure only, not model calls or a campaign.

The Mac isolation commands can run before this authority exists. The approved
graph activation stage must wait for it. Existing B06 services remain untouched.
