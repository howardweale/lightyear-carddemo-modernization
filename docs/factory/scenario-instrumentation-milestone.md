# Workstream 1.1: executed twin coverage

The 16/47 CBACT04C number is a lexical rule-anchor overlap measure. It is not
executed branch coverage and is preserved as historical context. This change
introduces a separate executed baseline on the pinned public twin.

The inventories contain 47 CBACT04C decisions (94 outcomes) and 55 CBTRN02C
decisions (110 outcomes), with original source IDs, paragraph lines and file
operations. Only observed trace markers count. Missing outcomes remain listed
as not observed, with no automatic unreachability claim. Neither program uses
EVALUATE in the pinned procedure; unsupported constructs fail closed rather
than silently reducing the denominator.

Derived fixed-format source records pure IF/UNTIL predicate outcomes at their
evaluation state, real INVALID/NOT INVALID KEY dispatch, paragraph entry and
the live status immediately after each I/O operation. Original source/copybooks
remain unchanged. The two-build acceptance compares every public scenario's
output bytes and return code with the uninstrumented twin. New run receipts
carry `scenario_adequacy`; uninstrumented receipts explicitly say unavailable.

`tools.check_scenario_coverage` reports public-only data separately from the
later generated-scenario campaign. The Ubuntu 24.04 CI artifact retains both
builds, original and derived source hashes, inventories, every input/output,
trace and per-scenario receipt. Runtime numbers must come from that artifact,
not from source inspection. The new tests cover inventory denominators, pure
derived copies, loop evaluation positions, trace validation and unknown-source
refusal. Twelve focused tests passed locally before publication.

Generators, mutation/solver campaigns, release thresholds and the POSTTRAN
second opinion are subsequent deliverables. This instrumentation does not
promote either twin or authorize a model call. All runs are engineering,
uncredited and public-only. No B06 evidence or hold changed.
