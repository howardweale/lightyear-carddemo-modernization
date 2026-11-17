# Graph-on run implementation (no PR yet, r1): Patch A

Planned: this opt-in library reuses G2's approved-projection loader, in-memory
GraphTools index, lexical search, HMAC cursors and four read methods. It has no
provider, judge client, network endpoint, signing operation or activation CLI.
The existing G2 route and its planner/analyst policy remain unchanged. Patch C
will connect this boundary to the separately reviewed five-round controller.

Planned: before indexing, a reviewed inventory binds exact public source bytes,
node identities, kinds, property names, excerpt ranges/hashes, dependencies and
allowed relations. Source excerpts are reconstructed from those bytes. Original
node source text, workload status, verification links and arbitrary properties
are not copied. Unknown or cyclic provenance refuses, including dependencies
through DERIVED_FROM edges. No modern, scenario or test identity is admitted.
Rule text is limited to the three reviewed INTCALC rules and their exact public
source hash and line anchors. There is no model-generated rule admission.

Planned: the approved projection must already equal the filtered payload before
GraphTools constructs an index. Trust binds profile and inventory hashes; the
existing approved loader verifies signatures, Tower approval and projection
integrity. The manifest binds the profile hash and exact snapshot digest.
There is no post-approval filtering, embedding index, reference-output access,
explain_divergence or graph_guidance endpoint on this boundary.

Planned: planner gets up to eight calls in phase zero. Initial builder and five
repair builders get three calls per phase, 26 calls total. Pagination spends a
call. Arguments are at most 1,024 encoded bytes; complete responses are at most
7,168. All results pass closed serializers and the caller's existing controller
isolation scanner. The caller must supply its reviewed canary inventory; a noop
scanner is not an approved activation configuration. Scanner/expiry failures
poison the session. Budget and query-turn accounting, complete transcripts and
the 8,192-byte whole-exchange cap belong to Patch C, not this standalone boundary.

Planned tests use synthetic source and canaries, real G2 query/index methods,
and a mocked approved-loader return. They prove the filtering/serializer boundary,
not production trust or operator attestation. Existing G2 approval tests remain
the separate proof for signature/Tower verification. No hidden case input is used.
The exact production snapshot and actual rolling-context size proof remain
blocking; this packet supplies neither and authorizes no graph activation.

Planned: the new synthetic CI job runs for every PR and main push, without path
filters. G2's existing explorer import closure includes dynamically selected
workflow services; an unfiltered trigger ensures these dependencies cannot evade
the test through an incomplete static path list. No checker exception is added.

Named limits carried by the eventual output:

- rule statements authored with knowledge of prior test results
- single program whose full source fits in context; graph effect on large estates not measured
- operator review, not independent attestation

The redesigned run remains capped at USD 50.00 (maximum reviewed reservation
USD 49.423616) and 26,880 seconds. Patch A does not create run or spend authority.
Patch B is the standalone graph-disabled five-round controller; Patch C enables
queries. Each patch requires separate exact-tree review and Howard push approval.
