# Public evidence verifier - draft

`tools/verify_public_evidence.py` (version 1.1.0) reads public evidence and
reports SHA-256 comparisons, receipt self-digests, hash-chain consistency and
Ed25519 signature results. It does not establish that the recorded engineering
result is correct or prove personal authorship of a Tower decision. A service
signature records what Tower attested. Fingerprint publication alone does not
establish trust in a key, a journal head or a decision.

This revision replaces the supplied draft and addresses each static-review
finding listed under "Findings addressed" below. It remains a draft until its
own review and hosted test results are complete.

## Prerequisites and examples

The declared target is Python 3.11 or newer. The standard library is enough for
`manifest` and `all`. The `cryptography` package (pinned to 50.0.1 in
`requirements/public-evidence-verifier.txt`) is needed only for Ed25519 work:
`decision`, `keyinfo` and `--trust-key`. Without it, those commands stop with
exit 2, and `all` reports signatures as SKIP. The pin is a direct dependency, not
a complete transitive lock or a vulnerability attestation.

Use a separate directory containing only the intended public evidence.

```sh
python3 -m pip install -r requirements/public-evidence-verifier.txt
python3 -I tools/verify_public_evidence.py manifest PUBLIC_EVIDENCE --manifest TRUSTED_SHA256SUMS --strict --json
python3 -I tools/verify_public_evidence.py receipt PUBLIC_RECEIPT.json --trust-key PUBLIC_KEY.pem=FULL_64_HEX_FINGERPRINT --strict --json
python3 -I tools/verify_public_evidence.py decision PUBLIC_PROOF.json --public-key PUBLIC_KEY.pem --key-sha256 FULL_64_HEX_FINGERPRINT --expected-head INDEPENDENT_HEAD_SHA256 --strict --json
python3 -I tools/verify_public_evidence.py all PUBLIC_EVIDENCE --trust-key PUBLIC_KEY.pem=FULL_64_HEX_FINGERPRINT --strict --json
```

`-I` reduces Python import-path exposure. The verifier source imports no network
client, subprocess or ctypes module; a test checks this.

Common switches belong after the subcommand. `manifest` supports repeatable
`--manifest` and `--allow-extra`; `receipt` supports repeatable `--trust-key` and
optional `--base`; `decision` also supports `--decision-sha256` and repeatable
`--expect-bound KEY=SHA256`; `all` supports repeatable `--exclude` and
`--trust-key`; `keyinfo` prints public-key fingerprints. `-v`, `-q`, `--strict`,
`--json` and the resource limits (`--max-json-mb`, default 64;
`--max-archive-members`, default 200000; `--max-archive-mb`, default 16384) are
shared subcommand switches. The JSON `tool` value remains `lightyear_verify`.

## Read the coverage as well as the verdict

| Exit | Verdict | Meaning |
| --- | --- | --- |
| 0 | PASS | No FAIL, at least one check verified evidence, and at least one check is anchored (below). SKIP/WARN permitted unless `--strict`. |
| 1 | FAIL | At least one FAIL, including malformed or unreadable evidence. |
| 2 | (none) | Usage or input error, missing or refused path, missing `cryptography` for signature work, or an internal error. Nothing is claimed. |
| 3 | INCOMPLETE | Nothing was verified (empty scan, no recognisable evidence), or `--strict` with SKIP/WARN. |
| 3 | UNANCHORED | Everything is internally consistent, but nothing was checked against a key or manifest you supplied. |

**Anchored checks.** A self-digest, hash chain, sibling binding or a manifest
found next to the files can be recomputed by anyone who edits the files, so on
their own they show consistency, not authenticity. A check is anchored only when
it rests on something the person running the verifier supplied: an Ed25519
signature valid under a key pinned with `--trust-key` or `--public-key`, a
manifest named with `--manifest`, or a journal head given with `--expected-head`
on an authenticated proof. Without at least one anchored check the verdict is
UNANCHORED, never PASS. The JSON `summary.anchored` field counts them.

