---
name: legacy-modernization
description: Modernize CardDemo INTCALC to Java using Lightyear Verify MCP tools, public development records, bounded evaluation submissions, and human Control Tower decisions.
---

Use the operator-configured Lightyear Verify server for the assigned INTCALC task.
Call `get_task`, `get_budget` and `lane_status`; do not infer qualification from a
successful development example. Understand bound copybooks with `describe_copybook`
and decode public development files with `decode_records` before implementing code.
`read_job_log` is for bound public development logs only.

Build and test a runnable Java JAR locally against development inputs. Submit code
with `submit_candidate(path, request_id)` using a fresh UUID for each distinct
candidate. Retry an uncertain response with the SAME UUID and identical artifact;
a new UUID consumes another submission. Never submit handcrafted output records.

Submission returns an attempt ID with a pending verdict. Poll `get_verdict` no
more often than every two seconds; do not create another attempt while it is
pending. After completion, work from the permitted diagnostics and public tests.
Confidential mode exposes affected datasets only, with no fields, kinds or count
bands. Public fixture field mode can identify a field or execution failure.
Diagnostics deliberately omit values and record keys. Do not probe for hidden expected values,
attempt to read judge storage, or increase the operator's budget. Budget exhaustion
ends submissions; `indeterminate` is not success. Preserve the signed `get_receipt`
envelope unchanged and report the attempt number and submission limit.

Normalization and acceptance are human decisions in Control Tower. For an allowed
timestamp discrepancy, `propose_normalization` creates a draft only; it does not
change comparison rules. Do not approve the draft or describe it as applied. An
operator must review it and prepare any newly bound task using the established
normalization verification workflow. Never launch or reconfigure the judge service.

Attempt slots are reserved allowances, not measured build minutes. The cumulative
inventory cap carries across tasks. Do not request new tasks to reset it. An
interrupted or equipment-failure receipt requires the operator's receipt-bound
Tower continue/void decision before another fresh attempt; void still consumes
the slot and does not alter the original receipt. No decision tool is available
to the agent. Field-specific normalization proposals are unavailable when a
confidential diagnostic supplies no field identity.
