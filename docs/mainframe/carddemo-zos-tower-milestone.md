# CardDemo z/OS Control Tower integration milestone

Date: 2026-10-03 (America/Los_Angeles). Implementation:
`8a6ac6b0fa07c5674b2de5cd84a206f3e135763d`, based on main
`74cb372bf1b05035b423d8f4fd7a44e7d702043a`.
This prepares the review workflow for Maintec's October 5 delivery. It is not
native z/OS qualification or a new MS94 measurement. Operator review; not
independent attestation.

## Operator outcome

The `carddemo-zos` workspace connects intake acceptance, agent normalization
proposals, difference dispositions and evidence release to Control Tower v2.
Requests arrive through `work/control-tower/requests/carddemo-zos/` using
`tower-request/1`. A read-only arrival view shows commitments, counts and status.
The [workspace guide](carddemo-zos-tower.md) and [Monday runbook](monday-runbook.md)
describe setup and the operator sequence.

The mandatory no-values disclosure policy covers HTTP routes, SSE, MCP and
exports. Closed evidence schemas admit hashes, counts and fixed status fields;
record values, raw arrival paths, untrusted filenames and free-text notes are not
returned. Notes are committed by hash before signing. Reads and exports verify
the signed journal and policy, and refuse tampering.

Normalization requires an authenticated agent proposal and Howard's verified
decision. `verdict-intcalc` uses only verified Tower decisions or the signed rule
register, with scope, expiry, supersession and source bindings checked. It no
longer reads the old comparison ledger in parallel. Exact comparison retains
filler and trailing-space differences unless an explicitly supported, approved
rule applies. Dispositions do not change verdicts. Evidence release requires
distinct sponsor and Howard decisions and exports only closed evidence and proofs.

## Evidence and validation

170 distinct regression cases passed, including real Java comparison and offline
replay. Two existing cases remain skipped locally: optional MCP SDK registration
metadata and POSIX FIFO behavior on Windows. All seven MCP method implementations
were exercised over HTTP. Nine documentation checks, JavaScript syntax and
whitespace checks passed.

The disclosure regression plants a record-value canary in public EBCDIC data and
checks HTTP read routes, SSE, refusal responses, all seven MCP methods and a valid
released export. It also tests malicious metadata, filenames and notes. Additional
tests reject stale, expired, tampered, superseded and incorrectly scoped rules,
missing agent provenance, incomplete releases and journal tampering.

The browser rehearsal confirmed the read-only arrival view, fixed Howard owner,
and absence of page errors, external requests or submitted decisions. A fresh
public-data intake rehearsal covered three synthetic runs and 50 files with zero
intake findings. The unchanged Java candidate produced an equivalent exact
INTCALC verdict for the retained fixture, verified offline without another run.
A separate timestamp regression demonstrated exact divergence followed by
equivalence only with a verified Tower rule register.

The signed rehearsal content hash is
`012add20ebece693c25e1fc2d07235ce16da734af203d78599336031a7552252`;
the retained verdict hash is
`39b177c571ddf1fd128be25e0b34bffd2dc83cc7e9056ad380c1be02a0f31789`.
The [rehearsal record](carddemo-zos-tower-rehearsal.md) gives the complete scope,
limitations and evidence hashes. Repository PR checks record publication validation.

## Publication and remaining boundary

The public change contains implementation, tests, a workspace template and
documentation. Arrivals, decoded records, signed rehearsal payloads, screenshots,
local workspace configuration and keys remain ignored and local. No production
identity, grant or Howard decision was created by the rehearsal.

Actual Maintec execution evidence is still required to measure native equivalence.
The public fixture exceptions remain documented and do not normalize Maintec data.
POSTTRAN, CREASTMT and TRANREPT remain observation-only. B05, `work/ms94`, Docker
and model calls were outside this work and were not used or changed.
