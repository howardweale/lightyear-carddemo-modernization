# CardDemo idiomatic screen-group receipt - 2026-10-18

As of 2026-10-18, COSGN00C idiomatic Java passed CI run 39147604819: 120 journeys and 678/678 API/browser interactions. Strict full-scope KILLED/all-generated: 702/769 (91.29%); historical baseline 701/768 (91.28%). SignonService: 19/21 (90.48%); SignonRules: 15/15 (100.00%). Remaining statement-engine programs: COACTVWC, COACTUPC, COPAUS0C, COPAUS1C. Other existing hand-written orchestration: COMEN01C. Open gaps: Missing-detail and SQL-error screen equivalence; Native CICS, IMS and DB2 behavior; Shared BMS parser and data-layout codec; Disclosed synthetic IMS rows and account pair; All surviving, uncovered and timed-out mutants remain in the denominator. No survivor, uncovered mutant or timeout is waived. Final publication CI and merge approval are separate. Unsigned; no signing, import, activation, Phase 2 or release authority.

Source head: `fafc4b3e63e9a4e57b4019d0a3a78d3a2570e0e5`; tested commit: `dba188ba166145808a59274240d0969e2783377a`.

| Class | Previous KILLED / all | Current KILLED / all |
|---|---|---|
| SignonService | 33/35 | 19/21 |
| SignonRules | new class | 15/15 |

Non-killed mutants in the completed group:
- SignonService.authenticate line 76: SURVIVED; removed call to ai/lightyear/carddemo/Commarea::set.
- SignonService.authenticate line 78: SURVIVED; removed call to ai/lightyear/carddemo/Commarea::set.

Surviving sign-on mutations remove intermediate COMMAREA assignments; later routing can overwrite these values. They remain unproved distinctions, not equivalence waivers.

[Original receipt, all seven CI archives, full mutant inventory and hashes](carddemo-cosgn00-evidence-2026-10-18/).
This supersedes the implementation classification for COSGN00C only. Earlier dated receipts and their measurements remain unchanged.
