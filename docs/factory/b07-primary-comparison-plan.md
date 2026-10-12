# B07: October 11 decision and pre-freeze power

This current draft supersedes the previous 96-hour budget/calendar text and
unselected independence alternatives. Howard selected graph (G) versus search (S),
no drift arm, 24 analysis slots per journey and arm (72 analyzed per arm), two
excluded pilots per journey/arm, and two isolated runners for at most 14 calendar days.
Spending and execution are not approved.

G/S share the matched input and seed for each slot. Accordingly use the paired
stratified randomization/sign test, pooled over J1-J3; preserve the journey
strata and exact discordance tables. The primary claim is two-sided superiority,
with graph's effect required positive. Report G-S and its interval. Both arms
must appear on both runners, balanced within journey and time blocks. Historical
B06 contrasts remain secondary with time-drift limits; preserve their declared
multiplicity correction.

The secondary non-inferiority margin is 15 percentage points. The reproducible
simulation tools/b07_prefreeze_power.py uses seed 20261011 and 10,000 draws/scenario.
The [full result](b07-prefreeze-power-2026-10-11.json) explores discordance of 20/40/60%
and differences from -15 to +20 points, with explicit invalid probability cases omitted.
The primary exact conditional test is the binomial test over discordant pair signs.
For planning, a conservative one-sided 95% lower bound uses 97.5% one-sided
Clopper-Pearson bounds for p(G-only) and p(S-only), with a union-bound guarantee.
The descriptive two-sided 95% interval allocates the error across four tails.
This conservative interval is explicitly a planning proposal, not a frozen
replacement for previously requested marginal Newcombe reporting.

At equal true performance, the chance of establishing non-inferiority is 50.57%,
26.90%, and 21.44% across those discordance assumptions (Monte Carlo SE at most 0.50 points).
That is below the stated 80% planning benchmark. The 15-point margin therefore
cannot be called reliably assessable at this size under these assumptions and
method. Report this limitation to Howard before any freeze. Do not reduce the
sample, silently enlarge the margin, claim equivalence from a null result, or
present these simulations as observed trial outcomes.

Full budgets remain 156 trials including pilots, 780 model calls, 468 compilations,
and 311.5667 serial trial-hours. Two ideal runners need 155.78335 continuous hours;
12 hours/day uses about 13 days before overhead, leaving little of the 14-day window.
Both runner parity and an exact model/token/dollar budget require separate review.
No execution precedes B06 Part 6 and the Part 1.5 graph-coverage proof.
