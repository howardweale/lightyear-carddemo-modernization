# M2.5 timestamp policy and normalization alignment - draft

Backlog lane - 30 October 2026. Additive source review; no runtime/source changes.

## The two timestamp policies

CBACT04C calls Z-GET-DB2-FORMAT-TIMESTAMP for each generated transaction.
That paragraph calls FUNCTION CURRENT-DATE each time, moves hundredths to the
first two fractional positions and fills the remaining four with zeroes.
Original and processing timestamp are equal within a transaction; different
transactions can observe different instants with a live clock.

The Java service receives one 26-character timestamp for the whole invocation
and copies it to both fields of every generated transaction. That is the
current single-timestamp policy, not per-record live-clock fidelity.

The [dated source and normalization record](m2-intcalc-timestamp-policy-2026-10-30.json)
binds all relevant bytes. The bounded comparison policy is the same deterministic
fixed instant on both sides. The current twin runtime_clock supports a fixed
calendar-valid timestamp with fractional 000000. Within that domain, repeated
CURRENT-DATE calls and Java's single value are comparable without discarding time.
Other live-clock or fractional-time behavior needs separate evidence and policy.

## Exact comparison boundary

The active comparator excludes only filler dataclass fields. Both
original_timestamp and processing_timestamp participate in field comparison.
The three runtime normalization rules are decimal canonical text, fixed-width
right padding and copybook filler. There is no timestamp omission, tolerance,
date truncation or record-to-record reordering rule.

Static AST-literal inspection confirms that the ledger's ID/scope/behavior
triples exactly equal the runtime rule literals, with ignored fields={filler}.
For the declared 26-character timestamp format, every non-padding timestamp
character is significant. Blank or different timestamps remain differences.
This is a static alignment finding, not a newly measured CI or native result.

Existing CI test sources cover different/blank timestamps, filler-only exclusion,
ledger/runtime agreement and the same injected timestamp requirement. Their
names and exact source hashes are in the dated record. No new local test or
workload is part of this documentation preparation.

## Additive correction to older metadata

The older spec/carddemo-intcalc.json says timestamps are ignored by the
comparator. That text contradicts the active comparator and ledger. This
record preserves the discrepancy explicitly and supersedes that explanatory
sentence for this review; it does not edit the old file or weaken comparison.

No live-clock legacy equivalence, new mutation kill, survivor reclassification,
native confirmation or release authority follows from fixed-clock comparability.
The choice of future live per-record versus single-instant business behavior is
still a separate keep-or-fix decision if the execution domain changes.

Draft only. Documentation uses [skip ci]; full CI before any later merge after
the run verification. No workflow, source, POSTTRAN/COPAU/F2/fence, model call,
signing or merge changes.
