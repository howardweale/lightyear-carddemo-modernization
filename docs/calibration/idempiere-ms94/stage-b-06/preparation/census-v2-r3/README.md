> Superseded before launch by [the 10:00 AM-9:00 PM PDT window](../census-v2-r3-window2/README.md). Original frozen plans remain preserved; all five slots were unstarted.

# Census r3: observed catch activation and failed-run audit

Prospective replacement group for October 9, 2026 **08:30-19:30 PDT**
(15:30 UTC October 9 to 02:30 UTC October 10). Latest full-budget launch:
**09:20:50 PDT**. Five serial fresh pairs, 7,190 seconds each including
finalization, plus 600 seconds reserve. New executable snapshot and exact Tower
approval are required. No Docker run or model call is authorized by this document.

## Preserved r2 failure

R2 stopped on J1 retained reference. Oracle collector stderr:
`java.lang.IllegalStateException: ambiguous generation catch`
(at PostingObserver.failure, original source line 493). Its signed failure
retains 84 events. The native receipt is equipment-failure/equipment-suspect;
there is no candidate verdict. Independent finalization then failed with
`Cannot admit JSON: b06-clock-evidence.json: [Errno 2] No such file or directory`.
The clock record is produced only after both execution lanes finish; the missing
file is a consequence of the incomplete run, not proof of a clock mismatch.
R2 terminal report `417ff6e3ce43fc3c656a2ccde4d3911709a218756c487807ca0eacdb2fcb0388`
remains failed, with one unfinalized attempt and four unstarted slots. Its 878.469
seconds and eight cleaned resources are historical; no result is replaced.

## Correction

JDI catchLocation identifies a method and bytecode location, not a recursive
activation. The prior collector rejected multiple occurrences of that method.
The corrected collector sets a thread-filtered breakpoint at the VM-selected
handler. At that breakpoint it checks the top frame and records the actual frame
count, location and thread. Pending generation entries deeper than this observed
activation are unwound. Uncaught exceptions record depth -1. A superseding
exception replaces the pending catch breakpoint; no method-name guess is used.
The new ready marker requires handler-activation-v1 proof on each unwind during
replay. Historical streams keep their original interpretation. This changes
exception bookkeeping only: class bytes, generated-target proof, J1 predicates,
expected outcomes and all other provenance requirements remain exact.

A failed-run audit authenticates signed collector failure/census records, exact
event bytes, chain and frame commitments. It lists absent artifacts and leaves
clock, observer, diagnostic and gate replay flags false. It creates no missing
clock or execution records and conveys no qualification credit. The controller
preserves the first stop and does not evaluate a partial audit as a passing slot.

## Validation and pending execution

The exact old observer reproduces the ambiguous catch error in a host-JVM
recursive fixture. The corrected observer passes real JDI collection in both
legacy and observer-binding-v2 modes. Host checks include generation completion
and actual handler activation; they are not Oracle/PostgreSQL qualification.
The new audit authenticates all 84 preserved r2 events read-only. The B06 suite
ran 205 tests successfully with 10 optional local-evidence skips. Focused tests
reject wrong handler depth/thread/location, missing new-protocol proof, modified
event bytes, missing failure records, wrong plan and unexpected feedback.

Observer classes compiled with the existing host Corretto 21 javac, with hashes
in observer-compilation.json. Native admission remains blocked pending new
snapshot, publication, exact Tower decision and successful native census. Zero
Docker commands and model calls during this repair. No B05, work/ms94,
template-r1 or J1 predicate changes. Operator review, not independent attestation.
