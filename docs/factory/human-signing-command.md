# Human-only signing command on DarkFactory

Planned command: `PYTHONPATH=src:. python3 -m tools.human_signing`.
Not yet exercised on the Mac/YubiKey; signing interoperability and native/P5
qualification remain pending. No factory/CI entry point invokes the device path.

Howard's two public keys, policies and creation report are recorded in the
[human return](signing-key-a-20261105/human-report.json#sha256=4092d8758d347e082d625e49b2c111252cd959b08a1980f9adb6e6208eb8fdc2).
The fixed public registry is `lightyear_execution.signing_key_a.PUBLIC_KEYS`:
controller-envelope A/9c (wire purpose `controller-receipt`), candidate-commit
A/9a; lightyear-A, DarkFactory, Howard as custodian and revocation contact.
The hashes identify exact LF-terminated PEM bytes, not OpenSSH fingerprints.
Key B has no signing role. Losing/revoking either A key invalidates the pair.

## Prepare public designation bytes

Use independently reviewed source and work-order hashes, not a guessed final E.
This public-only step produces an **unsigned** record for separate approval.
It neither opens a window nor admits a run.

```sh
PYTHONPATH=src:. python3 -m tools.human_signing prepare-designation \
  --source-commit "$REVIEWED_SOURCE_COMMIT" \
  --work-order-sha256 "$REVIEWED_WORK_ORDER_SHA256" \
  --output scoped-designation.json
```

The designation contains both exact public PEMs, role/slot mapping, raw key IDs,
OpenSSH keys/fingerprints and candidate allowed-signers digest.
The generic preparation API retains false device-attestation, preflight,
possession and native-qualification flags; the separate human report is not
silently promoted into those claims.

## Before Howard signs

Use the dedicated standard non-admin account and a local interactive Terminal
on DarkFactory, with only A inserted. Do not expose the token or terminal to
agents, CI, remote shells or candidate code. No installation is automatic.
The reviewed adapter requires Python >=3.11, the repository cryptography
dependency, yubikey-manager **5.9.2** in that same Python environment, and
firmware **5.8.0**. Existing ykman CLI installation alone does not establish that
Python can import its SDK. Resolve packaging in an attended preparation step;
do not change keys, credentials or management-key configuration.

Obtain the original sealed `external-signing-request/1` packet, its digest,
context digest, reviewed scoped designation/digest, and current revocation
snapshot/digest. Use a separate public channel whose origin Howard must verify.
Review the exact payload and approval before typing the command's confirmation.
Never derive the expected hashes solely from the untrusted packet being checked.

The canonical revocation snapshot has exactly these fields:
```json
{"schema":"human-signing-revocations/1","designation_sha256":"<approved digest>","issued_at":"<offset timestamp>","expires_at":"<offset timestamp>","revoked_raw_key_sha256":["<revoked raw-key SHA256 if any>"]}
```
Use an explicitly reviewed current list (possibly empty), never an assumed
empty list. Timestamps and hashes above are placeholders, not runnable values.
Revocation of either key stops both roles. No revocation service is contacted.

## One explicit operation

```sh
PYTHONPATH=src:. python3 -m tools.human_signing sign \
  --role controller-envelope \
  --request request.json --request-sha256 "$APPROVED_REQUEST_SHA256" \
  --context-sha256 "$APPROVED_CONTEXT_SHA256" \
  --designation scoped-designation.json \
  --designation-sha256 "$APPROVED_DESIGNATION_SHA256" \
  --source-commit "$REVIEWED_SOURCE_COMMIT" \
  --work-order-sha256 "$REVIEWED_WORK_ORDER_SHA256" \
  --revocations revocations.json --revocations-sha256 "$APPROVED_REVOCATIONS_SHA256" \
  --output controller-reply.json
```

For a candidate request, obtain separate approval, then use `--role candidate-commit`
and a new output filename. The command wraps a Git SSHSIG namespace `git`
signature into the exact retained commit bytes; it never runs Git or updates
a ref. Controller signatures cover the raw canonical envelope payload.
The direct-controller message ceiling is conservatively 1,024 bytes pending
native interoperability; larger messages stop, never silently hash/sign a
different message. Candidate signing covers the defined SSHSIG SHA512 framing.

The tool checks the entire packet before hardware access, prints role and
public bindings, and requires a typed request-digest confirmation. It verifies
both slots' keys, GENERATED origin and PIN ONCE/touch ALWAYS before requesting
the current PIN once through /dev/tty, then one physical touch. No PIN argument,
environment variable, file or IPC field exists. No management authentication,
key creation/export, certificate writes, resets or credential changes occur.
The SDK follows [Yubico 5.9.2 PIV](https://github.com/Yubico/yubikey-manager/blob/5.9.2/yubikit/piv.py);
candidate framing follows [OpenSSH SSHSIG](https://github.com/openssh/openssh-portable/blob/master/PROTOCOL.sshsig).

## Fail-stop and return

The fixed local journal is
`~/Library/Application Support/Lightyear/human-signing-attempts`.
An exclusive durable intent consumes each source/work-order/run/case/attempt/
role before any hardware call. Changing request/context/expiry cannot re-enable
it. Do not delete, relocate or roll back this journal to retry an ambiguous
operation; it is a local safety mechanism, not rollback-resistant native proof.
A timeout/error/wrong PIN/disconnect stops without retries. The parent terminates
then kills the bounded hardware worker on failure; no automatic recovery exists.
If cleanup is unconfirmed, unplug A immediately.

Both the wall expiry and a same-process elapsed-time bound are checked before
and after signing. This local bound does not replace the admitted controller's
original monotonic deadline. The receiver must still use its retained request,
original deadline/journal and existing public verifier, and reject late output.
The tool publicly verifies the returned signature before emitting reply bytes.
A result receipt records digests only. A missing success/result receipt, partial
output or error means stop; a file's existence alone never proves completion.
No automatic send, Tower import, admission, production activation or P5 claim.
Unplug all keys before logout; freshly insert for the next attended window.

CI-only disposable fixtures cover both verifier roundtrips, optional independent
OpenSSH verification, substitution/revocation/expiry refusal, policy checks,
durable no-retry intent and worker cleanup. No hardware imports in normal test
discovery and no local tests or signatures are part of implementation.