The JSON `summary.verified` field counts PASS results that check evidence.
Parsing a file, pinning a key, or recording decision context does not count, so
a run whose only PASS lines are of those kinds is INCOMPLETE, never PASS. In
`all`, partial manifests are SKIP and present-file mismatches may be WARN; `all`
does not enforce a complete file inventory, so prefer `manifest` with explicit
manifests for a complete download. Strict mode promotes SKIP/WARN to INCOMPLETE;
it does not add missing checks. HMAC and unsupported signatures are SKIP. A
self-digest or hash-chain PASS is not a signature PASS. No independently supplied
head means no freshness assurance.

Manifests compare raw bytes and optional sizes. Receipt references can accept a
canonical JSON hash instead of a raw byte hash. Canonical JSON uses sorted keys,
compact separators and either UTF-8 characters or ASCII escaping. Signatures
cover the canonical object without `content_sha256` and `signature`. Duplicate
JSON keys, duplicate manifest entries, explicit NaN/Infinity constants and JSON
nested deeper than 256 levels are rejected. A `content_sha256` that is not
lowercase 64-hex on an object carrying a signature, a chain element or a named receipt is a
FAIL. An envelope signature (one with `value` or `key_id`) that has lost its
`algorithm` is a FAIL. A sibling's `content_sha256` counts as a binding
target only when it recomputes from the sibling's content.

## Safety rules

- **Symbolic and hard links are never followed.** A listed path that is, or
  passes through, a symlink, or a file with more than one hard link, is a FAIL in
  `manifest`; an unlisted one is an extra (FAIL); `all` reports each as SKIP; a
  symlinked file or directory, or a hard-linked file, named on the command line
  is refused with exit 2. Files are opened with `O_NOFOLLOW` where the OS has it,
  and only regular files are read. The directory you name may itself sit under
  linked parents; only paths below it are checked. A directory swapped for a
  link while the verifier runs is not detected; run it on evidence nobody else
  is changing.
- **`work/mainframe/arrivals/` is never read.** The check applies to both the
  literal and the resolved path, after Unicode normalisation and case folding,
  ignoring trailing dots and spaces, in every command: walks prune it, manifests
  listing it FAIL, and naming it exits 2.
- **Archives are read in memory, never extracted, and bounded.** Member count
  and declared uncompressed size are checked as each tar header is read, and
  after a zip's central directory is read, so an archive bomb is refused before
  any member is decompressed. Tar extended headers over 1 MiB are refused before
  they are buffered. Each member is decompressed at most once per run, and a run
  decompresses at most 64 GiB in total. A member that yields more bytes than it
  declares is a FAIL. Member names are normalised as an extractor would write
  them (`./a`, `/a` and `x/../a` are all `a`), and a repeated name, including an
  appended tar member, is an `archive-duplicate` FAIL. An unreadable,
  unsupported or over-limit archive is named in the result instead of being
  ignored.
- **Nested digests are bounded.** Re-serialising nested self-digests may use at
  most 16 times a document's size plus 16 MiB; beyond that the document is not
  checked (FAIL when named, SKIP in `all`).
- **Malformed evidence is a FAIL, never a traceback.** Any parse, type or
  unsupported-format error while checking one file becomes a `malformed`, `json`
  or entry FAIL for that file; the run continues with the next file. Output that
  cannot be encoded is escaped, never allowed to crash the report.
- **Private keys in evidence are a FAIL.** `all` reports any `.pem` file
  containing a private key block.

## Decision proofs

