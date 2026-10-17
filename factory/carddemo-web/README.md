# CardDemo slice 1 web continuation

Scope authorized by Howard: COSGN00, COMEN01, COACTVW, COACTUP, COPAU00 and COPAU01. The other fifteen BMS maps remain later slices. Transaction IDs, menu destinations and roles, COMMAREA offsets, BMS fields, and database columns are derived from public sources pinned at the commit recorded in `spec/modernization/carddemo-screens/provenance.json`.

The pending-authorization detail screen links to COPAUS2C for PF5 fraud actions. That source writes DB2 AUTHFRDS before the caller updates IMS detail. Its public DDL and DCL are pinned and the PostgreSQL schema is generated from the DDL. This dependency must be included in the eventual transaction and after-state proof.

## Implementation status

The source inventory, six BMS models, program-specific COMMAREA codecs, HMAC session envelope, typed JDBC lookup, sign-on/menu/account-view translations, one-transaction HTTP dispatcher, and model-driven TypeScript renderer are under construction and CI review. The token uses a separate application session key and cannot sign a Factory request. CI uses disposable fixtures only. No local suite or application is executed as part of this work.

COACTUP’s locked two-record rewrite and twelve source-compiled generic, phone, SSN, state/ZIP and FICO edit paragraphs are implemented as internal components. Their tests await CI; they are not registered as a working account-update handler. Source declarations, conditions, statements and messages carry physical source locations, and unsupported syntax refuses compilation. Date/money validation and the full confirmation state machine remain outstanding. Quoted COPY dependencies and the called date service are now inventoried recursively, with CEEDAYS explicitly external.

The account-update and authorization handlers, complete account-view edge behavior, Compose acceptance, independent reference interpreter, API/browser sessions, mutation denominator and final unsigned Factory request are still required. The dated data-only receipt and public release asset preserve 500,000 records and 27/40 typed IMS cases; they do not establish screen equivalence. The account-view path with a missing master but a present customer fails explicitly until the COBOL uninitialized-record behavior is established; it must not be reported as faithful yet. COACTUP no-change and concurrent-change comparisons are generated separately because the source trims different operands. The HTTP dispatcher currently registers only the three implemented handlers; the other slice handlers remain unavailable. There is no full-screen equivalence claim, no running application claim, and no release or Phase 2 authorization.

Menu options outside slice 1 retain their original labels and role checks and target `/not-in-this-slice`. They are listed individually in the generated quirks inventory. They do not get placeholder business services.

## CI

`CardDemo web slice` derives bindings, compiles Java and TypeScript and tests source-bound menu/account-view behavior, program-specific COMMAREA bytes, tampering, expiration, and interaction commit/rollback. This initial gate establishes the foundation only; it is not the P5 screen proof. P5 must compare all field values and attributes, cursor, messages and PostgreSQL after-state after each interaction through both API and Playwright, with at least 90% of screen-handler mutants caught.
