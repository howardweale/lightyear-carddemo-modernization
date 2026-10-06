# Verify graph context implementation

Date: 2026-10-05. Base: main
`d2c59494ce0d1286b32cffa6925a2e143f174b8e`.
Operator review; not independent attestation.

## Behavior

An operator can build a deterministic, signed public-source graph projection,
have the judge scan it against its lane evaluation inventory, and request a
hash-bound Tower decision. Unknown provenance, runtime/reference dependencies
and private visibility are excluded. Approved source bytes are checked against
the explicit INTCALC policy; evidence text cannot replace them.

The toolkit registers five bounded read-only graph tools only after approval,
signature, hash, lane, mode, customer and expiry checks. It uses the existing
GraphExplorerIndex with source/publication loading disabled. Default-off startup
retains the original ten tool names and schemas. Graph-enabled decode adds
record paging, field selection and summary without changing the default-off
interface. Receipts use schema v2 with the configured context hash; v1 keeps
its original signed bytes with null context implied.

Tower shows projection status and receipt context, and opens the matching
decision from its authenticated history. Toolkit query telemetry is local,
untrusted and never used as judge evidence.

The [operator guide](graph-context-operator.md) covers keys, source and lane
bindings, file separation, requests and startup. The
[A/B draft](specs/graph-context-ab.md) fixes a proposed sample and stopping
rules; it grants no permission for live calls.

## Deliberate privacy details

Confidential mode redacts every source literal, not a watch-list-dependent
subset, so redaction positions cannot expose private watch-list membership.
The signed eligibility certificate omits detailed scan counts and locations.
The full report remains judge/operator-side. Judge initialization checks that
the scan covered its exact evaluation inventory. Source-literal matches remain
failed scans unless each hash is explicitly acknowledged in a Tower reason;
other protected matches cannot be waived.

The tools only transform already approved public source and already visible
verdicts. The existing judge disclosure policy and cumulative attempt budget
are unchanged. This preserves the stated judge-mediated leakage argument
subject to the projection's source/provenance boundary; a keyword scan alone
does not prove arbitrary graphs safe.

## Local validation and limits

The final Windows regression run exercised 293 tests across Verify, the smoke
kit, Tower, Console, graph explorer, B06 and milestone documentation:
275 passed, 17 platform-specific skips, and one existing Tower HTTP test failed
with Windows connection-aborted error 10053. That exact test passed on an
isolated rerun (4.400 seconds), with no implementation or test change.
The original failed result is retained here. The combined run took
100.764 seconds.

All 17 graph tests passed in the combined run, including real signed Tower
approval, provenance mutants, deterministic/public-fixture construction,
leak detection, evaluation binding, confidential byte independence, default
tool-schema compatibility, expiry, cursor/response limits and signed receipt
versions. The public ACCT-CURR-BAL check finds CBACT04C paragraphs.

JavaScript syntax, whitespace and protected-path checks passed. A Windows
graph CI job is included; its initial local checkpoint preceded remote CI. Linux
separate-user/bubblewrap acceptance and live-client tests have not been rerun
on this Windows host. No improved model effectiveness or cost is claimed.

Zero Docker and zero model calls. No B05 evidence, B06 implementation,
template-r1, work/ms94 or GraphContextAssembler changes. No generated graph
projections, private data, watch-lists, credentials or signing keys are included
in the review commits.

## Review units

1. `3c3495d` (`codex/verify-graph-projection`): projection policy/commands,
   Tower approval/status and receipt binding.
2. `41c0af9` (`codex/verify-graph-toolkit`): five optional toolkit tools,
   decode paging, operator documentation and CI.
3. Prospective A/B design and this implementation record (documentation only).

Public review units are [projection #259](https://github.com/howardweale/lightyear-carddemo-modernization/pull/259),
[toolkit #260](https://github.com/howardweale/lightyear-carddemo-modernization/pull/260), and
[comparison/milestone #261](https://github.com/howardweale/lightyear-carddemo-modernization/pull/261).
CI and merge status are recorded by those PRs. Each retains the zero-model boundary.

## October 6 publication validation

The [Windows graph CI job](https://github.com/howardweale/lightyear-carddemo-modernization/actions/runs/37508345006/job/112422651286)
passed on toolkit head `871f31efd9ab08ef77fd9d7ac158643d76bf70f0`:
285 tests ran, 17 platform-specific skips, no failures. This includes 47 Verify,
123 B06, 51 Tower, 50 Console and 14 graph-explorer tests. The protected-path
check passed. Existing platform skips do not establish Linux isolation.

An unrelated hosted CloudBank source-build plugin failed to load Jansi during
initial PR259 CI, cascading into a missing local common artifact. The original
failure remains in its job log. [PR263](https://github.com/howardweale/lightyear-carddemo-modernization/pull/263)
is a separate CI-only Maven 3.9.11 pin with Apache's SHA-512; every existing
build and test remains enabled. Its result and the final merge states are
recorded by the linked PRs. No new model calls or local Docker runs were made
for publication.

## Post-merge review follow-up

The [review remediation record](graph-review-remediation.md) separates the
public-overlap and Tower usability fixes from the still-required real projection
approval and Linux activation. The [Tower user manual](../control-tower-users-manual.md)
now gives the CardDemo intake sequence, including normalization before an immutable
verdict. Historical October 4 results remain unchanged.
