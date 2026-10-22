# COPAU private prerequisite helper — 22 October 2026

F8 preparation only. This implements steps 1–5 of the [private prerequisites
record on #415](https://github.com/howardweale/lightyear-carddemo-modernization/blob/83a3c892f3d449222f2fa3c0b8f15d24c4622946/docs/factory/copau-f2-prerequisites-2026-10-22.md).
It is a separate main-based change. It does not require #415's code to run.
Publication is not permission to install or execute the helper. Howard first
reviews the final green commit, then separately approves private operation.

## Public and private boundaries

The standalone, standard-library Python helper is
`tools/copau_private_prerequisites.py`. Its only CLI destination is
`C:\ProgramData\Lightyear\FactoryControllerPrivate-v1`. It never reads the Tower
identity, credential, journal or endpoints; never signs a WorkOrder; never calls
a model, sets a credential environment variable, installs a service or starts work.
The new HMAC secret is distinct from the Tower Ed25519 key.

Before private operation, Howard checks for suitable existing material. The
`register-key` and `register-bundle` actions preserve its exact bytes. A different
existing private location needs a separate custody/location review; do not move,
replace or regenerate material just to satisfy this fixed-root helper.

The helper refuses a root overlapping any supplied checkout, workspace, artifact
or other exposed root, a Git ancestor, links/reparse points, hard-linked inputs,
non-regular inputs, permissive private ACLs and existing output names. It checks
file identity before/during/after bounded reads. Files are created exclusively.
On Windows the root is owned by the current user with a protected user-only DACL;
files may inherit only that user's access. Administrators remain a Windows trust
boundary (including ownership of files created by an elevated administrator).
Ancestor replacement permissions for other identities are refused. Run private
actions as Howard, with no concurrent editor/controller modifying these files.
This does not defend against a malicious administrator or the same Windows user.

## Reviewed operator sequence, not an execution request

Use an exact approved checkout and an existing Python 3.13 interpreter. Pass the
complete inventory of exposed roots through repeated `--exposed-root` arguments.
Those paths are ordinary public working directories; never pass secret values
on a command line. The script tree and current directory are also excluded.
Do not run from the private root. No downloads or dependency installation occur.

1. `initialize`: only if the fixed private directory is absent. The existing
   `C:\ProgramData\Lightyear` parent must already be safe. This action creates
   an empty directory with its restrictive ACL, not keys. Parent access may need
   Howard's elevated PowerShell. Subsequent private actions use normal Howard
   PowerShell. No existing ACL is silently repaired or weakened.
2. `create-key --issuer <production-issuer> --key-id <production-key-id>`:
   only when no suitable key exists, after the exact confirmation prompt. It
   creates `work-order-hmac.txt` containing 64 ASCII hex characters from 32
   cryptographically random bytes, without a newline. The runtime consumes the
   UTF-8 characters, not hex-decoded bytes. `register-key` accepts a privately
   placed suitable existing file instead. A private custody record binds its
   digest; that digest is never exported. Howard arranges a private recovery
   copy separately. Never place the key in transcripts, Git, artifacts, CI
   variables, command arguments or a worker environment. This helper does not
   load `LIGHTYEAR_WORK_ORDER_SIGNING_KEY`; future controller provisioning needs
   a separate reviewed private step, scoped only to the controller process.
3. Howard prepares `expected-source.json` privately inside the secured directory.
   It must have exactly these fields: `schema` = `copau-private-source/1`,
   `freeze_sha256`, `amendment_sha256`, private `source_reference`, private
   `coverage_description`, `approved_expected_state_source` = true, and `values`.
   The values must come from the approved frozen judge's controller-private
   expected-state sources. Preserve the private source and coverage provenance.
   Do not substitute arbitrary canaries or a public evidence archive. If the
   approved private source is unavailable, stop: this helper cannot invent it.
4. `prepare-bundle`: after the source/coverage attestation prompt, validates that
   source and creates `copau-expected-values.json`. The runtime format is exactly
   `schema` = `factory-private-expected-values/1` and `values`: 1–64 unique
   strings, each at least 40 characters after whitespace removal/case folding,
   and at most 262144 UTF-8 bytes. Canonical duplicates are additionally refused.
   `register-bundle` validates a privately placed existing bundle against the
   source and preserves its original serialization. Neither action claims to
   independently establish oracle correctness or coverage.
5. `public-metadata --reviewed-commit <approved-helper-commit>`: rechecks the key,
   bundle, bindings and ACLs, then creates `public-prerequisites.json` inside the
   private directory. It prints only a generic success message. Howard reviews
   and publishes **that file only**, never the directory or other files. The
   reviewed commit is Howard's attestation; the exact helper file hash is also
   recorded so engineering can compare it against that commit.

The two pinned public record digests are:

- [Original freeze](copau-factory-judge-freeze-2026-10-18.json):
  `f7f68623af3773c0a71f0d3dc82da4932a5d61993feb01595957179c9cff49ee`.
- [Freeze amendment](copau-factory-judge-freeze-amendment-2026-10-20.json):
  `d226935e37a19b611cff5d05f383d7d37f1835449b36c600abfe913cee3bfe22`.

Any refusal preserves partial outputs for private inspection. Do not retry key
creation or delete an existing secret to get a clean run. No success is printed
on failure and private exception text is suppressed. Recovery is an explicit
operator decision, not automatic rollback or regeneration.

## Public schema and acceptance

`validate_public` is the strict executable schema for `copau-public-prerequisites/1`:
no additional fields are allowed at any public level. The handoff includes a
generated attestation reference, UTC preparation time, helper commit/hash, both
freeze hashes, issuer/key ID/algorithm and custody attestations, and the private
bundle's exact SHA-256, byte count and value count. It includes no private path,
key digest, key bytes, bundle values or private source/coverage descriptions.
It explicitly says source coverage is operator-attested, `signed=false` and
`run_authorized=false`. Public IDs must be intentional public labels, not secrets.

CI exercises real disposable Windows ACLs and junctions, Linux links/modes,
exclusive writes, preservation, schema/size/value limits, frozen bindings,
public projection and redacted failures, using synthetic data only. No operator
file is a test fixture. The existing runtime's private-input format remains
unchanged. F8 stays unready until Howard supplies this metadata plus the Tower
public PEM/fingerprint/head and engineering binds and validates the final request.
