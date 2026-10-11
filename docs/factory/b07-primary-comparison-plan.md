# B07 comparison and two-runner planning amendment

Howard selected graph-versus-search as the primary contemporaneous comparison
and two isolated runners for planning, subject to later approval. This document
does not change frozen B06 plans or authorise model/native calls.

Primary proposal: one pre-specified two-sided graph-vs-search test pooled across
journeys, stratified by journey (Cochran-Mantel-Haenszel only if independent slot
assignment is adopted). If slots are paired/shared, use a paired stratified
randomisation test instead; the independence assumption must be resolved in the
frozen statistical plan. Report effect size and interval, not only p-values.
All journey-specific and historical B06 contrasts are secondary, with the
pre-specified multiplicity adjustment retained for their family. No post-hoc
primary selection. At 24 slots/journey, power is limited; a null result is not
equivalence. A simulation using pre-specified plausible effects is required
before freezing, rather than inventing a power percentage.

Without a curated-context drift arm, graph-vs-B06 and search-vs-B06 cannot separate
treatment from model/service/time drift. They are labelled historical secondary
comparisons. The previously presented optional18-trial drift arm is not selected.

Two isolated runners split balanced graph and search slots within each journey
and time block. Both arms must run on both runners; assigning graph to one and
search to the other would confound treatment with machine. Record runner IDs,
resource allocations, source/image hashes, model versions and timestamps. No
shared mutable inputs, output directories, ports or Docker resources. No overlap
with a B06 evidence window on either machine. Runner parity and allocation are
reviewed before execution.

Full G+S design: 311.5667 serial trial-hours, ideal two-runner elapsed floor
155.78335hours (~6.49days at continuous operation), plus preparation, cleanup,
failures and review. At12hours/day this is about13calendar days. The existing
96-hour cap is not satisfied even by the ideal two-runner schedule; an approved
budget/calendar amendment or a separately reviewed smaller design is still
required. Neither is silently chosen here. These are budget arithmetic, not a
promised completion date. Reduced slots would widen intervals and require a new
precision/power assessment before approval.
