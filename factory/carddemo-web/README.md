# CardDemo slice 1 web continuation

Scope: COSGN00, COMEN01, COACTVW, COACTUP, COPAU00 and COPAU01, plus linked COPAUS2C. The other fifteen BMS maps are later slices. Transaction IDs, fields, COMMAREA layouts, menu destinations and roles, SQL columns and authorization fraud bindings are generated from pinned public source at `59cc6c2fd7ebd7ef7925cad552a01a4b8b6e4d5e`. There are no manually maintained physical field mappings.

## Implementation and validation

All six stateless Java handlers are registered. They share one PostgreSQL transaction per interaction and a server-verified application session token containing the source-bound COMMAREA and prior terminal state. This application token cannot sign or activate a Factory request. Date, phone, SSN, state/ZIP, FICO and monetary validation and account-update rendering execute source-compiled statements. Account writes acquire both records and retain source change/conflict comparisons. Authorization paging uses parent-qualified segment identity and captured twin order. The linked fraud action and detail replacement share the interaction transaction.

These implementations and the six raw-reference adapters are undergoing CI validation. Successful component tests are not a claim of full screen equivalence. The independent raw-COBOL reference interpreter, complete generated invalid-field and conflict sessions, every-field/attribute/cursor/message/database comparison through API and Playwright, and a measured screen-handler mutant kill rate of at least 90% remain required. The final dated receipt and Factory request must remain unsigned and must include actual denominators and all gaps.

## Disposable public demonstration

From this directory, `docker compose up --build` builds PostgreSQL, generated schema/fixtures, the Java service and UI. Open `http://127.0.0.1:8080`. CI is the execution environment used for this change; no local application or Docker run has been performed by the agent.

The loader uses the pinned public VSAM records and seven explicitly synthetic IMS authorizations for the first public cross-reference account. It does not parse or claim a verified IMS unload. The fixture volume contains `fixture.json` with the public demonstration login and account. Database credentials are disposable demonstration defaults. The database has no published host port and the UI binds loopback. Do not use this Compose configuration for real data. An omitted session key creates an ephemeral application-only key; restarting the service invalidates existing sessions. No real request signing, import, activation, native execution or Phase 2 is included.

The loader checks the generated-source/fixture identity before reuse and refuses a different existing fixture instead of destroying it. To retain another fixture, use a separate Compose project name and port.

## CI gates

`CardDemo web slice` derives bindings, runs Java component tests, compiles TypeScript, builds the Compose runtime and exercises six-screen API and Playwright journeys. The browser gate compares rendered values and protections to service responses; that comparison is not an independent COBOL oracle. CI artifacts retain frames, runtime diagnostics and explicit gate scope. Disposable CI session signatures are confined to test application paths.

## Retained quirks and evidence limits

- Menu options 3-10 retain source labels and role checks and lead to one explicit `/not-in-this-slice` endpoint. Admin-menu sign-on is outside this six-screen slice.
- COACTUP no-change and concurrency comparisons trim different operands. The source account rewrite places the group bytes where the master layout has ZIP bytes; the implementation preserves this discrepancy.
- Missing-record condition literals differ from assembled messages, allowing subsequent reads. Deterministic initialized working storage is an explicit reference assumption, not observed CICS behavior.
- The source phone predicate repeats the area-code condition; today's DOB is rejected. Invalid DISPLAY bytes use a documented EBCDIC comparison assumption until the source NUMERIC test.
- Authorization PF7 page-counter behavior and short-page next flags are retained. More than twenty recorded pages is refused because the source history array has twenty entries.
- The source's two-digit authorization year uses an explicit 2000-2099 reference window; native DB2 interpretation is unverified. Missing detail and SQL error-path screen equivalence are not yet established.
- Public IMS unload framing, native CICS/IMS/DB2 evidence, and native acceptance remain absent. The earlier data receipt's 500,000 records and 27/40 typed IMS cases do not establish screen equivalence.

No release, z/OS, evidence acceptance, signing or Phase 2 authority follows from these changes or green CI.

## Independent six-screen proof and unsigned receipt

The raw-source interpreter has independent declaration/overlay storage, qualified
references, bounded control flow and CICS/DLI/SQL ports for all six screens,
the linked COPAUS2C fraud action and CSUTLDTC date wrapper. It does not use the
Java edit AST or candidate responses to calculate expected results. The BMS
parser and physical data-plan/typed projection codec are disclosed shared
dependencies. CI confirmation is required; implementation is not proof.

`prove_slice.py` builds source-shaped invalid-field, missing-record, page-boundary,
no-change, committed/cancelled update, two-session conflict, fraud-toggle and PF3
sessions. Each API and Playwright interaction compares every field and effective
attribute, cursor, message and every PostgreSQL table against the raw reference.
Browser replay uses independent pages for interleaved signed application sessions
and exercises PF buttons and keyboard shortcuts. SEND TEXT is compared as a
terminal text response with no BMS fields. Non-ERASE sends preserve terminal
state according to the map's low-value fields.

