# Graph-on CI acceptance and operator handoff

G1 extends the existing zero-model Linux acceptance. G2 on-demand factory tools
and G3 comparison planning are subsequent work in this lane. No model run,
production signing, Tower import or activation is authorized by this change.

## Automated CI

The Lightyear Verify workflow runs the original graph-off acceptance and the
graph-on variant against the same public CardDemo projection policy. Its
scripted agent exercises all 16 MCP tools, runs five native public-fixture
candidate submissions and five offline replays, and checks separate OS users.
The graph-on judge is bound to the exact projection and synthetic evaluation
inventory. Ephemeral fixture approvals exercise the existing admission path;
they are not Howard's production approval.

Every projection member is scanned, including every node, edge, source excerpt,
annotation/guidance record and extension. The L10 decoded-view scanner is used,
with bounded decoded matching for Verify's shorter protected fields. A planted
encoded protected value in a source excerpt must be refused. The scanner also
checks the response stream. No raw evaluation, detailed watch list, credentials,
private keys or response logs are exported.

The public output contains a dated inventory scan, acceptance report, synthetic
public approval proof and unsigned activation preparation. A zero guidance count
means that this public projection has no guidance records; negative fixtures
still exercise guidance leakage. The retention workflow on trusted main validates
the source run, attempt and all cross-file hashes before publishing immutable
Release assets. Before that workflow lands, PR artifacts are temporary evidence.
A Release receipt must actually exist before claiming permanent retention.

## Howard's activation boundary

1. Review the exact green revision and retained public reports. A CI fixture
   proves platform behavior, not an operator-approved deployment.
2. Follow the existing graph activation checklist on a fresh dedicated VM.
   Bind the actual public projection, operator evaluation inventory, independently
   trusted keys and current Tower journal. Preserve the old VM and spent budget.
3. Obtain the real projection approval through the existing
   `verify-graph-projection` Tower workflow. Never reuse the synthetic CI proof.
4. Supersede the unsigned preparation with the actual approval proof, inventory
   scan and VM acceptance hashes. The preparation is deliberately not importable;
   no new Tower request kind or approval bypass is introduced.
5. Howard reviews and activates. Observe live expiry and revocation separately.

The CI reports identify their exact source commit/run/attempt. Do not relabel old
CI evidence after any push, merge or projection change.
