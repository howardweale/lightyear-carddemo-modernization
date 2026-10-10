# October 10 review: October 11 engineering window on hold

The previous October 11 9 AM–9 PM PDT engineering approval is suspended by
Howard's review follow-up. **No engineering attempt will start under it.**
The old receipt and approval milestone remain intact as historical records.
No machine, account, Tower, image, signing key or frozen execution file is changed.

The development supervisor, child entrypoint and native execute entrypoint now
refuse with `engineering-on-hold-review-291-302-renewed-approval-required` before
signing or Docker. The hold cannot be overridden by an approval JSON field or
by supplying the previous approval-file digest. It is deliberately unconditional
while the amended runtime is unimplemented. Historical checkouts retain their
original bytes and must not be invoked.

## Amended proposal requirements — not an executable approval

Keep the image, Oracle-only scope, calendar, ten-attempt cap, per-attempt
60-minute work/10-minute cleanup limits, 30-minute candidate timeout, output
budget, zero credit/models and no-overlap rules from the original proposal.
Before requesting renewed approval, bind the following concrete implementation:

1. A memory-bounded observer proven on the host at the old 192 MiB heap, with
   request creation/enabling/disabling and watched class-prepare diagnostics,
   periodic heap high-water telemetry, and clean stop at 85% of heap.
2. Explicit JVM heap and container memory values enforced by the real adapter,
   plus an owned private heap-dump path. Exact values await measured headroom;
   this document does not approve guessed values.
3. Per-attempt strict or diagnostic-unmatched-return mode. A proposed maximum
   of three accepted unmatched returns must be recorded and enforced; every
   other anomaly remains a stop condition. No inferred generation/provenance.
4. Exact implementation commit, observer source and compiled hashes, approval
   digest, and separate engineering signing-key fingerprint checked at launch.
5. A reviewed sequence: one strict attempt, one diagnostic attempt, then stop
   for analysis. No automatic retry or unattended continuation.

This batch has not implemented those memory/signing/runtime changes. The real
native adapter is still unproven. No replacement approval, Tower request, key,
launch receipt or native run was created. Howard must review the final concrete
plan and explicitly re-approve before this hold can be lifted.
