# Judge and environment qualification

This is development test equipment for the next factory version. It does not
modify MS92, replace its failures, count as an autonomous success, or establish a
factory success rate. There are no builder or analyst calls in these controls.

`qualification-status.json` is the signed inventory of all nine native equipment
attempts, including the two unsuccessful attempts. `isolated-qualification.json`
records the passing v3 reassessment of five real native controls. These reports
do not upgrade MS92 or assert that the next autonomous controller is ready.

## Reference review and native controls

The operations reference derives from the passing MS91 journey. Its only initial
changes lengthen the rollback and lock observation windows to 1.5 seconds.
The operator accepted its **scope conditional on passing native checks**. This is
recorded in `references/operations/scope-acceptance.json`; it is not a claim that
the operator performed a line-by-line source audit.

The positive reference must pass the complete combined judge on Oracle and
PostgreSQL. Four further fresh database pairs deliberately introduce wrong order
quantity, missing invoice accounting, an incorrect payment/invoice link, and a
committed row with the rolled-back draft identity. Both lanes must reject each
mutation for its specific intended reason. A crash, missing evidence, an
unrelated business failure, or incomplete cleanup does not qualify a mutant.
The rollback mutation models a leaked committed draft; it does not disable the
database engine's rollback implementation.

`operations-qualification.json`, when produced by
`python -m tools.report_judge_qualification`, is the signed aggregate result. The
report requires terminal receipts, signatures, gate hashes, source archives,
identical judge implementations across controls, and complete cleanup. Failed
attempts remain in their original directories. A reference result is always
marked `autonomous_success: false`.

The first fresh positive control exposed a missing Oracle counter sample in the
observer. It remains an execution failure. Observer v2 records such incomplete
transitions without treating them as rollback witnesses; valid independent
witnesses remain mandatory. It does not rewrite the old observer or MS92 results.

## Complete results and private answers

`qualified_judge.evaluate` writes `gate.json` for pass, business failure,
execution failure, judge error, or insufficient evidence. An exception cannot
become a pass. Private error details remain inspectable locally, but builders
receive only the closed structural diagnostic projection. Expected monetary
results, database observations, private reference source and judge files must
never be added to builder inputs or tool results.

Public contracts declare inputs, document shape, links, trace fields and
transaction boundaries. Operations currently requires **one aggregate
order-linked invoice line**. Two shipment-linked invoice lines are outside that
declared shape; accepting them requires a separate contract/judge version.

## Local builder tools

Install the repository's pinned `agent` optional dependency in the environment,
then start the dedicated stdio server from this workspace:

```powershell
$env:PYTHONPATH = 'src;.'
& work/native-venv/Scripts/python.exe -m tools.journey_builder_mcp --max-compilations 5
```

The server exposes public contracts, allowlisted API signatures from a pinned
iDempiere commit, deterministic Java support, structural checks, and bounded
offline compilation. Its compiler mounts only the candidate and public support
file, has no database network, and returns structural diagnostics rather than
raw Maven output. Compilation does not execute the journey or establish business
correctness. Compile invocations and results are retained, and failed tool
invocations consume their slot.

`JourneySupport` supplies plain decimal serialization, explicit trace insertion
and replacement, typed posting access, a skip-if-posted guard, and transaction
commit/rollback/close handling. The public posting API can still create internal
costing/reposting effects; the guard is not a blanket no-reposting guarantee.
The support reference passed a fresh composed native check on both engines in
`work/ms93/reference-support-isolated-02`, using judge v3. Separate component
checks and reference-source review remain prerequisites for campaign reliance.

The separate application runner mounts only the candidate, a public launcher and
an output directory. The private judge and its captures remain in the trusted
collector. The application stops before the host copies its declared trace/log
and writes the execution receipt. The local MCP compiler has neither database
access nor the private reference. Its persistent session budget survives server
restarts. The MCP server has been exercised over its actual stdio transport;
connecting it to a new model campaign remains a separate release gate.

The first isolated support-reference execution completed both databases but
retains `insufficient-evidence`: Oracle rolled back and immediately began its
retry between samples. Observer v2 required an intervening sample with no
transaction. Observer v3 also recognizes a changed transaction ID, provided the
same session/serial has exactly one rollback, applied undo and no intervening
commit, bound to the observed business-partner write. It still rejects ambiguous
transitions. `work/ms93/observer-v3-reassessment.json` is a separate reassessment
of the preserved capture, not a replacement receipt.

`tools.replay_qualification_controls` checks a fresh isolated support reference
and four preserved native negative-control captures with judge v3 in disposable
workspaces. It verifies original signatures, archived source, gate bindings and
cleanup, then checks that every original file is unchanged. This explicitly
distinguishes replaying real negative captures from executing fresh mutations.

## Purchasing investigation and release gates

The existing procurement reference candidate completed both engines and passed
the independent business readback, but failed the old complete footprint gate.
Application source and captured rows link
the extra cost queue, cost history and accounting history to internal costing
and matched-invoice reposting. `tools.qualification_procurement_scope` verifies
document/client/product relationships, unchanged existing rows, balanced
history and unique captured history identities. It grants **no admission**.

The proposed purchasing judge requires that scope check before admitting those
effects. It retains every raw row and the exact numeric comparison. A fresh
reference execution (`work/ms93/reference-procurement-01`) passed its complete
combined judge on both engines, with cleanup confirmed. It remains test
equipment awaiting human reference review; it is not an autonomous success.
The source investigation, eight historical scope checks and adversarial scope
tests are separate evidence from this fresh execution. The historical failures
remain unchanged. The proposed rule/register and purchasing review still need
to become explicit preconditions of a future frozen campaign.

## Feedback and remaining release gates

The v3 development exporter replays all 78 MS92 native attempts: 45 have
supported structural feedback. It covers checked exceptions, unresolved
imports, inaccessible methods, signatures, source-supported Boolean API
mismatches and missing trace fields after successful execution. A failed,
incomplete journey no longer produces a flood of downstream missing fields.
This is exporter coverage, not evidence that those attempts would repair or pass.
Old unqualified purchasing footprint claims are deliberately excluded.

Compiler, SDK, public MCP transport, engine observer and result-envelope tests
are development qualification. No builder call is made by these tests.

Before fresh generation: complete the reviewed purchasing and component gates,
connect the controlled MCP transport to a separately versioned controller,
finish the independently verified footprint and declared trace-type feedback,
pin the public tool/controller/judge versions, and declare the pilot budget and
stopping rules. Components need separate stage checks as well as their composed
journey checks. Preserve unfamiliar
evaluation scenarios. Prior MS92 source-transfer and call authorization does not
authorize a new campaign. Small pilot and ten fresh generations remain later
gates, not achievements of this qualification work.
