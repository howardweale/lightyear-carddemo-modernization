# CardDemo slice 1 web continuation

Scope authorized by Howard: COSGN00, COMEN01, COACTVW, COACTUP, COPAU00 and COPAU01. The other fifteen BMS maps remain later slices. Transaction IDs, menu destinations and roles, COMMAREA offsets, BMS fields, and database columns are derived from public sources pinned at the commit recorded in `spec/modernization/carddemo-screens/provenance.json`.

The pending-authorization detail screen links to COPAUS2C for PF5 fraud actions. That source writes DB2 AUTHFRDS before the caller updates IMS detail. Its public DDL and DCL are pinned and the PostgreSQL schema is generated from the DDL. This dependency must be included in the eventual transaction and after-state proof.

## Implementation status

The source inventory, six BMS models, base COMMAREA codec, HMAC session envelope, typed JDBC lookup, and sign-on/menu translations are under construction and CI review. The token uses a separate application session key and cannot sign a Factory request. CI uses disposable fixtures only. No local suite or application is executed as part of this work.

The account view/update and authorization handlers, program-specific COMMAREA extensions, generated TypeScript UI, HTTP/transaction integration, Compose acceptance, independent reference interpreter, API/browser sessions, mutation denominator, durable receipts and unsigned Factory request are still required. There is no full-screen equivalence claim, no running application claim, and no release or Phase 2 authorization.

Menu options outside slice 1 retain their original labels and role checks and target `/not-in-this-slice`. They are listed individually in the generated quirks inventory. They do not get placeholder business services.

## CI

`CardDemo web slice` derives bindings, compiles Java and tests source-bound menu behavior, COMMAREA bytes, tampering and expiration. This initial gate establishes the foundation only; it is not the P5 screen proof. P5 must compare all field values and attributes, cursor, messages and PostgreSQL after-state after each interaction through both API and Playwright, with at least 90% of screen-handler mutants caught.
