# B06 approved runtime-resolution probe

The single approved probe **passed** on October 6, 2026. Operator review;
not independent attestation. This resolves the six-class runtime selection
question; it is not native journey qualification or measurement admission.

## Execution and cleanup

- Approved source commit: `159897376007c6d6b70fbac1bb96cd390b2bfb0f`.
- Approved window: October 6, 03:00–03:55 UTC.
- Actual start/end: `2026-10-06T03:01:25.491941Z` to
  `2026-10-06T03:03:06.084587Z`.
- Actual probe duration, including cleanup: **100.594 seconds**.
- One attempt; no retry. The deliberately omitted database settings did not
  prevent the plain runtime-catalog test from completing.
- One network-disabled application container; zero database containers,
  native pairs or model calls. Its owned name and label were checked absent.
- Image: `sha256:f3bed005214fbaec7f580a2d27e0dffa7a868bfc913db8c231d6f2b3fe4e0300`.
- Signed probe receipt: `efb25e0d95ae9724d02d1734cd7d83082dd9d173bcf696c8f21dc340316fa346`.
- Separate read-only audit: **1.000 second**, all **1,905** recorded output-file
  hashes matched, approved source bytes unchanged, actual cleanup confirmed.
- Signed [audit](independent-audit.json):
  `294c2386ee34670b6c0d02e0ae435bf5c50c5bd466e56f95e62df88eccc182c9`.

The raw runtime configuration, class blobs and logs remain local under
`work/b06-admission-r7/runtime-resolution-approved/attempt-1/`. Only the
hash-bearing audit and preparation summary are copied beside this report.
These safe summaries form the public review payload; the snapshot itself is
private. See the [r7 milestone](../milestone-r7.md) for the preparation boundary.

## Observed loaded classes

The actual Equinox test runtime loaded `NodeTestTask` and
`ExecutionListenerAdapter` from Tycho's `org.eclipse.tycho.surefire.junit59`
**4.0.8** bundle under `/root/.m2/repository/`. The copy under `/application/`
was not the selected source for these two classes.

| Class | Loaded class SHA-256 |
| --- | --- |
| `org.junit.platform.engine.support.hierarchical.NodeTestTask` | `b8f75cb129bd7c932fc226edfb520335d34cbce6ae659337238918fe4f2b862c` |
| `org.junit.platform.launcher.core.ExecutionListenerAdapter` | `37ffa222eacc16555002cfe2119b38f44b46aa9eefe935af57ab490e64a912ec` |
| `org.compiere.util.DB` | `b0ece1362b62ba035c3d9f816b8574b366099d18d149af33240d17319a7c1f3c` |
| `org.compiere.model.PO` | `1dc95fe1a0282c2ef1552cd33403acaf857033dbdfda14883da2ca14e016920a` |
| `org.compiere.acct.Doc` | `ef54332a50ce9196612d64dbdd25747f843bc4fcae8925adc425e08d31ef97b1` |
| `org.compiere.acct.DocManager` | `2b0cf9982df4de9a2f57923d11612225a006087d48377042bb673251f689ca59` |

The four application classes came from the application base bundle and match
the earlier catalogue. Each of the six had one unambiguous observed source.
This finding does not assert loaded identity for unprobed classes.

## J1 smoke preparation and remaining authorization

The [hash-only preparation summary](j1-smoke-preparation.json) binds a new
local executable snapshot of **2,106 files** at
`work/b06-execution-snapshots/j1-smoke-r7`, based on implementation commit
`d2c59494ce0d1286b32cffa6925a2e143f174b8e`.

- Snapshot: `cc2f9522d3be2d7a527780f98de42391ede4d3c7438ddce0dee6cd64fa38b77b`.
- Preparation summary: `b263fe435a3985ed8fce8eb6fd23ffff5c186ad4187a774cd3632dbab00027b0`.
- Offline assembly duration: **17.156 seconds**, separate from the probe.
- Three slots: retained reference; duplicate-invoice-line native mutant;
  candidate-origin invoice null dereference with direct closed-diagnostic
  inbox delivery and replay required.
- Original r6 private assembly remains unchanged. The new slot closure adds
  the exact public `JourneySupport.java` input required by the inherited J1
  gate. Candidate source bytes and J1 business predicates are unchanged.
- The legacy preparation-hash field binds the verified r6 input manifest;
  this is hash verification of inputs, not a claim of native entry admission.
  Full native entry remains required separately for every slot.
- Image digests, measured runtime class identities, compiled observer,
  class-bound lock SQL, private inputs and real-clock guard are bound.
- Proposed smoke window: **October 7, 03:00–09:00 UTC**. Maximum per pair
  7,190 seconds including finalization; three maxima total 21,570 seconds,
  leaving only 30 seconds in the six-hour window at the extreme bound.
  The controller must refuse any slot without its complete remaining budget.
- The conservative 96-hour calendar guard fits within October. This is a
  three-slot zero-model smoke, not the 135-slot qualification or measurement.

All 2,106 snapshot file hashes and all three slot input closures were rechecked
using the snapshot's own imports. Twenty offline tests covering assembly,
conversion, Tower decisions, delivery, lock SQL and preparation passed.
Two initial sandboxed test invocations encountered Windows temporary-directory
access denials; the unchanged tests passed outside that filesystem sandbox.
These test invocations made no Docker runs or model calls.

**No executable group authorization or Tower request has been issued.**
The existing B06 Tower authority root/public key must first be identified;
the group plan must bind its key hash, distinct from the campaign signer.
After the exact safe group plan has a verified public commit,
`tools.ms94_b06_group_decision.write_request` can construct the request binding
that commit, plan, snapshot and window. Howard must then issue the exact
operator Tower decision with a fresh journal. The campaign signer cannot
substitute for this decision. The conditional window approval alone is
insufficient, and no smoke slot has run.

The one-shot probe follow-up is paused. B05 evidence,
`work/ms94`, template-r1 and J1 predicate sources were not changed.
