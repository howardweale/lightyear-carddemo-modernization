# Public designation preparation: two signing roles on key A

Planned integration accepts two different Ed25519 public keys for controller
envelopes (A/9c) and candidate commits (A/9a). Key B remains an encryption-only
off-site backup. The additive preparation module has no hardware API, private
key loader, subprocess, transport, signer, admission or production activation.

`prepare_designation` produces canonical public designation bytes and candidate
allowed-signers bytes compatible with the existing public signing handoff. It
distinguishes SHA256 of exact PEM bytes, SHA256 of raw Ed25519 bytes, and the
OpenSSH SHA256 fingerprint. Slot, PIN ONCE and touch ALWAYS fields are intended
human declarations; they are not device inspection or signature proof.

`verify_designation` requires an independently authenticated expected digest,
designation ID, source/work-order binding and explicit current revocation
snapshot. Revocation identifiers are SHA256 of the raw Ed25519 public key.
Revocation of either role refuses the complete pair because both share one
device failure domain. Unknown fields, changed policies/slots, identical keys,
scope substitution and noncanonical bytes fail closed.

`handoff_parameters` returns only the public-key keyword arguments for
`PublicSigningHandoff`. The integrating controller still owns admission,
original deadlines, attempt identity, actual designation approval, revocation
freshness and all native evidence. No existing production call site changes.

The registered public keys and the separate human-only command are described
in [the command guide](human-signing-command.md). Not yet integrated into
CandidateHistory, CICommitSigner or the orchestrator. Not yet demonstrated
signing interoperability on hardware or qualified for P5. Existing gates, fences and required checks remain unchanged.

Earlier signatures remain cryptographically verifiable with their original
public keys and signed bytes. Historical trust after compromise additionally
depends on preserved designation/revocation records and reliable timing; this
module neither erases old signatures nor retroactively declares them trusted.

Validation: CI discovery includes public RFC8032 fixtures for role separation,
format compatibility, fingerprint identity, scope/digest binding, revocation,
malformed records and attempted proof/secret-field insertion. No local tests,
hardware signatures or real key generation are part of this change.