Beyond signatures, chain and head, the decision event must show: an `actor.id`;
an `actor.kind` of `human` or `customer` (an allow-list, so `agent`, `service`,
any other value or a missing kind FAIL); `channel` exactly `control-tower`; a
non-empty `roles_held` contained in the decider's latest earlier
`roles_assigned` grant (Tower's own rule); and a session opened exactly once
earlier in the same journal, by the same identity, with an `expires_at`, not
ended by `session_ended`, and with the decision time between its start and
expiry.

A later decision of the same kind, scope, bound and `decision_slot` is a FAIL
(superseded), as in Tower's own verifier. Tower judges "same subject" with a
per-kind rule this verifier does not reproduce, so a later decision of the same
kind with an overlapping bound or a different slot, or any later event of a kind
Tower does not write, is a `decision-superseded` WARN to confirm out-of-band.

Only the `decision` command, with the Tower key pinned out-of-band, can give a
decision PASS. In `all`, a proof whose key is not pinned is checked for
structure only and its semantics are SKIP; if you pinned keys and the proof's
signature is under a different one, that is a `decision-key` FAIL.

Proofs labelled as tests or fixtures (by file name, scope, decision reason,
decider name or role-grant reason) get a `synthetic-fixture` WARN: they show the
verification mechanics only, not a real-world decision. Under `--strict` that
WARN makes the verdict INCOMPLETE.

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

## Tests and report-only CI

`public_verifier_tests/test_public_evidence.py` holds 88 self-contained tests.
Every fixture is generated in a temporary directory by the test itself, so no
repository evidence, Release download or network access is needed and no test
is skipped for a missing fixture. The suite covers positive controls,
tampering, and one test class per finding below. The only private keys are
disposable Ed25519 keys created in memory per test; only public halves touch
disk, in a temporary directory. Those signatures prove the verifier's mechanics
only and establish no trust in any Lightyear key.

The unit-tests job in `.github/workflows/verify-public-evidence-report.yml` runs
the suite on PR changes and main pushes touching the five verifier files, with
Python 3.11 and only `cryptography==50.0.1`, read-only contents permission and no
secrets. The job treats any skipped test as an error. The hosted log is the
record of results; this document makes no claim about them.

The manual `report` job reads one of two existing public Release fixture assets,
checks its full pinned SHA-256, and records `all --strict --json` output without
using the exit code as a merge gate. Signature SKIP is expected without the
original fixture key, and the asset carries a `synthetic-fixture` WARN.

## Findings addressed

| Static-review finding | Change | Test class |
| --- | --- | --- |
| Truncated (16-hex) hash comparison when accepting an extra file | Full 64-hex comparison | `ExtraFileFullHash` |
| Incomplete actor/channel validation | Allow-listed human kinds, exact channel, identity, roles and session checks; fixture labelling | `DeciderIdentity` |
| Inconsistent restricted-path and symlink handling | One no-follow walker and path classifier used by every command; literal and resolved restricted check | `SymlinksAndRestrictedPaths` |
| Malformed-input exceptions | Per-file guard maps errors to FAIL; input errors and internal errors exit 2 | `MalformedInput` |
| Unbounded archive and JSON reads; duplicate archive members | Size, depth, member-count and declared-size limits; duplicate members FAIL; refused archives named | `ResourceLimits` |
| PASS with zero successful checks | INCOMPLETE (exit 3) when nothing was verified; `summary.verified` | `CoverageVerdicts` |
| `cryptography` required at startup | Imported only for Ed25519 work | `OptionalCryptography` |

One further defect was found during the rework: through a symlink, the supplied
draft would parse a file inside `work/mainframe/arrivals/` and report PASS.
`SymlinksAndRestrictedPaths.test_symlink_into_arrivals_not_followed` covers it.

An independent adversarial review of the first rework found further attacks,
each now covered in `IndependentReviewFindings`: a recomputed self-digest alone
reaching PASS (now UNANCHORED); a signature object with its algorithm removed
being ignored; `all` treating a proof under an unpinned key as valid; a sibling's
claimed digest being trusted; uppercase digests skipping the check; tar name
aliases (`./a`, `/a`) shadowing a member; session and role-grant gaps; an
oversized tar extended header, repeated decompression of one member, and
nested-digest re-serialisation exhausting memory or time; an output encoding
crash; hard links into restricted areas; a symlinked directory named on the
command line; an injected file that quotes a trusted manifest's hash; and an
unsupported zip method aborting the whole run.

This report does not establish qualified-run admission, fixture exclusion,
production authorization, promotion eligibility or a complete evidence inventory.
