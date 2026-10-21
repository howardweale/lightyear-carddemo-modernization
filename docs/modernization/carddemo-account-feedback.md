# J1: typed account feedback

`AccountValidationFeedback` holds explicit message reasons, display flag values,
typed storage fields and first-error selection for the existing native COACTUPC
input, text, money, SSN, FICO and state/ZIP helpers. `AccountFeedbackState` is the
small adapter to the original fixed-width storage and message-off predicate.
The source annotations and complete 88-paragraph inventory are checked in CI.

The first non-space message remains intact, including a low-value or tab byte.
Labels retain 25-byte storage truncation and space-only trimming; messages retain
75-byte storage writes. Valid yes/no values stay Y/N, valid range checks retain
stale flags, and STATE/ZIP keeps its literal message without a label prefix.
No new paragraphs are retired and no whole-screen conversion is claimed.

CI compares every storage byte and scratch field against the original parsed
statement bodies across all affected paragraphs, prior errors and input flags.
Separate tests cover every message, flag encoding and storage width, and prove
that the comparison rejects deliberate byte and scratch differences.

The supplemental POM targets both new classes, including nested types. Each
must have nonempty mutation results and at least 90% KILLED out of all generated
mutants; timeout, error and no-coverage statuses earn no credit. Existing tests,
the original POM, independent full-slice proof and frozen receipts are unchanged.
Only CI runs tests and mutation analysis; no local execution or model calls.
