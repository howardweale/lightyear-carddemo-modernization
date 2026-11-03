# External custody signing handoff

Planned route: [option A and the revised planning dates](custody-option-a-20261103/decision.json#sha256=9ee96e111ee019003192f2c0988b696985b06bfeb74757660e389949cff43acf).
This component checks public replies from an isolated human signer. It has no
private-key loader, signer command, network connection, Git subprocess, native
owner, admission or activation path. Not yet: controller integration, a usable
operator signing command, Tower delivery/outbox, native qualification or P5 closure.

## Public protocol

1. The admitted controller obtains the exact source commit, work-order digest,
   run, case, attempt and original expiry from its trusted state. It supplies the
   original same-process monotonic deadline too; neither deadline is restarted
   for signing. Public keys and their exact file digests come from a separately
   reviewed designation. A reply cannot choose its own trust key or context.
2. For a controller envelope, `controller_payload` adds `custody_signing` to a
   canonical unsigned body. The owner seals and durably journals these exact
   bytes **before** handing them to the human. Signing uses the existing envelope
   format: Ed25519 over those canonical body bytes, `content_sha256` of those
   bytes, and a signature key ID equal to SHA-256 of the exact PEM public file.
   The reply must contain exactly that body and the two envelope fields.
3. For a candidate commit, `candidate_message` appends the complete custody
   binding as a canonical trailer **before** the controller creates and seals
   the unsigned commit object. The controller retains its exact object bytes,
   including tree, single parent, author, committer and provenance trailers.
   The human returns the same commit with its OpenSSH `gpgsig` header added.
   Verification accepts only the single designated `factory@lightyear.invalid`
   OpenSSH Ed25519 allowed-signers entry and SSHSIG namespace `git`.
4. Reply verification compares bytes and bindings, verifies the signature and
   checks both deadlines before and after verification. The caller receives a
   payload digest or commit object ID. This is signature validity only; it is
   not a controller-origin attestation, admission, ownership proof or GO verdict.

The SSHSIG reader follows the [OpenSSH protocol](https://github.com/openssh/openssh-portable/blob/master/PROTOCOL.sshsig)
with a deliberately narrow profile: version 1, Ed25519 keys, namespace `git`, empty
reserved field, SHA-256 or SHA-512, no trailing binary data, and bounded armor.
Commit requests accept four headers (tree, one parent, author, committer), with
no merge parents, pre-existing signature or extra headers. Supporting other
formats requires a separate review. Controller JSON must be canonical, bounded
and free of duplicate keys; the public PEM must be canonical Ed25519 SPKI.

## Integration work still required

Not yet: `CandidateHistory` accepts this external path. Its existing exact signer
guard is untouched; no new arbitrary callback becomes trusted. Integration must
replace the old CI-private-key dependency with a concrete external adapter,
preserve model provenance and every existing audit, and bind the revised message
and receipt schema into the final source candidate. The new helpers must not be
used to reconstruct an expected request from a returned packet.

`PublicSigningHandoff` adds a persistent public handoff for one live owner. It
requires distinct public keys for the two roles and retains each exact request
before returning it for export. The reply slot is consumed before size checks,
deadline checks or signature verification. Invalid replies and uncertain writes
stop the object; an existing database cannot be reopened to resume. Each role has
one export and one reply under the original deadlines. This is a component API,
not yet a production controller path or usable operator command.

The local SQLite profile uses rollback journals, `synchronous=EXTRA` and
`fullfsync=ON`, following the [SQLite synchronization documentation](https://www.sqlite.org/pragma.html#pragma_synchronous).
Not yet: native power-loss qualification, exclusive filesystem ownership or
protection from hostile database rollback. The controller must authenticate the
designation and bind exactly one database to its admitted attempt; a caller can
otherwise choose another path. No caller-supplied digest establishes that trust.
`SIGNATURE_VERIFIED` records cryptographic validity only: a final deadline failure
can prevent delivery even after that row is stored. It is never a GO receipt.

Not yet: human transport, exact public signer designations, revocation checks,
timeout ownership or all-process quiescence. The Mac owner and Tower adapter must
enforce those separately, including an immutable outbox and hash/case/attempt-bound
authenticated acknowledgment. A late response, late import, missing acknowledgment
or ambiguous result must never upgrade failure. Not authorized: crash recovery.

Before any private input, the native owner must establish exclusive process
control and prove cleanup against the original deadline. Callback assertions,
PID scans, EOF and process-group emptiness do not establish that proof. No
disposable result may be relabeled as a production-controller receipt.

## Human actions and limits

Howard is the Mac operator and custodian of both separate dedicated signing keys,
with A/A and PIN once / touch always retained, under the [operator decision](custody-operators-20261103/decision.json#sha256=09e8e80db3cf62302a98ed627ce306749197c28bd2e9a51e8efc7b823389c19d).

Planned later: designate separate controller-envelope and candidate-commit public
keys, fingerprints, scope and revocation terms; retain Tower authority solely
for its existing human-authorization role. Keep private signing identities in
the isolated account. No PIN, PUK, serial, private key or age identity file is
needed in chat, GitHub, CI or the factory. The age A/B recipients remain
encryption-only; this change does not select signing keys from them.

For each separately admitted window, review the sealed digest and exact context,
use the reviewed local command when available, and return public signatures only.
Keep PIN once / touch always, unplug after every window, then log out. Begin the
next window with a freshly inserted key. Exact-head merge and spend decisions
remain separate. No command in this document grants execution permission.

CI regressions cover valid signatures, altered payloads, key/context replay,
duplicate or malformed data, deadline exhaustion during verification, and an
independent OpenSSH verification of disposable test signatures. Not yet: CI
results for this change, real signer handling or native qualification.

The handoff regressions cover persistent export/consumption order, duplicate and
concurrent replies, expiry after a verified commit, ambiguous commit results,
context/payload/state tampering, changed owner PID, hardlinks, existing sidecars
and refusal to resume. Not yet: host crash/power-cut tests or complete-route proof.
