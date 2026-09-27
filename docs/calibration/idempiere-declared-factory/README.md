# MS91 — declared dark factory operations run

**Result: verified on the first generated candidate.** The campaign declared and
froze the judge, comparison register, controller, model request and budget before
generation. The same agent-generated Java journey then executed natively on
Oracle and PostgreSQL, and the combined deterministic judge passed. The full
capture archive subsequently reproduced that verdict offline.

| Measure | Observed result |
|---|---:|
| Builder calls | 1 of 11 total calls approved |
| Analyst calls / repairs | 0 / 0 |
| Human-authored candidate or repair-message bytes | 0 |
| Controller changes / recorded interventions | 0 / 0 |
| Native paired attempts / failures | 1 / 0 |
| Input tokens / output tokens | 17,321 / 11,441 |
| Generation time | 349.641 seconds |
| Native execution and gate time | 387.656 seconds |
| Total campaign time | 745.157 seconds (12 minutes 25 seconds) |
| Unresolved row / trace differences | 0 / 0 |
| Numeric columns governed by the typed rule | 9,393 |
| Numeric cell observations validated | 2,746,888 |
| Retained, rule-admitted raw row / trace differences | 6,038 / 15 |
| Full publication | 7,509 files; 61,948,306 archive bytes |

The observation count is not a test-case count. Most observed database data is
inherited seed data; the journey is one bounded business scenario.

## What ran

A newly generated customer/product/order journey used fractional prices, tax,
discount, Unicode text, an empty optional field and fractional shipment time. It
completed two partial shipments and one aggregate invoice/payment, created a
credit note and reversed it, exercised two overlapping explicit-row-lock updates,
and injected a pre-commit failure followed by rollback and caller-keyed retry.

Native final rows, relationships, quantities, monetary results, accounting,
write footprint and cross-engine differences were independently checked against
the frozen judge. The generated harness used the application model and workflow
APIs. Intermediate lock-wait and rollback assertions remain application-trace
evidence; this is not an independent transient monitor, crash/restart recovery,
load test, full application equivalence or platform qualification.

The passing receipt sets `dark_factory_run: true` for this declared, bounded run.
It meets the requested zero-repair-byte and zero-controller-change conditions.
Because the first candidate passed, **this run did not exercise analyst-led
repair** and does not establish a general autonomous repair success rate.
Specification, judge and controller preparation before the declaration are outside
the repair-byte metric. The original MS89/MS90 results remain intact.

## Pinned policy and model

- Judge: `idempiere-declared-comparison-v3`.
- Numeric eligibility comes from native column types and captured-cell provenance,
  not a list of field names. Decimal equality has no tolerance; exponent notation
  is refused. Numeric-looking text gets no numeric exception.
- Every accepted rule has an owner, review date and measured scope in the single
  comparison register, which retains raw difference witnesses.
- Timestamp scope: only `adempiere.m_inout.shipdate`, Oracle DATE, verified UTC
  capture sessions, second-level equality without rounding. Owner Howard Weale;
  review 2026-12-25. Lost fractions remain visible in raw captures.
- Requested model: `gpt-6-astra`, reasoning `high`, through the signed-in Codex CLI.
  CLI version `0.155.0-alpha.9.2` and executable SHA-256 were frozen. The provider's
  resolved model snapshot is not exposed and remains unknown.
- Organization API migration was deferred. No GCP resources were started. Per-call
  billed dollars and local electricity costs are unknown, not zero.

## Inspect and replay

`campaign.json` is the signed campaign result. `plan.json`, `declaration.json` and
`authorization.json` preserve the pre-generation declaration and exact-plan
approval. `LightyearOperationsTest.java` is the exact generated and executed
candidate. `receipt.json` signs the publication manifest/archive identity.
`evidence.zip` contains all source captures, raw rows, catalogs, journal, prompts,
model responses, accounting, gates and the frozen implementation.

From the repository root with dependencies installed and `src` plus the repository
root on PYTHONPATH:

```powershell
python -m tools.publish_frozen_campaign verify --output docs/calibration/idempiere-declared-factory --trusted-key-sha256 c2fbae3453e8bcae03e0830a9eb83f310f027ad51929deee967ecee1a41f399f
```

Expected result: `verified-complete-frozen-campaign`, judge v3, one replayed passing
gate, `dark_factory_run: true`, zero new model calls and zero native executions.
The verifier runs the installed, hash-matched implementation; it does not execute
arbitrary source taken from an archive. Establish trust in the operator key
separately. Operator signatures and offline replay are not independent attestation.

## Identities

| Artifact | SHA-256 |
|---|---|
| Frozen plan | `cc547e958c97bd6b500fb57c5bfce9fa21824453fbf55178465ab628a0df8a3d` |
| Comparison register | `2d1ba26d412cad3d633a1613df909b04978b14fa70e8db31a5204ff741ef28e7` |
| Campaign receipt | `e121c5c9fa3d789054651f8f37ea7b64c3e927a4697a18e39d2ce367f9ec35fe` |
| Native gate | `6c8ccd36378af194c44fd8c552c0ec71f86d6fb47e1b4120091c9759660ec7e0` |
| Executed candidate | `b53e4959d806fa8a2362906213d8e7063b99cf3027f6c5fb1476fac11c5d5599` |
| Capture archive | `6817c8205eb3621cf604f6ff56669647a214c31e9bea307ffda29c596042c948` |

Native run: `journey-d8a88a4c337845d4bcaf42ef976ff028`.
All campaign-owned containers, networks and volumes were absent on an independent
post-run Docker inventory check; the signed cleanup record confirms credential
destruction. No remaining calls are used after a terminal successful campaign.

Validation: 21 new adversarial/lifecycle tests and 72 existing journey tests
passed before generation. The new native run and full offline capture replay
passed afterward. Full MS90 capture replay also reproduced both historical verdicts.
