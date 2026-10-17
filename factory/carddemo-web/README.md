# CardDemo slice 1 web continuation

Scope: COSGN00, COMEN01, COACTVW, COACTUP, COPAU00 and COPAU01, plus linked COPAUS2C. The other fifteen BMS maps are later slices. Transaction IDs, fields, COMMAREA layouts, menu destinations and roles, SQL columns and authorization fraud bindings are generated from pinned public source at `59cc6c2fd7ebd7ef7925cad552a01a4b8b6e4d5e`. There are no manually maintained physical field mappings.

## Implementation and validation

All six stateless Java handlers are registered. They share one PostgreSQL transaction per interaction and a server-verified application session token containing the source-bound COMMAREA and prior terminal state. This application token cannot sign or activate a Factory request. Date, phone, SSN, state/ZIP, FICO and monetary validation and account-update rendering execute source-compiled statements. Account writes acquire both records and retain source change/conflict comparisons. Authorization paging uses parent-qualified segment identity and captured twin order. The linked fraud action and detail replacement share the interaction transaction.

These implementations are undergoing CI validation. Successful component tests are not a claim of full screen equivalence. The independent raw-COBOL reference interpreter, complete generated invalid-field and conflict sessions, every-field/attribute/cursor/message/database comparison through API and Playwright, and a measured screen-handler mutant kill rate of at least 90% remain required. The final dated receipt and Factory request must remain unsigned and must include actual denominators and all gaps.

## Disposable public demonstration

From this directory, `docker compose up --build` builds PostgreSQL, generated schema/fixtures, the Java service and UI. Open `http://127.0.0.1:8080`. CI is the execution environment used for this change; no local application or Docker run has been performed by the agent.

The loader uses the pinned public VSAM records and seven explicitly synthetic IMS authorizations for the first public cross-reference account. It does not parse or claim a verified IMS unload. The fixture volume contains `fixture.json` with the public demonstration login and account. Database credentials are disposable demonstration defaults. The database has no published host port and the UI binds loopback. Do not use this Compose configuration for real data. An omitted session key creates an ephemeral application-only key; restarting the service invalidates existing sessions. No real request signing, import, activation, native execution or Phase 2 is included.

The loader checks the generated-source/fixture identity before reuse and refuses a different existing fixture instead of destroying it. To retain another fixture, use a separate Compose project name and port.

## CI gates

`CardDemo web slice` derives bindings, runs Java component tests, compiles TypeScript, builds the Compose runtime and exercises six-screen API and Playwright journeys. The browser gate compares rendered values and protections to service responses; that comparison is not an independent COBOL oracle. CI artifacts retain frames, runtime diagnostics and explicit gate scope. Disposable CI session signatures are confined to test application paths.

## Retained quirks and evidence limits

- Menu options 3–10 retain source labels and role checks and lead to one explicit `/not-in-this-slice` endpoint. Admin-menu sign-on is outside this six-screen slice.
- COACTUP no-change and concurrency comparisons trim different operands. The source account rewrite places the group bytes where the master layout has ZIP bytes; the implementation preserves this discrepancy.
- Missing-record condition literals differ from assembled messages, allowing subsequent reads. Deterministic initialized working storage is an explicit reference assumption, not observed CICS behavior.
- The source phone predicate repeats the area-code condition; today's DOB is rejected. Invalid DISPLAY bytes use a documented EBCDIC comparison assumption until the source NUMERIC test.
- Authorization PF7 page-counter behavior and short-page next flags are retained. More than twenty recorded pages is refused because the source history array has twenty entries.
- The source's two-digit authorization year uses an explicit 2000–2099 reference window; native DB2 interpretation is unverified. Missing detail and SQL error-path screen equivalence are not yet established.
- Public IMS unload framing, native CICS/IMS/DB2 evidence, and native acceptance remain absent. The earlier data receipt's 500,000 records and 27/40 typed IMS cases do not establish screen equivalence.

No release, z/OS, evidence acceptance, signing or Phase 2 authority follows from these changes or green CI.
