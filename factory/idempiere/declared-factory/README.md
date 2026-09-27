# MS91: declare the judge, then run

Status: campaign-01 verified on 2026-09-27. The first generated candidate passed the frozen native judge on Oracle and PostgreSQL. See [published evidence](../../../docs/calibration/idempiere-declared-factory/README.md).
Organization-controlled API migration is deferred at the user's request.

The prepared scenario covers fractional order-to-cash, two partial shipments,
one aggregate invoice, a credit note and its reversal, two controlled concurrent
row-lock updates, and a pre-commit injected failure followed by a caller-keyed retry.
This is bounded application testing. It does not qualify load, crash/restart
recovery, a whole application, a schema, or a database platform.

## Rules and evidence

`comparison-register.json` contains 15 column rules, one engine-identity metadata
rule and 6,024 retained historical witnesses. Every rule has an owner, review date
and measured scope. The numeric selector contains all 9,393 NUMBER-to-numeric
columns from the native datatype inventory. A field name alone never permits a
numeric exception. Observed cell provenance and native column types are required;
aggregate stock is bound to the captured numeric stock rows.

Decimal equality is exact, without tolerance. Exponents, nonfinite values,
floating-point inputs and numeric-looking text columns do not qualify. Even equal
invalid numeric spellings fail. Nulls remain nulls. UUIDs, audit clocks, workflow
text and engine metadata retain their separate, bounded, re-executed predicates.
A numeric audit clock may differ only under its owned clock rule, never under
numeric equality.

The accepted timestamp scope remains only `adempiere.m_inout.shipdate`, Oracle
DATE versus PostgreSQL timestamp without time zone, in verified UTC capture
sessions. Raw fractions remain in evidence. Owner: Howard Weale. Review:
2026-12-25. Other columns and subsecond business requirements remain outside scope.

Committed business outcomes have independent full-database readback. Intermediate
lock waits, partial-stage values and rollback observations still include
application trace assertions; there is no independent lock-wait monitor. Unbound
trace values compare as exact strings. The public work order requires plain,
consistent decimal trace serialization before generation. It does not reveal
expected business outputs.

## Frozen campaign

Prepare a new directory with `python -m lightyear_calibration.declared_campaign
prepare --campaign work/ms91/campaign-01 --executable <pinned-codex-executable>`.
Preparation performs local image/resource checks and grants no execution authority.
Review `plan.json`, the builder input and the source hashes. The proposed limit is
11 total client calls: at most six builders and five analysts, with a four-hour
campaign limit and a 15-minute per-client limit. Local Docker only; no GCP starts.
The work order also caps one generated Java file at 60,000 bytes and 650 lines.

After explicit approval of that exact plan and source transfer, use the
`authorize` command with `--plan-sha256` and `--approval`, then `run` with the same
campaign and executable. No resume or amendment command exists. A budget increase,
judge change, controller change or input change requires a new campaign directory
and declaration. Every attempt publishes its judge hashes and rule version.

The CLI binary hash/version, requested model `gpt-6-astra` and reasoning `high`
are pinned. The CLI does not expose an independently attested provider model
snapshot or per-call dollar invoice; those values stay unknown. Calls, token
usage where reported, elapsed time, failures and incomplete accounting are retained.
No API key is requested or used for this campaign.

Only compiler errors, source-supported API type mismatches and a verified
out-of-footprint table/call may reach the analyst. The analyst selects closed
structural records; no expected business output or free-form repair instruction
can reach the builder. Initial specification work is excluded from repair-byte
measurement. Candidate and repair-message identity are verified afterward.

`halted-no-supported-repair` means the permitted diagnostic channel is empty,
not that the defect cannot be repaired. Analyst rejection and a frozen budget
stop have distinct statuses. A completed combined gate, verified zero repair
bytes, zero recorded controller interventions and complete call accounting are
all required for the bounded `dark_factory_run` flag. Campaign-01 met those conditions on its first candidate. No analyst or repair call was needed; this run does not exercise the repair loop.

## Complete capture publication

After a terminal campaign, use `python -m tools.publish_frozen_campaign publish
--campaign work/ms91/campaign-01 --output docs/calibration/idempiere-declared-factory`.
The archive preserves every attempt's raw captures, candidate, prompts, model
responses, call accounting, rules, native receipts and frozen implementation.
A failed execution is recorded as incomplete rather than acquiring a fabricated
passing native gate. Operator signing does not mean independent attestation.

Offline verification uses `python -m tools.publish_frozen_campaign verify
--output docs/calibration/idempiere-declared-factory --trusted-key-sha256 <trusted-key>`.
It verifies signatures and blob hashes, reconstructs captures, checks source and
repair provenance, and reruns every complete native gate without databases or
model calls. Use the frozen implementation; do not execute arbitrary archive code.
The trusted operator-key fingerprint must come from a separate trusted source.

The older MS90 full captures are already packaged at
`docs/calibration/idempiere-judge-v2-captures`. They contain 7,379 files in a
60,012,367-byte archive. Verification reproduced the original failing native gate
and the passing v2 comparison with zero new database executions. The original
MS89/MS90 receipts and implementations are unchanged.

## Validation so far

- 21 new adversarial and lifecycle tests pass; 72 existing journey tests pass.
- Complete MS90 capture replay succeeds, including both historical verdicts.
- A separate retained MS87 operations preflight validates 2,747,060 numeric cells
  and admits 6,049 raw row differences with no unresolved row differences.
- That preflight still fails on four unbound intermediate trace formatting
  differences. It is not a fresh campaign result, and its raw observations were
  not changed. The new trace format is declared in the initial work order.

Run new tests with `python -m unittest discover -s tests -p test_declared_factory.py`.
Set `PYTHONPATH` to `src` and the repository root, or install the project editable.

## Campaign-01 result

The authorized 11-call campaign consumed one builder call and zero analyst calls.
Its combined gate passed with zero unresolved row or trace differences, zero
human-authored repair bytes and zero controller changes. Generation used 17,321
input tokens and 11,441 output tokens. Total campaign time was 745.157 seconds
(12 minutes 25 seconds); there were no failed calls or native attempts.
No GCP resources were started. Dollar billing remains unknown under the signed-in
transport. The frozen plan and original result have not been amended.
