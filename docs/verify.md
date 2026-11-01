# Public evidence verifier â€” draft

This is an unqualified draft adapted from the supplied `lightyear-verifier.zip`.
Static review counted 33 test methods; no tests, verifier commands, key operations,
signature checks, dependency installations or workflows were run during local preparation.
The supplied sample output is historical attachment data, not validation of this
adaptation. Resolve the static-review findings before operational use.

The proposed `tools/verify_public_evidence.py` reads public evidence and reports
SHA-256 comparisons, receipt self-digests, hash-chain consistency and Ed25519
signature results. It does not establish that the recorded engineering result is
correct or that an actor personally signed a Tower decision. A service signature
records what Tower attested. Fingerprint publication alone does not establish
trust in a key, a journal head or a decision.

## Prerequisites and examples

The declared target is Python 3.11 or newer with `cryptography==50.0.1`.
`requirements/public-evidence-verifier.txt` pins that direct dependency; it is not
a complete transitive dependency lock or a vulnerability attestation. The supplied
code requires cryptography at startup even for manifest-only commands. No package
availability, compatibility or vulnerability checks were made in this draft.

The following commands are examples for a later authorized qualification or use.
Use a separate directory containing only the intended public evidence. Do not
point this draft at private data or rely on its exclusion guard as a sandbox.

```sh
python3 -m pip install -r requirements/public-evidence-verifier.txt
python3 -I tools/verify_public_evidence.py manifest PUBLIC_EVIDENCE --manifest TRUSTED_SHA256SUMS --strict --json
python3 -I tools/verify_public_evidence.py receipt PUBLIC_RECEIPT.json --trust-key PUBLIC_KEY.pem=FULL_64_HEX_FINGERPRINT --strict --json
python3 -I tools/verify_public_evidence.py decision PUBLIC_PROOF.json --public-key PUBLIC_KEY.pem --key-sha256 FULL_64_HEX_FINGERPRINT --expected-head INDEPENDENT_HEAD_SHA256 --strict --json
python3 -I tools/verify_public_evidence.py all PUBLIC_EVIDENCE --strict --json
```

Run from a reviewed checkout and install the dependency into an isolated environment.
`-I` reduces Python import-path exposure; it does not restrict filesystem reads or
limit memory, archive expansion, or CPU use. The verifier source has no network
client or subprocess import. The tests do invoke subprocesses and some generate
and use disposable signing keys, so they are a separate execution surface.

Common switches belong after the subcommand. `manifest` supports repeatable
`--manifest` and `--allow-extra`; `receipt` supports repeatable `--trust-key` and
optional `--base`; `decision` also supports `--decision-sha256` and repeatable
`--expect-bound KEY=SHA256`; `all` supports repeatable `--exclude` and
`--trust-key`; `keyinfo` prints public-key fingerprints. `-v`, `-q`, `--strict`
and `--json` are shared subcommand switches. The JSON `tool` value remains
`lightyear_verify` to preserve the supplied report format.

## Read the coverage as well as the verdict

| Exit | Meaning in the supplied implementation |
| --- | --- |
| 0 | No FAIL; SKIP/WARN are permitted unless strict mode is used. |
| 1 | At least one recorded FAIL. |
| 2 | Usage error or caught InputError; some malformed inputs currently escape this handling. |
| 3 | Strict mode with SKIP/WARN and no FAIL; JSON verdict is INCOMPLETE. |

A PASS verdict can have zero successful checks. In `all`, partial manifests are
SKIP and present-file mismatches may be WARN. `all` does not enforce a complete
file inventory. Prefer explicit manifests for a complete download and inspect
`summary` and each `results` entry. Strict mode promotes SKIP/WARN to INCOMPLETE;
it does not add missing checks. HMAC and unsupported signatures are SKIP. A
self-digest or hash-chain PASS is not a signature PASS. No independently supplied
head means no freshness assurance, and matching an expected head only shows
agreement with that supplied value.

Manifests compare raw bytes and optional sizes. Receipt references can accept a
canonical JSON hash instead of a raw byte hash. Canonical JSON uses sorted keys,
compact separators and either UTF-8 characters or ASCII escaping. Signatures
cover the canonical object without `content_sha256` and `signature`. Duplicate
JSON keys and explicit NaN/Infinity constants are rejected. Archive members are
read without extracting them; resource limits and duplicate-member handling
remain review items.

## Tower public-key publication dependency

