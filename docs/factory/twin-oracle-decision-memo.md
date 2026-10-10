# Decision memo: provisional twin and future default-oracle promotion

Decision requested: retain the public twin as an engineering answer key, with
POSTTRAN provisional and non-releasable. Do not promote it to a general z/OS
replacement yet. Howard's POSTTRAN decision is implemented as the chosen answer
key class; it does not waive the four safeguards.

The original 18 exact comparisons establish three INTCALC datasets only, not
broad coverage. Original receipts remain unchanged. New CI exercises the real
compiler, runtime clock, collation, repeatability and independent POSTTRAN
invariants. [Twin limits](twin-limits.md) records what is emulated and unknown.
Generated-scenario reconciliation becomes a promotion prerequisite when the
Workstream1.2 generator lands; none is present in this checkout. The current
POSTTRAN Java second opinion is also absent, so disagreements cannot yet be
resolved by comparison. No Python POSTTRAN reference is introduced.

Promotion requires: generated-scenario three-way agreement; no unresolved
field/status/timing differences; completed platform probes; deterministic repeat
outputs; and a signed operator review of the public sample. Review signatures
must come from the actual reviewer through the approved signing path. They are
operator review, not independent attestation. Any twin/Java disagreement blocks
promotion pending a person deciding which implementation is wrong.

Even after that engineering gate, VSAM locking/recovery, Enterprise COBOL runtime
edge cases, code-page behavior and production environment remain unconfirmed
until an authorised Maintec/z/OS baseline. No Maintec data is accessed here.
CICS online, DB2 and IMS require legacy-platform answer keys and remain outside
the batch twin's scope.
