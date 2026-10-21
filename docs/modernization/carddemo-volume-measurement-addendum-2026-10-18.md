# CardDemo volume measurement correction — 2026-10-18

The historical volume receipts used `raw_round_trip` and `typed_round_trip` for the same comparison: reconstruct typed PostgreSQL columns and compare them with the original generated record bytes. Those two flags establish one check, not two independent round trips. Historical receipt bytes are preserved.

New `carddemo-volume-browse/2` output reports only `typed_round_trip`, with `typed_reconstruction` counts and a summary computed from those counts. It checks complete, unique ordinal coverage. There is no claim of a separate raw-table replay. The byte-key browse comparisons remain separate and unchanged.

CI fixtures corrupt a reconstructed value and require both the result and summary to change. Missing, duplicate and invalid ordinals refuse a complete result. Fresh volume measurements are emitted by the existing PostgreSQL CI job; this correction does not reattribute historical measurements or grant native, release or execution authority.
