# B05 archive publication proposal — no upload authorized by this document

The proposed destination is a GitHub release, `ms94-b05-evidence-v1`, attached
to a reviewed commit on `main`. Keep the 31 original ZIPs as separate assets,
named `b05-<phase>-<trial>-attempt-<attempt>.zip`. Publish their signed receipts,
the public verification key, an asset-to-receipt manifest, dependency locks and
a clean-room offline replay runbook alongside them. Do not commit the archives
to Git history or combine them into one large ZIP.

## Measured size and identity

The 31 local archives total **3,529,643,030 bytes (3.53 GB; 3.29 GiB)**.
Individual archives range from **109,344,165 to 115,421,072 bytes**.
Each is well below GitHub's current 2 GiB limit per release asset. GitHub permits
up to 1,000 assets per release.
[GitHub release documentation](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases).

The [proposed asset inventory](archive-publication-inventory.json) records exact
sizes, ZIP hashes, signed manifest hashes and signed receipt hashes. The local
inventory pass checked all 31 receipts and manifests against the existing public
key and checked every ZIP hash and byte count. It did not create new verdicts.

Decoding deduplicated manifest files produced 229,562 unique files containing
15,313,084,526 bytes. This is an inventory across all archives, not the working
disk requirement for replaying one archive. A release rehearsal must measure peak
space on a clean machine before specifying a supported minimum.

## Leak check: not yet cleared for release

A read-only scan decoded every unique manifest file using the publication
format's identity, gzip and component encodings, verified its content hash, and
recursively inspected nested gzip/ZIP content. It inspected 233,767 unique
content objects and 16,079,912,203 bytes including nested contents. The scan
looked for private-key blocks, common OpenAI/GitHub/AWS credential patterns,
bearer tokens, URL credentials and credential assignments. It found no matches
for the first six pattern categories. That is a bounded pattern-scan result,
not proof that secrets or personal data are absent.

There were nine credential-assignment finding records:

- Four decoded capture files contain populated password fields in `AD_User`
  (both engines), `CM_Media_Server`, and `C_BankAccount_Processor`.
- Two capture files contain a password-related SQL predicate in
  `PA_DocumentStatus.WhereClause`; these are query text, not account passwords.
- Three implementation files contain credential-related source/test expressions
  requiring classification as references or fixtures rather than live secrets.

Values and credential hashes are deliberately omitted from this proposal. The
local scan retains paths and finding fingerprints for review. The populated
database password values have **not** been established as exclusively public,
non-live demo seed data. They block a release recommendation in their current
unreviewed state.

The archives also contain native row captures, checkpoint/history evidence,
reference sources, model transcripts and local runtime configuration. Their
disclosure is broader than the safe terminal JSONs already on `main`. Review
must cover identity/contact data, endpoint and filesystem metadata, hidden
expected values, reference-source disclosure, upstream licensing and seed-data
provenance. A literal-pattern scan does not clear those categories. No Maintec
record values are authorized for this release.

## Proposed release gates, in order

1. Classify every flagged value locally. Compare demo claims to a pinned public
   seed artifact or documented fixture, recording provenance without copying
   passwords into the review. Check all credential-bearing columns, including
   values the regex may miss, and inspect personal-data and configuration fields.
   Run an independent scanner with pinned rules over the decoded contents.
2. Produce a disclosure report identifying exactly which original archives can
   be released. If any contains protected data, keep the original private.
   Never silently redact or re-sign it: its existing receipt binds the exact
   bytes. A derived sanitized bundle would require a separate signed identity,
   a fresh replay test, explicit limitations and separate approval; it must not
   claim byte identity to the original B05 publication.
3. Rehearse a fresh offline replay using only the proposed release assets and
   public dependencies. Bootstrap the exact hash-matched replay implementation
   from the signed inventory, rather than assuming current `main` has the same
   bytes as the frozen executable. Pin the trusted public-key hash through the
   reviewed repository record. Refuse path traversal, duplicate members, missing
   blobs, unexpected files and any digest/signature mismatch before execution.
   Require all 31 full-entry, complete-gate, diagnostic, calendar, provenance,
   delivery and operator-review replays to match. No signing key, model service
   or live database is needed for offline replay.
4. Present Howard with the exact release manifest, disclosure report, clean-room
   replay report, release commit and asset sizes **before uploading anything**.
   Obtain approval for that exact payload, including any reference/checkpoint
   disclosure. Publishing this proposal is not approval to upload archives.
5. After approval, upload the unchanged approved ZIPs and small companion files
   as release assets. Download every public asset, compare its bytes/hash against
   the approved manifest, and publish the verification results and replay command
   in this results directory. Add a DOI-backed mirror only as a separately
   approved follow-up if long-term archival permanence is wanted.

Until these gates pass, outside readers can inspect the published signed audit
and receipts but cannot independently replay all 31 archives from public assets.
The existing terminal audit remains valid as a local audit; it is not a public
availability claim. B05 remains frozen, B04 remains void, and no upload has been
performed. Review is operator review, not independent attestation.
