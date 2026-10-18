# CardDemo slice 1 — unsigned receipt, October 18, 2026

The bounded six-screen proof passed in [CI run 39127778944](https://github.com/howardweale/lightyear-carddemo-modernization/actions/runs/39127778944). The unchanged strict mutation gate killed **701 / 768 mutants (91.2760417%)**, above 90%. API and browser replay completed all **120 cases / 678 interactions**, including **666 BMS interactions**, all six programs, full field/attribute/cursor/message and PostgreSQL state, and every returned COMMAREA byte. SEND TEXT and invalid-menu source faults retain their explicitly bounded comparisons.

| Gate | Measured result |
|---|---|
| Foundation and Compose smoke | Passed |
| Independent raw-reference sessions in each proof job | 120 / 120 cases; six programs |
| API replay | 678 / 678 interactions |
| Browser replay | 678 / 678 interactions |
| Mutation | 701 KILLED, 49 SURVIVED, 17 NO_COVERAGE, 1 TIMED_OUT; 768 total |
| CI unsigned receipt | Acceptance complete for this bounded proof; no missing measured gates |

Source head: `7aa129137753775f5d35f2eaceaf11b64aa2e162`. Tested synthetic merge: `47c585cb0be676e965950d8bc570ba6aa82b269f`, with parents main `5c1852cc36fc28fc34f16ed91a2243023acdc657` and that source head. GitHub commit metadata verifies identical source and tested trees. These are measurement identities; the generated receipt did not exist in those commits. Its repository publication occurs in a later evidence commit, which the separate Factory request binds explicitly.

The [JSON receipt](carddemo-slice-1-2026-10-18.json) preserves the exact CI-produced bytes, source/generator/mapping/session hashes, all case results, quirks and exclusions. [Provenance](carddemo-slice-1-evidence-2026-10-18/provenance.json) records verified tree identity and archive digests. [Complete original archives](carddemo-slice-1-evidence-2026-10-18/archives) retain every CI artifact, including raw reference sessions, content-addressed database states, browser evidence, PIT XML and diagnostics. Their bytes match GitHub's SHA-256 digests. [File hashes](carddemo-slice-1-evidence-2026-10-18/SHA256.json) and the [mutant review](carddemo-slice-1-evidence-2026-10-18/mutation-review.json) support independent inspection after Actions artifact expiry.

All 67 non-killed mutants remain in the denominator. Static review found residual interpreter/formatting boundaries, intermediate state assignments, role and pagination branches, and missing-record/SQL-exception paths. The replay wrapper intentionally rolls back complete sessions between mutants, so savepoint-release survivors are not evidence of independently proved savepoint behavior. No survivor is waived or classified as equivalent; timeout receives no credit. These limits do not change the configured 90% acceptance rule and remain visible for Howard's review.

The independent baseline executes pinned raw COBOL through a bounded interpreter; shared BMS parsing and typed-data projection are disclosed. Additional hand-specified contracts and mocked READ misses supplement real-PostgreSQL scenario replay. Public fixture bytes remain intact; valid updates use disclosed synthetic SSN/state/ZIP/phone inputs, seven synthetic authorization rows and one synthetic account/cross-reference pair for genuine no-change coverage. Blank-group LOW-VALUES, account ZIP rewrite, retained fraud audit F-to-R transitions, invalid-menu source faults, numeric DISPLAY assumptions, and terminal null projection remain as documented in the JSON quirks.

Native CICS/IMS/DB2/LE and production data are unobserved. Other maps and destination services, SQL-error screen equivalence, public IMS unload compatibility, release and z/OS acceptance remain outside this proof. The October 17 data receipt is preserved unchanged.

This is unsigned evidence for review. It grants no signature, evidence acceptance, import, activation, merge, release or Phase 2 authority. Final PR readiness still requires fresh checks on the publication commit and Howard's approval of that exact green SHA. No local tests, application, generators, compilers or Docker were executed to prepare this packet.

The original CI Markdown has a misencoded heading and is retained byte-for-byte as [raw text](carddemo-slice-1-evidence-2026-10-18/original-ci-receipt.md.txt) and inside its original archive. The readable receipt above is separately authored; the CI JSON and all measured results are unchanged. Future CI receipt headings use ASCII punctuation.
