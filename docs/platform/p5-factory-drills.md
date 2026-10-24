# P5 factory failure drills

Status: draft measurement harness; not a go decision or a completed dress rehearsal.
No local invocation is authorized. The workflow uses disposable CI authorities,
synthetic inputs, a stub provider and the existing production verifiers. It never
loads the installed Tower, operator keys, private answer values or model credentials.

The fixture creates an isolated Git executable and commits the four bound inputs.
It signs a synthetic engineering approval with a disposable Tower authority, then
commits only the plan, contract and proof. The unchanged FactoryModelAdmission
checks the actual committed evidence, executable ancestry, clean tree, runtime
inputs, role/model identity, caps, window, signatures and external trust head.
The hardened work-order verifier separately checks a disposable HMAC envelope.
Corrupted HMAC and Ed25519 receipts are negative controls. No verifier is mocked
in the drill job. Synthetic report-policy unit tests mock signature results only
to isolate report rules; those tests are not signature acceptance evidence.

| Drill | Measurement in this draft | Remaining qualification gap |
|---|---|---|
| Kill mid-build | Actual subprocess termination after READY; no candidate marker | Full controller kill/recovery and its failure receipt |
| Worker network | Actual OCI backend, pinned image, network-none denial; reachable bridge positive control | Controller post-denial receipt |
| Budget exhausted | Real per-call admission and two-call cap; third stub call refused | Dollar/token and fallback subcases; complete controller receipt |
| Tower unreachable | Real verifier and signed journal behind disposable HTTP relay; admission and append outages | Deployed API/controller outage path and fallback receipt |
| Workspace changed | Actual tracked bytes changed after sealing; real runtime admission before stub | Race-time assembled-worker replacement and full controller receipt |
| Answer fragment | Exact unchanged normalized 40-character scanner, synthetic fragment, zero downstream stub calls | Full controller context construction and failure receipt |
| Wall/window | At and beyond elapsed cap, signed window immediately before and at end | Full controller timeout receipt; measured boundary mismatch if any |
| Duplicate attempt | Sequential replay and eight concurrent real nonce verifications | Run-directory identity and controller receipt |

The concurrent test forces a feasible interleaving: all actual ledger reads
complete before any append. It does not replace the read values, signature checks,
or writes. Counts report observed admissions; they are never changed to one to
make the test pass. This measures a race boundary, not arbitrary scheduler coverage.
The wall test injects only the monotonic clock, and supplies explicit times to the
real signed-window verifier. Boundary outcomes are reported even if unexpected.

Each completed component observation is signed by the disposable observer, binds
the source hashes, CI checkout, run and attempt, and includes expected/observed
results and gaps. Public artifacts contain only those observations and disposable
public keys. Authority files and credentials stay in temporary directories and are
never uploaded. Raw synthetic answer fragments are not included in public reports.

An observer receipt is explicitly **not** a production controller failure receipt.
The qualification step verifies retained signatures and refuses missing records,
harness errors, mismatched summaries, failed expectations, observer-only receipts
or any remaining gap. This draft therefore intentionally blocks qualification
until end-to-end evidence is implemented. Green report-policy tests or successful
measurement cannot make the factory run eligible. Production and frozen files are
unchanged; a measured defect requiring a frozen change must be escalated, not fixed
through an implicit exception.

Post actual results and each remaining gap to approval queue issue #436 after
independent artifact review. The deadline remains Wednesday 28 October 2026,
18:00 America/Los_Angeles. Any unresolved qualification gap blocks go/no-go unless
Howard explicitly accepts it in writing; the harness does not encode an automatic
override. Java idiomatic-index change: zero. No model spend, real signing or run
authority is granted by this PR. Ten-minute checks stay off.
