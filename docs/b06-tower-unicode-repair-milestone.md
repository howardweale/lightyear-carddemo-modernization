
# B06 Tower Unicode serialization correction

The original r1 request failed closed before approval: the producer hashed ASCII-escaped JSON while the writer stored UTF-8 Unicode. An en dash in the review waiver exposed the mismatch in evidence and request-envelope hashes. The correction uses Tower canonical bytes and digest at its request boundary; native plan content seals and frozen r1 evidence are unchanged.

The new end-to-end Unicode regression reproduced the original hash mismatch, then passed with the correction. It checks the real inbox, producer/consumer bindings, idempotence, and tamper rejection. The replacement freeze also exercises its exact full plan through the real inbox. No observer policy, native evidence, or historical outcome is relabeled.

## Frozen preparation completed

Completed 2026-10-10T18:07:12.414752+00:00 in 1888.032 seconds, with zero Docker/model calls.
All 113,611 frozen files, 783 public source comparisons and 70 focused frozen tests passed.
Plan `6ad761916d4e2b2dcfae86b38f3f368292b18f9ff5c94c49c3a9fbaafe038048`; snapshot `61c6749befdfed62796db3752db611c1836b9e8db7d6359b0e876224abed5ebe`.
[Full plan](calibration/idempiere-ms94/stage-b-06/preparation/observer-unmatched-r2/README.md).
Publication and preparation do not authorize native execution.
