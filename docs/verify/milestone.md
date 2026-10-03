# Lightyear Verify MCP milestone

Date: 2026-10-03 (America/Los_Angeles). Based on main
`d4a97d04ee84f63b556ec905297863d2ba60585b`.
This is a software implementation milestone using public synthetic fixtures,
not a native Maintec qualification or an autonomous effectiveness measurement.
Operator review; not independent attestation.

## Delivered behavior

An agent can inspect approved public development material and submit a runnable
Java JAR through the stdio MCP toolkit. A separately launched, operator-owned
Linux judge executes the JAR against private evaluation inputs under a different
OS user and returns closed INTCALC diagnostics and signed receipts. The existing
intake comparator and offline replay determine the verdict; candidates cannot
submit their own outputs or access the judge's signing authority.

The toolkit provides copybook description, public record decoding, public job-log
reading and lane status, plus task, submission, verdict, budget and receipt tools.
A normalization proposal creates a human review draft only. This version does not
apply normalization through the judge service or let an agent decide a proposal.

Submissions use UUID idempotency and durable budget reservation before execution.
The default budget is five submissions and 25 reserved execution minutes, with
five minutes per submission and no refund. A chained signed journal records
queries and refusals; restarting the service preserves consumption. An incomplete
accepted attempt consumes its reservation and blocks new submissions rather than
silently rerunning. Task, input and implementation bindings are checked on replay.

Bubblewrap provides fresh namespaces, no network, a read-only runtime and inputs,
and exactly three writable output files. The judge refuses shared UIDs, root
execution, agent-writable installations and unsafe private-directory permissions.
Candidate process groups and descendants are terminated at the execution boundary.
The [setup guide](README.md) documents the installation, four harness examples,
limits and the included legacy-modernization skill.

Control Tower consumes signed immutable exports for attempts, budgets, verdicts
and repeated-diagnostic alerts. Human normalization requests enter the Console's
authenticated review queue. The reader projects the same verified immutable
record it inspected, retaining the generic export signature and chain checks.

## Validation

Local acceptance completed 107 passing tests and two platform-specific skips:
60 Windows intake/Tower/toolkit tests, 42 additional Console regressions and five
Linux acceptance tests. The latter run the real MCP SDK, separate OS users,
Java candidates and Linux sandbox. The Windows suite includes the concurrent
immutable export writer/reader. Skill validation, JavaScript syntax and whitespace
checks passed. The [acceptance record](acceptance.md) gives the full scope.

The retained Java candidate is equivalent on the retained public INTCALC fixture.
Erroneous interest rounding, an omitted account and changed timestamp dates
produce divergence; repeating the date fault produces an alert. All five submitted
receipts replay offline, submission six is refused, and a restarted service
retains the exhausted budget. A separate fixture remains an intentional divergent
timestamp control. Modified receipts and journal records fail verification.

The leak scan covers every evaluation field value of at least four non-padding
characters, excluding only documented exact overlaps with bound public fixtures
as approved by Howard. The evaluation-only canary remains protected. Captured MCP
responses, receipts, Tower views, requests and exports contain zero protected-value
matches. The agent UID cannot read private judge files. A hostile Java candidate
cannot read the host signing key, reach the judge port or leave its delayed child
running after teardown. These are exercised controls, not a general noninterference
proof. The README states the response-alphabet leakage bound.

The dedicated Linux PR workflow repeats the real isolation and SDK acceptance.
Repository checks record remote validation separately from these local results.

## Publication and limits

Publication contains implementation, tests, CI, documentation and the skill only.
Private archives, evaluation captures, checkpoints, runtime logs and keys remain
local. No model calls, Docker operations or Maintec data were used. B05 evidence,
`work/ms94` state and B06 preparation were not changed.

The judge requires a protected Linux installation with working user namespaces;
the toolkit is cross-platform. Isolation is an OS boundary, not a disposable VM
or protection against kernel exploits and side channels. Source compilation,
hosted multi-tenancy and a licence choice are outside this delivery. Operators
must pin a trusted journal head to detect deletion of a valid suffix. No live
model-harness smoke test was performed, and no Maintec equivalence is claimed.
