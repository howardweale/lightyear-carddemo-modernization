# Control Tower Decision Console milestone

Date: 2026-10-02. Scope: the Decision Console specification against main
`819ef1e76e2e60d24ce0d207931a7ee977476c6a`. This is an implementation milestone,
not a new MS94 measurement or a declaration of MS95 readiness.

## Customer value

Operators can inspect campaign evidence, review differences and record decisions
against exact evidence hashes in one local console. The service countersigns
authenticated intent and preserves the decision history. Engines retain ownership
of execution and verdicts. A Console decision alone does not execute anything.

Customer workspaces provide scoped estate, slice, verdict and difference views.
Evidence release requires a customer sponsor and a separate campaign authorizer
to approve the same archive bytes. Partners see only the customer's current share
level. Auditors can inspect and verify but cannot write domain decisions.

## Delivered review units

| Unit | Delivered behavior | Local implementation tip before publication |
|---|---|---|
| Foundation | Typed decision kinds, scoped roles and identity, exact evidence binding, same-session review, idempotent decisions, verification and seven agent read/proposal MCP tools | `488956315f5cb06c87ad240d557caeb16afbfc2c` |
| Campaign cockpit | Read-only adapters, closed alerts, B04 archive regression, local browser interface and admission boundary for future controllers | `0e4ffef0bf2d5527ff4cc4b4d7e70e2527f0ae20` |
| Rule and qualification queue | Independent rule review, still-caught checks, approved-only register and fail-closed qualification acceptance | `1122932304d169db8bb544f21adad178729e13ae` |
| Catalogue | Signed accepted records, binding-change expiry and consistency checks against public and website projections | `71cd79f3eb931b16122b377a5195cbe1f1ac390b` |
| Customer workspaces | Scope isolation, slice/reference/share decisions, dual evidence release and offline archive verification | `0c62acf0c1b5cca4443617426d61a1fa471d8cb5` |

The branches are delivered in dependency order. Missing later modules remain
unavailable and cannot approve guarded requests. Existing normalization decisions
and session exports remain compatible with the original verifier.

## Validation evidence

- The complete new suite passed **27 tests**. It covers role refusals, stale
  evidence, view-before-decide, idempotency, classification decisions per item,
  independent-review requirements, rule validators, catalogue drift, dual release,
  partner sharing, workspace canaries and future-controller admission.
- The unchanged decision, graph-explorer and live-Tower suites passed **39 tests**.
- Each exact review branch was tested in a separate extracted tree: foundation
  12 tests; cockpit 21; workflows 25 with two later-feature skips; catalogue 25
  with one workspace skip; final workspaces 27 with no skips.
- The browser flow passed sign-in, campaign alerts, evidence review and decision
  recording. It observed zero external browser requests and no persisted session
  credentials. Screenshots were visually inspected.
- The B04 regression uses 14 selected original signed archive files and a public
  verification key. Their committed bytes match the provenance manifest. It
  raises the gate-decline alert at cohort 2 and the repeated `accounting_cache`
  cause at cohort 3. B04 remains VOID; the interrupted fourth cohort slot is not
  counted as completed. Missing total costs are unavailable, not zero.
- The observer test appends a partial journal record while the observer reads;
  source bytes and modification times remain unchanged by observation.
- No model calls, native campaign pairs or cloud API calls were needed. No frozen
  MS94 source, campaign process, historical signature or verdict was changed.

These are implementation tests with disposable local authorities. They are not
new equipment qualifications, autonomous cohort successes or independent human
attestation. Repository CI results are tracked on the delivery pull requests.

CI exposed two integration issues before merge. The broad suite does not install
the optional MCP SDK, so its runtime tool-surface test now skips only when the SDK
is absent; dedicated Console CI installs and exercises it. Observer policy now
lives in `control-tower/decision-console-policy.json`, preserving the legacy
`control-tower/policy.json` bytes. The actual legacy audit rebuild and comparator
again produce `d4e89afa898c723625aca87b12f3eeeddbdd5779efc9834ae45147ea3a9cbd68`.
No historical audit snapshot was regenerated or replaced.

Delivery PRs: [foundation #226](https://github.com/howardweale/lightyear-carddemo-modernization/pull/226),
[cockpit #227](https://github.com/howardweale/lightyear-carddemo-modernization/pull/227),
[workflows #228](https://github.com/howardweale/lightyear-carddemo-modernization/pull/228),
[catalogue #229](https://github.com/howardweale/lightyear-carddemo-modernization/pull/229),
and [workspaces #230](https://github.com/howardweale/lightyear-carddemo-modernization/pull/230).

## Boundaries and remaining dependencies

Production LAS native replay is not present at the baseline. Qualification
acceptance therefore supports explicitly labelled signed fixtures and refuses
non-fixture production qualifications until the trusted native replay adapter is
implemented. Catalogue tests do not establish a production lane qualification or
publish a production website claim.

Historical projections can verify only evidence actually supplied to their local
registry. Missing snapshot files or terminal evidence are reported as unavailable
or incomplete; the console never fabricates a successful integrity check. The
selected B04 fixture is deliberately not a complete private execution archive.

Offline archive verification establishes signature, scope, member hashes,
journal chain and both release decisions at the archived head. It does not
re-execute native databases or prove that no newer decision exists. Future engine
consumers must obtain a fresh trusted journal head before every slot.

The future-controller boundary is available for a newly frozen engine integration.
No existing frozen controller has been migrated to it. The Console cannot start,
stop, resume, cancel or schedule a campaign. Classification reviews by another
operator remain labelled operator review, not independent attestation.

SSO implementation, hosted multi-tenancy, WORM retention, production LAS replay
and remote customer deployment remain outside this delivery. Signing keys,
private captures, checkpoints, reference sources and private archives are not
part of the public regression fixture.

## Operating documentation

- [Decision Console setup and boundaries](control-tower-decision-console.md)
- [Scoped kernel and request/verification contract](control-tower-decision-kernel.md)
- [Exact B04 regression provenance](../tests/fixtures/decision-console/b04/provenance.json)
