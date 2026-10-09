# Verify graph stage 2: acceptance record and automated walkthrough

October 9, 2026. Operator review, not independent attestation.

## Delivered

The [supplied graph-off acceptance](graph-off-acceptance-2026-10-09.md) is preserved
byte-for-byte, including line endings, and linked from the activation checklist.
Its file SHA-256 is
`879de2e8d3ad243bbb53257967c49c0785863901d83f708c50301144e2d48942`.
It records Howard's arm64 platform acceptance, ten-tool baseline, manual walkthrough
and five-verdict replay at revision `25735d06beeefb97935903082ad046b4774e6bc3`.
The record does not claim an x86_64 pass or graph activation.

`tools/verify_smoke/walkthrough.py` automates the 15-step public-fixture protocol
through the same MCP stdio command and RAM-only token environment as Inspector.
It runs through `agent.py` as lyagent, generates UUIDv4 requests, checks intentional
idempotency, enforces a 360-second attempt deadline and polls at least two seconds
apart. It never resubmits on timeout and stops at the first mismatch.

The report records every reached step, request/attempt identities, artifact hashes,
verdicts and exact public receipt bytes with their byte hashes. Existing report
files refuse before connecting. Failed transport cleanup preserves the attempted
submission prefix without copying exception text or credentials into the report.

Fixture-only judge responses expose exact public receipt bytes, the repeated
diagnostic alert and an observed journal head. The client refuses older judges
before submission. Non-fixture receipt responses and the ten MCP tool schemas
are unchanged. A client report does not replace signature verification or replay;
the operator must pin the sealed journal head after shutdown.

The smoke runbook makes this script the default and retains Inspector as the
manual fallback. A fresh task with five unused cumulative attempts is mandatory;
neither a renamed task nor an erased ledger creates a valid fresh budget.

## Verification and limits

Twelve focused offline tests passed in 0.141 seconds. They cover a full fake-judge
pass, a mismatch at each of the 15 steps, timeout without resubmission, idempotency,
missing refusals/alerts/head, exact receipt bytes, existing output preservation,
credential-safe failure reporting, non-fixture compatibility and existing token
handoff/install/public-manifest behavior. No native candidate, Docker command,
model call, full test suite or build was run for this work. The initial restricted
host test encountered temporary-directory permission denial; the same focused
tests passed under the approved test execution context without machine changes.

The new automated walkthrough has not run in a Linux VM. Its first real run must
use a newly provisioned installation at the reviewed published revision, not an
in-place update of a sealed smoke configuration. The October 9 manual acceptance
remains separate evidence.

## Remaining stage 2 work

Verify Tower provisioning is pending. The proposed `lyverifytower` identity,
`verify-public-reference` scope, independent authority/data roots and loopback
port 8768 remain unprovisioned by this change. Account, ACL, service and other
machine changes wait for a gap after B06 stops and its evidence is sealed, with
Howard's elevation approval. No B06 authority or credentials may be reused.

The INTCALC projection and leak scan are also pending: they require that separate
authority, separately trusted operator/judge keys and the fresh Linux task's
actual inventory. No projection request or operator decision was manufactured.
Graph-on admission must subsequently show 16 tools, one public query, unchanged
budget and no submissions/models. Protected leak matches block release; exact
public-overlap acknowledgments remain Howard's decision.

Implementation and documentation use their own graph worktree and branch. B06
source, frozen inputs, services and evidence were not edited by this work.
