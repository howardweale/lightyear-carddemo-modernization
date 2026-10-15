# POSTTRAN Phase 2 authorization

The October 14 plan is copied unchanged from preparation run 38753431205, artifact 11983520538. The October 15 execution addendum preserves its candidate, compiler image, scenarios, inputs and comparisons. It binds the reservation repair and makes the return-code rule explicit: equal 0 or 4 may agree; equal 8 or 12 diverge. Only `generated:posttran-duplicate-id` permits candidate 999 against twin 12.

The unsigned request uses the existing Factory `engineering-run-approval` kind, whose required role is `campaign-authorizer`. Its request seal is the complete execution-plan digest; `observer_sha256` binds the workflow; `class_hashes` bind the candidate, provenance and compiler image archive. These are field mappings for this existing kind, not an observer or class-loading run. Caps mean attempt 1, one run, no retries. The public authority key is committed; no private key is included.

A signature cannot be embedded in the same Git commit whose hash it signs. The request therefore binds an exact executable commit. A later execution PR may add only the unsigned request and its signed proof; any code, plan, key or other change is refused. The existing approved-head variable must still match the exact final execution PR head, and a separate externally configured `POSTTRAN_PHASE2_APPROVED_JOURNAL_HEAD` binds the trusted signed journal. Variables alone never authorize execution.

Before creating the consumed tag, the runner verifies the proof, the exact plan and candidate bindings, the preparation artifact's existence, its downloaded image archive hash, and at least 24 hours of retention. A failure creates no consumed tag. An unknown result after the tag POST still consumes the attempt conservatively and must not be retried.

The retained compiler artifact expires **October 29, 2026 at 14:49:11 UTC**. The authorization window ends 24 hours earlier; retention is rechecked immediately before reservation. No proof is supplied, no repository approval variable is changed, and no comparison is authorized by this document. Howard's exact-final-green-commit approval remains required before merging.
