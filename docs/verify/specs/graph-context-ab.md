# Graph context A/B comparison — prospective draft

Operator review; not independent attestation. Zero model calls in preparation.
This draft is not authority for a live test. Howard must approve the exact
commit, projection/proof, client/model versions and cost ceiling before either
arm starts. Schedule after the B06 launch; B06 has priority.

## Fixed design for review

First agent: Claude Code. Run ADK as a separate experiment only after its live
client acceptance passes. Do not pool agents or lanes. For the currently
available public INTCALC lane, use 20 paired replicates (40 fresh sessions per
agent), each implementing the same bound task. This measures repeated
task/session behavior on one program, not generalization across 20 programs.
Any additional lane requires a new preregistration before its calls.

Each pair has graph off (the original ten-tool interface) and graph on (the
six graph tools (including graph_guidance) plus paged decode). This compares the bundled context
intervention, not graph access separately from decode paging. All other
prompts, public development inputs, judge inventory, normalization policy,
attempt limits, model/client parameters and resources are identical. Freeze
a seed and counterbalanced randomized arm order before the first invocation.
Each session gets a clean workspace/context; no artifact, transcript or learned
repair is shared between arms.

Maximum five submissions per session. Independent approved PUBLIC fixture
inventories and explicitly preregistered cumulative ledger policies are needed
to accommodate 40 sessions: the existing inventory-keyed five-attempt budget
must not be bypassed by changing task IDs. The operator must prospectively
approve any necessary cumulative budget increase through Tower. No private
customer inventory or Maintec data is permitted.

## Outcomes, costs and stopping

Report all 20 pairs, including failures. Primary: proportion passing within
five attempts, separately per arm with Wilson 95% intervals, and paired
discordant counts. Report attempts to first pass (right-censor at five),
model tokens (cached separate), actual provider cost, wall time to verdict,
and total cost divided by verified programs; undefined if none pass. Also
report total model and tool calls, decode response bytes, graph response bytes,
and transport/equipment failures. Agent query logs are untrusted telemetry,
not proof of correctness or model consumption.

### Prespecified paired efficiency analysis (before any calls)

The success primary above is unchanged. **Key secondary outcomes** are provider
cost and model tokens per verified program, paired by replicate. Freeze this
analysis with the experiment commit, before any invocation, to handle a ceiling
in the pass-within-five-attempts outcome without selecting a new primary later.
For each arm use total session cost / number of verified programs, and total
input + output model tokens / number of verified programs. Include costs and
tokens of failed sessions in the numerator; zero verified programs means
undefined, never zero. Cached input tokens are included once in total input,
reported separately, and charged at the frozen provider's cached rate.

Report graph-on minus graph-off differences and ratios of these aggregate
quantities. Quantify uncertainty with 10,000 paired bootstrap resamples of the
20 replicate IDs, resampling each pair together, using fixed seed 259261.
Use percentile 95% intervals; disclose how many resamples had zero successes in
an arm and hence undefined ratios. If any are undefined, report the finite
interval as conditional, never as an unconditional confidence interval.
Also report each pair's raw cost/token differences and an exact paired sign-flip
randomization test of the mean raw difference (all 2^20 assignments). Report
both secondary p-values and Holm-adjusted values for this two-outcome family.
These are secondary efficiency results, not a second way to declare primary
success. A both-arms-pass-only paired summary may be descriptive, labelled as
selected on outcome; it must not replace the full-population analysis.
Missing provider cost or token counts stay missing, with completeness counts;
no zero imputation and no definitive efficiency claim from incomplete accounting.

Freeze a 30-minute wall cap per session and 24-hour cap per agent experiment.
Stop on budget exhaustion, a leakage match, a projection/receipt mismatch,
unapproved context, missing evidence or isolation failure. Preserve the result;
no replacement sessions, opportunistic sample extension, optional stopping on
good results or exclusion of expensive failures. An interrupted/incomplete
experiment is labelled incomplete, not a completed comparison.

## Privacy and interpretation

Verify approved projection bytes are independent of evaluation values and
query results contain only those bytes plus the already visible verdict.
Confidential projection redaction covers all literals, not a watch-dependent
subset. The judge records the approved context hash but never consumes query
logs or graph answers as comparison evidence. Check the same disclosure
policy and cumulative attempt ledger in both arms.

The existing approximate 2,046-bit field-mode and under-26-bit confidential-mode
five-attempt bounds concern judge-mediated disclosure. Read-only deterministic
post-processing of already approved source and already disclosed verdicts
adds no new private observation channel. This argument is conditional on the
projection's provenance, source allowlist and leak gate; it is not a claim that
a keyword scan proves arbitrary graphs safe. Approval/leak reports remain
operator-side; the agent receives only a signed eligibility certificate with
the opaque report hash and acknowledged public-source literal exceptions.

No causal claim about graph tools alone, no independent attestation, and no
comparison with B05/B06 measurement rates.
