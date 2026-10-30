# M2.1 INTCALC duplicate-xref refusal - draft

Backlog lane - 30 October 2026.

The source/index mismatch is OPEN as KF-006 in the
[M5 addendum](m5-intcalc-xref-addendum-2026-10-30.json), with exact source hashes.
CBACT04C SELECT lines 34-39 omit WITH DUPLICATES; XREFFILE.jcl lines 72-75 define
the account AIX as NONUNIQUEKEY. Native z/OS behavior remains unknown.

The interim Java policy is an explicit, value-free IllegalStateException:
INTCALC duplicate XREF account key: multiple cards require z/OS confirmation.
No card is selected and no source/index declaration is changed.
No legacy equivalence is inferred. The existing twin contract stays intact.
The check precedes the balance loop, including an empty balance input.

Two authored regression cases cover reversed several-card inputs and duplicate
keys on empty input. Existing normal/default/zero-rate/EOF-policy tests remain.
Planned: CI checks these Java cases. No local workload or test execution occurs.
No new mutation kill, survivor reclassification or release credit follows.

[M4 native question](m4-zos-confirmation-2026-10-30.md) remains unfilled.
[Howard's work order and correction](work-orders/m2-p6-p7-2026-10-23.md) is the
reference. Process exit mapping belongs to the separate M2.4 draft.

Draft only. No workflow, POSTTRAN-bound, COPAU/F2/fence or preserved evidence
change. The code draft pushes normally for CI feedback, sparingly; the work-order
documentation commit uses [skip ci]. No merge before run verification is complete.
