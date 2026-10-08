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

## Kiro CLI

**Status: passed (operator review; not independent attestation).**

Date: 2026-10-08. VM: `lyverify-kiro`, Multipass Ubuntu 24.04 on an Apple Silicon
Mac, provisioned from public `main` with the unchanged kit. One extra package,
`unzip`, was installed by the VM administrator because the Kiro installer requires
it; Java, bubblewrap, Python and the judge were not changed.

Client: **Kiro CLI 2.28.0**, run as lyagent from the `agent.py` shell, signed in
with a new dedicated identity on a Kiro Pro plan. Verify was connected through
`~/.kiro/settings/mcp.json` (stdio, no `autoApprove`, no `env` block); Kiro listed
all **10** Verify tools. Model: **`claude-sonnet-4.5`**, selected explicitly (not
Auto). Howard approved Kiro, a $20 Kiro Pro month as the spending cap and the
exact runbook prompt; the approved model was amended from Claude Sonnet 5.5,
which Kiro did not offer, to `claude-sonnet-4.5`. The exact single task prompt
was used unchanged.

| Artifact | Verdict | Diagnostics reported by the client |
| --- | --- | --- |
| `good.jar` | equivalent | None |
| `rounding.jar` | divergent | `ACCT-CURR-BAL`, `TRAN-AMT` value-differs |
| `skipped.jar` | divergent | `ACCTFILE` `count-differs`, `missing-record` |
| `date.jar` | divergent | `TRAN-ORIG-TS`, `TRAN-PROC-TS` value-differs |

Verdicts and diagnostics match the Inspector table and the Claude Code run.
Four attempts were consumed and one remains. Kiro reported **18 Verify tool
calls** (6 reads, 4 submits, 4 verdict reads, 4 receipt reads). The operator
reports that Kiro requested no non-Verify tool (no shell, file write, web or
`propose_normalization` call) during the run.

**Offline replay (operator, after `stop.sh`): `verified`**, 4 attempts, 4 native
verdicts replayed, 0 model calls, exit code 0. Terminal journal head:
`d0bee4d0b02b934c424aff22d9c6009032c63b8353ce6966b0d72f24e14a877c`. The head
was read from the session journal immediately before replay rather than pinned
by an independent observer during the run.

Receipt identities as reported by the client (not separately inspected here):

| Artifact | Attempt ID | Receipt SHA-256 |
| --- | --- | --- |
| `good.jar` | `attempt-66ee2b2e001d4e8799be8bccf7471810` | `e4b13c1a68f75c3f6a27f2ed2afec423ebafdc8a7e5390cd928e59af0db6f088` |
| `rounding.jar` | `attempt-83182446600f464e9e4e952d44740ed6` | `dd819afca048e9f753bae3b69b2760291965ea173ac7c57b5e9688c1400eb7cb` |
| `skipped.jar` | `attempt-f9bfc1f83fce4112b09e001d7bf54f67` | `abf1914299b946a5397efe0d03ca395049b8c7eb1287b9b3ce3183709ab6bddc` |
| `date.jar` | `attempt-6757aa51909c4ee09dc6db0caacf0ae9` | `023bae3a626704dbe004f44210be1f7fa0067c717cd6be435932d74122d9b084` |

Receipts were signed with Ed25519, key ID
`c5073e99efc5b23907b859ab70cf2e9b17a77df12cace6f24b65a6eced5800c1`, schema
`lightyear-verify-receipt/2`, as reported by the client.

Usage: **6.73 Kiro credits** (Kiro's usage display, Pro plan). Kiro does not bill
per run; at the plan rate ($20 per 1,000 credits) this is a **calculated** $0.13,
or $0.27 at the add-on rate of $0.04 per credit. Not an invoice. Wall time was not
measured precisely; the run completed within about six minutes.

Observations (none failed the checklist):

- **Model-generated idempotency keys.** The four request UUIDs were unique, but
  were composed by the model rather than generated randomly; three of the four are
  not valid RFC 4122 variant UUIDs. Verify accepted them. Consider validating
  request IDs as UUIDv4 in a later change.
- **Read order.** The six public reads were reported in a different order from the
  prompt. Harmless, but recorded.
- **Receipt saving.** Kiro reported receipt identities and hashes; it did not
  write receipt files (no write tool was used). The judge's journal and the
  offline replay are the retained evidence.

These results demonstrate the public-fixture client workflow with prebuilt
artifacts inside Kiro. They do not establish autonomous implementation
effectiveness, Maintec equivalence or independent attestation.

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
