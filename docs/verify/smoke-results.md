# Lightyear Verify manual smoke-test results

Date: 2026-10-04.
Platform: Apple Silicon Mac; Multipass Ubuntu 24.04 arm64.
**Operator review; not independent attestation.**

These results record Howard's report of the public-fixture walkthrough and live
client test. They were not rerun to prepare this document. Receipt hashes, client
transcripts, exact client versions (except the noted Codex npm version), platform
report hashes and an independent offline replay result were not supplied with
this report. Four Claude Code receipts are reported retained; this document does
not claim to have inspected or independently verified them. x86_64 remains untested
in this record. See the [runbook](smoke-runbook.md) and [milestone](smoke-milestone.md).

## Inspector

VM: `lyverify-inspector`. **Passed:** all 15 walkthrough steps.
Zero model calls.

## Claude Code

VM: `lyverify-claude`. The primary model was `claude-opus-5-5`, with small
`claude-haiku-4-5` use also reported. The following four outcomes were observed:

| Artifact | Verdict | Reported diagnostics |
| --- | --- | --- |
| `good.jar` | equivalent | None reported |
| `rounding.jar` | divergent | `TRAN-AMT`, `ACCT-CURR-BAL` |
| `skipped.jar` | divergent | `ACCTFILE` `count-differs`, `missing-record` |
| `date.jar` | divergent | `TRAN-PROC-TS`, `TRAN-ORIG-TS` |

Four receipts retained; one attempt left. The run used **18 Verify tool calls**
and **9 minutes wall time**. Reported cost: **$0.76 at API rates**; this is the
operator's API-rate cost figure, not an independently reconciled invoice.
No detailed token breakdown or separate auxiliary-model cost was supplied.

These results demonstrate the reported public-fixture client workflow with
prebuilt artifacts. They do not establish autonomous implementation effectiveness,
Maintec equivalence, independent attestation, or completion of every optional
platform/acceptance check in the runbook. Auxiliary Haiku use is recorded rather
than claiming a strictly single-model run.

## Codex

**Status: planned. NOT completed.**

The build installed using the runbook's former `chatgpt.com` install script was
rejected at sign-in with `invalid_client`. After switching to the official npm
package, `@openai/codex` **0.160.0** device login was not completed. There is no
completed Codex Verify result, receipt set, tool-call count or cost to report.
This does not establish that npm installation or the revised login procedure has
passed the smoke test.

The [runbook's Codex section](smoke-runbook.md#codex-installation-and-vm-sign-in)
now uses `@openai/codex` and documents browser sign-in through a forwarded
localhost callback. A future live test still requires the runbook's approval.

## Product finding: decoded results dominate context

The operator reports that `decode_records` results consumed most of the agent's
context: **54% of Claude Code usage** was attributed to those results. This is
the reported usage attribution, not a separately measured token count here.

Proposed follow-up (not implemented by this documentation change):

- Default large public-development decoding responses to a bounded summary:
  schema, total record count, decoding errors and an explicitly limited preview.
- Offer deterministic paging with a bounded page size, total/returned counts and
  a cursor bound to the file and decoding options. Clearly indicate remaining
  records; do not silently truncate or imply that a preview is the full dataset.
- Let the client request only needed fields/pages while preserving existing
  disclosure restrictions. Summaries and pages must not expose private evaluation
  records or weaken confidential-mode diagnostics.
- Validate paging completeness and compare response size, agent context usage,
  tool calls and the four known artifact verdicts against this baseline before
  claiming a context or cost improvement. Any repeat model test needs approval.