The pinned menu emits an invalid-option error and then accesses an invalid table
subscript. Proof compares that emitted image and database state and records the
source fault and physical trace; it discards that session without claiming a
successful COBOL return or fabricating continuation. Options outside slice 1
remain explicit navigation boundaries. Native CICS behavior remains unobserved.

The CSUTLDTC wrapper executes from pinned source. The bounded CEEDAYS port models
Gregorian YYYYMMDD and documented feedback numbers and Lilian epoch from
[IBM CEEDAYS](https://www.ibm.com/docs/en/zos/2.5.0?topic=services-ceedaysconvert-date-lilian-format).
Valid and invalid leap-day cases are required. This is not native LE execution.

CI uses three separate disposable fixtures for API, browser and mutation proof.
PIT mutates the six Java handlers and their validation/rendering/write helpers;
the denominator includes every generated mutation in that configured scope.
Only KILLED mutations count toward the required 90%; timeouts, uncovered code,
survivors and errors remain in the denominator. A real-PostgreSQL JVM replay uses
the same independent reference sessions, rolling back between mutant executions.
Separate engine tests check commit/rollback calls.

`receipt.py` creates dated Markdown/JSON artifacts with exact source/tested SHAs,
every gate's result and denominators, source/data/mapping/generator/session hashes,
quirks, scope and missing evidence. Missing or failed artifacts fail the gate.
The receipt is an unsigned Factory review request for Howard; it is never signed,
imported or activated. Final measured results remain pending until CI completes.

Compose CI alone fixes the business clock through `reference-ci`; normal Compose
uses real time. Session expiration retains real time. The mutation-only Compose
override publishes PostgreSQL on runner loopback, solely for disposable JVM tests.
No local test, application, generator or Docker execution was used for this work.

The independent reference NUMVAL-C adapter accepts the slice's default-dollar,
decimal-point edited values, including spaces after a sign and leading-decimal
zero amounts. It rejects embedded digit spaces and duplicate signs, and bounds
precision to 15 digits. TEST-NUMVAL-C exposes only zero/nonzero validity because
the pinned programs do not consume the invalid-character position. Grammar is
based on [IBM NUMVAL-C](https://www.ibm.com/docs/en/cobol-zos/6.3.0?topic=functions-numval-c),
not candidate Java results. Protected FSET input is reconstructed from the prior
reference frame, with caller attempts to overwrite protected fields rejected.

The proof retains the public fixture bytes, including its source-invalid SSN and state/ZIP pair. Positive update scenarios submit explicitly synthetic SSN 123-45-6789, OR/97001 and phone 2 (206)555-0102; invalid-field cases start with these valid inputs so unrelated public-data errors cannot mask the target edit. Every submitted field remains in the case artifacts. Visible terminal values render null cells as blanks, while each raw reference frame retains exact symbolic-output hex. First-byte null selection follows [IBM BMS output rules](https://www.ibm.com/docs/en/cics-ts/6.x?topic=support-bms-design-performance). This remains a bounded terminal projection, not a native 3270 execution claim.

The no-change proof uses a separate synthetic account (90000000001) and cross-reference (card 9000000000000001), cloned from public records with group PROOFGRP and the same customer. All original records remain unchanged in the seed. This is necessary because pinned COACTUPC maps a blank submitted group to LOW-VALUES, which differs from a stored space-filled group; a separate post-commit resubmission case asserts that quirk and the absence of writes. The genuine no-change case still requires NO-CHANGES-DETECTED, no INPUT-ERROR and no REWRITE.

The raw reference preserves relational NOT across abbreviated comparisons such as `selection NOT = SPACES AND LOW-VALUES`, while a leading logical NOT applies only to its own condition, following [IBM abbreviated-condition semantics](https://www.ibm.com/docs/en/cobol-zos/6.3.0?topic=expressions-abbreviated-combined-relation-conditions). The full proof explicitly requires invalid-selection rejection, detail navigation and both fraud-toggle messages/database transitions before its six-screen coverage gate.

Pinned COPAUS2C retains the AUTHFRDS audit row when fraud is removed: duplicate INSERT invokes FRAUD-UPDATE, setting AUTH_FRAUD to R and the report date to CURRENT DATE. The proof requires the F-to-R transition with unchanged row count, key and all other payload columns, preserves pre-existing rows, and compares the complete database after both actions. It does not expect deletion.

Full-proof interactions reference complete expected database snapshots by SHA-256; browser and Java replay verify the bytes before comparing every table and row. Identical states are stored once, avoiding the former 842 MB repeated-state cases file without reducing comparisons or case counts. Numeric DISPLAY condition names retain invalid/LOW-VALUES bytes under the disclosed EBCDIC comparison bound until source validation.
