# Optional Tycho development outputs — practice r8b

Howard requested “fix and rerun” after the failed r8 practice. This authorizes
one fresh non-evidence practice, with the same pinned image, no network,
databases, native pairs or model calls, and owned cleanup only. No Tower request.

The previous capture incorrectly required every dev.properties output directory
to exist. New folder-selection policy `/2` records an absent `target/classes`
or `target/test-classes` only when explicitly declared as a dev output and not
also required by Bundle-ClassPath. It does not create a directory or synthesize
content. Missing manifest roots, other dev paths, symbolic links and external
paths still refuse. Presence is rechecked after streaming; any change refuses.
The effective dev.properties bytes, manifest, ordered classpath, explicit absent
roots and file hashes are replayed. A loaded class from an absent root refuses
both capture and replay. Historical selection `/1` replay is retained.

98 offline tests passed in 16.174 seconds, including full worker/producer/replay
on the absent-output fixture and negatives for loaded-class attribution,
changed presence, a missing manifest root and a forged absence over real files.

Fresh plan hash:
`b65272f5de7b054a6cfe0fb9894421c51d445f004d8a3bbece3ed74cd82196ef`.
Local directory: `work/b06-runtime-practice-r8b`. This is a new one-shot plan;
the old r8 practice and r7 evidence remain unchanged. All 285 r7 frozen files
and 12 old practice source copies were checked unchanged before final reporting.

Practice passed in 387.000 seconds with replay and independently verified cleanup; see [r8b review](practice-r8b-review.json). Native admission remains
blocked; this is operator review, not independent attestation.