PR #488 is a draft, not merged, at the retained review head
`3c234e749198c47ee1b795764ae8aed889c8f129`. After that exact public-key change is
reviewed and lands, the intended canonical location is
`docs/security/tower-authority/current.public.pem`, with metadata at
`docs/security/tower-authority/fingerprint.json`. Do not assume either path is
available on main until then. The retained proposed metadata identifies:

- SHA-256 of exact PEM bytes: `658ba69010237ebc143a1e6d2c519f7d2adb1843993bc171c1d015e7b86b0c8a`.
- SHA-256 of DER SubjectPublicKeyInfo: `4c7cc58ceb4a72cd27a1095d0d8047e545c8ee363936885cd4d14c3d9805df80`.

Obtain the expected full fingerprint through an independently trusted channel.
The verifier accepts either convention, while Tower key IDs use the exact PEM
bytes. Re-encoding line endings changes that hash. This Tower key is for human
Tower decision verification; publication does not make it a machine-receipt
signer or an encryption recipient. A public test-fixture proof with an unpublished
fixture signing key remains unverified; do not substitute the Tower key.

## Tests and report-only CI proposal

All 33 supplied test bodies and assertions are preserved. Filename, tools-path
and module-import adaptations remain; fixture decorators now gate unrelated
Release and public-key cases independently. Their evidence path constants remain historical
attachment data; no evidence was accessed at those paths during preparation.
Most tests are conditional on externally supplied fixtures. An eventual run must
report pass/fail/skip counts and actual fixtures used; discovery of 33 methods is
not evidence that 33 tests executed or passed. Hosted PR/push CI runs the
standalone suite with verbose unittest output; no local execution was performed.

The manual `report` job in `.github/workflows/verify-public-evidence-report.yml`
reads one of two existing public Release
fixture assets, checks its full pinned SHA-256, and records `all --strict --json`
output. It neither creates evidence nor runs the test suite. This small report
covers only the selected asset, not a complete Release. Signature SKIP is expected
without its original fixture key. The verifier's original exit code is preserved
in the log and job summary even though it is not used as a required merge gate.
Dependency/download errors remain infrastructure failures. The Release report
job is gated to workflow_dispatch and does not run on PR/push. A separate
unit-tests job runs on PR changes or main pushes touching the five verifier
files. There is no schedule or release-event trigger. No manual dispatch or
Release report run was performed during this correction.

## Unresolved static findings

The supplied behavior was preserved, including defects. The review packet records
these with source line references: truncated hash comparison when accepting an
extra file; incomplete actor/channel validation; inconsistent restricted-path and
symlink handling; malformed-input exceptions; unbounded archive/JSON reads; and
coverage gaps from skipped fixtures or empty scans. These findings block a claim
that this draft is qualified for public verification. No licensing or operational
claims were added.

This report does not establish qualified-run admission, fixture exclusion,
production authorization, promotion eligibility or a complete evidence inventory.
The example Release inputs are synthetic fixtures and remain labelled as such.
The proposed job has no secrets or signing credentials and uses unauthenticated
HTTPS to read the selected already-existing public asset. No workflow was dispatched or run during local preparation. Publishing this
correction enables its PR test trigger but does not dispatch the manual Release
report.

The standalone tests live in `public_verifier_tests/test_public_evidence.py`,
outside the existing `tests/` discovery roots. The new isolated hosted CI job uses `python -B -m unittest discover -s public_verifier_tests -p test_public_evidence.py -v`
in its own Python environment with the exact pinned dependency. Existing
repository extras such as `.[verify]` require cryptography>=46,<47 and must not
be coinstalled with the standalone 50.0.1 pin. The manual Release report job does not
run the test suite; its separate PR/push unit-tests job does. Other workflows
and existing dependency pins remain unchanged.

The test job uses Python 3.11 and only cryptography==50.0.1. It has read-only
contents permission, no secrets or protected environment, and no Release
download or fixture generation. Missing external fixture roots retain the
existing unittest.skipUnless reason, `evidence not available: <path>`. The
retained published tree contains neither the default repo/ nor downloads/
fixture root. Under that absent-fixture condition, AST inspection predicts
31 skipped tests and two executed tests, not 33 passes. The two ungated tests
check a fake private-key marker and an unsafe manifest path; neither generates
or signs keys. This is a prediction, not a hosted execution result. The actual
unittest log and summary remain authoritative. Available fixtures do not cause
skips and all original assertions remain active. Some fixture-backed tests use
disposable in-memory keys if explicitly supplied fixtures make them runnable;
those test signatures never establish public trust or qualification.

Concurrency uses the repository's required branch/main pattern. All earlier
static verifier limitations remain disclosed while a hardened replacement is
awaited. This correction adds no qualification or fixture-exclusion claim.
