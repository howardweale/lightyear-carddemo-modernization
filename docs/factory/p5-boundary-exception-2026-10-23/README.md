# P5 boundary exception — 23 October 2026

Status: review draft; final-head CI pending. No merge, signing, spend or factory-run permission.

The [first eight-drill run](https://github.com/howardweale/lightyear-carddemo-modernization/actions/runs/40039170100) found two safety gaps: a call at the wall-clock cap and eight concurrent admissions for one nonce. The [second run](https://github.com/howardweale/lightyear-carddemo-modernization/actions/runs/40046311187) met all eight Linux component expectations, while its Windows boundary regression still failed. Full controller qualification remains incomplete.

The nonce fix serializes the real read/check/append/fsync operations under an OS lock. The deadline fix compares monotonic time directly to the deadline, refusing equality. A deterministic floating-point regression exercises a start value where subtraction rounds below the cap. The actual failing Windows start was not recorded; fresh Windows CI must validate the fix.

Historical `providers.py` bytes remain identical to main. The exact old/new source hashes and every located historical binding record are in `exception.json` and `binding-inventory.json`. The only net F2-fenced source change is `budgeted_providers.py`; no judge-freeze path changes. The nonce source is outside the F2 fence but has historical record bindings, all retained in the inventory without rewriting those records.

The original harness commit remains separate. Existing combined-repair history is preserved, then explicitly reversed and replaced by separate nonce and deadline commits. This is additive history, with no force push or squash.

F2 recomputation is deferred until after #455 merges, using the exact final PR head and resulting merge. No new plan seal, request binding or readiness is created here. The earlier orchestrator mismatch remains an unresolved finding, not an adopted change.

The PR drill table retains all eight before-fix outcomes and must receive final-head outcomes with run links after independent artifact review. Pending results are not passes. The qualification gate remains intact; full controller/receipt gaps still block go/no-go. Wednesday 28 October 18:00 PT is at risk. Ten-minute checks remain off.
