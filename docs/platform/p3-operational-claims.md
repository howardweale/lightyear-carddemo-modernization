# P3 operational-prose evidence gate

This increment extends the existing commit-claim entry point. It checks added
prose in Markdown, HTML and JSON under `docs/`, plus the public `index.html`.
It also rechecks existing linked assertions when their receipt bytes change or
disappear. The existing generated-status and commit provenance checks remain.

The lexical categories cover installation/activation/deployment, decisions,
execution, z/OS verification and CI outcomes. Each clause requires either an
explicit **Planned:** or **Not yet** prefix, or a public JSON receipt of the
matching category with an exact byte digest on its link. A future-work marker
cannot exempt a later actual claim separated by a sentence, semicolon or contrast.

## Receipt link contract

Use a relative Markdown receipt link or an HTML anchor, with
`#sha256=<full lowercase SHA-256 of exact JSON bytes>` on the target. The target
must be a committed regular file under `docs/`. A missing, altered, linked or
unknown-schema receipt fails closed. A CI receipt cannot support an installation
claim; a point-in-time installation receipt cannot support a decision claim.

The existing `factory-first-install-acceptance/1` public record has an explicit
installation-only adapter. Other evidence can use `public-operational-receipt/1`:

| Field | Required meaning |
| --- | --- |
| `kind` | `installation`, `decision`, `execution` or `ci` |
| `status` | `completed` |
| `historical_only` | `true`; no ongoing authority or currentness inference |
| `source_commit` | Exact 40-character source identity |
| `evidence_sha256` | Exact 64-character public evidence digest |
| `observed_at` | Timestamp with UTC or explicit offset |
| `public_url` | Repository CI run/artifact, operator issue/PR comment, or Release asset |
| `conclusion` | `success` for a CI receipt |

Such a metadata wrapper needs independent evidence review in its own PR; the
checker does not create one or treat its author as an authority. This gate checks
link, category, schema and retained-byte consistency. It does not establish that
arbitrary prose is true, download external evidence, verify a cryptographic
signature, or confirm that a service is running now. Exact-head human review
remains necessary. A bare CI URL elsewhere in a document is insufficient.

## History and audit

Unchanged historical prose remains byte-for-byte intact. A date in a newly added
filename provides no exemption. Newly copied or renamed prose receives the same
check as other additions. The audit function inventories pre-existing lexical
claims without recognized clause-local receipts, with path, line, claim digest
and source-file digest; it records unreadable sources as errors.

Planned: retain the one-time historical audit as a new dated list after CI
generation and independent review. That list is unfinished in this increment;
there is no claim that all historical prose already satisfies the new contract.
No audit entry grants authority or an exemption to future changes. Some audit
entries will be descriptions or old evidence using unsupported schemas; those
need review, rather than automatic factual accusations or rewritten history.

## Validation and limits

Sixteen synthetic CI tests cover the exact MS-106 installation sentence,
matching and mismatched receipts, explicit future markers, clause isolation,
changed/deleted/link-mode evidence, traversal, backdated additions, historical
audit, JSON/HTML handling, fenced examples and the real commit-check entry point.
The original tests remain intact. No local tests or repository runtime are part
of preparation. This is an evidence-link gate for the listed lexical forms;
arbitrary paraphrases and claims embedded in executable code examples remain
outside automatic classification and require review.

P1 remains higher priority. P4 and P5 follow. Java idiomatic-index change: zero.
