# CardDemo slice 1 â€” unsigned receipt

Status: proved-in-ci. Acceptance complete: True.

Source head: 7aa129137753775f5d35f2eaceaf11b64aa2e162; tested commit: 47c585cb0be676e965950d8bc570ba6aa82b269f.

| Gate | Passed | Evidence |
|---|---|---|
| api-reference | True | {"passed": true, "programs_compared": 6, "programs_required": 6, "interactions": 678, "bms_interactions": 666, "completed_cases": 120, "planned_cases": 120, "case_denominator_status": "complete generated suite", "validated_fields": ["AADDGRP", "ACRCYCR", "ACRCYDB", "ACRDLIM", "ACSADL1", "ACSADL2", "ACSCITY", "ACSEFTC", "ACSFNAM", "ACSGOVT", "ACSHLIM", "ACSLNAM", "ACSMNAM", "ACSPFLG", "ACSPH1A", "ACSPH1B", "ACSPH1C", "ACSPH2A", "ACSPH2B", "ACSPH2C", "ACSSTTE", "ACSTFCO", "ACSTTUS", "ACSZIPC", "ACTSSN1", "ACTSSN2", "ACTSSN3", "ACURBAL", "DOBDAY", "DOBMON", "DOBYEAR", "EXPDAY", "EXPMON", "EXPYEAR", "OPNDAY", "OPNMON", "OPNYEAR", "RISDAY", "RISMON", "RISYEAR"]} |
| browser-reference | True | {"passed": true, "programs_compared": 6, "programs_required": 6, "interactions": 678, "bms_interactions": 666, "completed_cases": 120, "planned_cases": 120, "case_denominator_status": "complete generated suite", "validated_fields": ["AADDGRP", "ACRCYCR", "ACRCYDB", "ACRDLIM", "ACSADL1", "ACSADL2", "ACSCITY", "ACSEFTC", "ACSFNAM", "ACSGOVT", "ACSHLIM", "ACSLNAM", "ACSMNAM", "ACSPFLG", "ACSPH1A", "ACSPH1B", "ACSPH1C", "ACSPH2A", "ACSPH2B", "ACSPH2C", "ACSSTTE", "ACSTFCO", "ACSTTUS", "ACSZIPC", "ACTSSN1", "ACTSSN2", "ACTSSN3", "ACURBAL", "DOBDAY", "DOBMON", "DOBYEAR", "EXPDAY", "EXPMON", "EXPYEAR", "OPNDAY", "OPNMON", "OPNYEAR", "RISDAY", "RISMON", "RISYEAR"]} |
| browser | True | {"passed": true, "interactions": 678, "required": 678} |
| mutation-reference | True | {"passed": true, "programs_compared": 6, "programs_required": 6, "interactions": 678, "bms_interactions": 666, "completed_cases": 120, "planned_cases": 120, "case_denominator_status": "complete generated suite", "validated_fields": ["AADDGRP", "ACRCYCR", "ACRCYDB", "ACRDLIM", "ACSADL1", "ACSADL2", "ACSCITY", "ACSEFTC", "ACSFNAM", "ACSGOVT", "ACSHLIM", "ACSLNAM", "ACSMNAM", "ACSPFLG", "ACSPH1A", "ACSPH1B", "ACSPH1C", "ACSPH2A", "ACSPH2B", "ACSPH2C", "ACSSTTE", "ACSTFCO", "ACSTTUS", "ACSZIPC", "ACTSSN1", "ACTSSN2", "ACTSSN3", "ACURBAL", "DOBDAY", "DOBMON", "DOBYEAR", "EXPDAY", "EXPMON", "EXPYEAR", "OPNDAY", "OPNMON", "OPNYEAR", "RISDAY", "RISMON", "RISYEAR"]} |
| mutation | True | {"passed": true, "killed": 701, "total": 768, "percent": 91.27604166666667, "threshold": 90, "missing_screen_handlers": [], "status_counts": {"KILLED": 701, "SURVIVED": 49, "NO_COVERAGE": 17, "TIMED_OUT": 1}, "denominator": "every PIT mutation in configured screen-handler/helper scope; timeout, no-coverage and errors are not counted killed", "report": {"path": "work/carddemo-proof-artifacts/carddemo-proof-mutation/pit-reports/mutations.xml", "sha256": "949c9a77a5d53b1b2f02b82424c0f18dbb106b387e2e448f0de530e1a60265b9"}} |
| ci-jobs | True | {"passed": true} |

Remaining evidence gaps: 

Quirks:
- Additional hand-specified language/routing contracts and mocked master READ-miss tests supplement independent raw-source real-PostgreSQL replay; they do not generate scenario expectations
- COPAUS0C selection XCTL preserves page count and pagination history before GATHER-DETAILS
- COACTUPC retains the requested account key in old details before a failed cross-reference read
- COMEN01C first entry sets reentry context before returning its menu screen
- API, browser and Java replay compare complete returned COMMAREA bytes; SEND TEXT has no token and raw source faults have no proved RETURN state
- COSGN00C uses fresh working storage and retains uppercase submitted user ID after error SENDs
- Record rewrites preserve explicit no-sign and non-negative-zero encoding metadata for unsigned DISPLAY and binary numeric fields
- AUTHFRDS fixed PIC X SQL hosts retain padding; VARCHAR follows its explicit length; PostgreSQL JSON timestamp spelling removes only fractional trailing zeros without losing microseconds
- PAUTDTL1 uses the pinned DBD unique PAUT9CTS ascending byte-key sequence within each parent; synthetic insertion/twin ordinals remain provenance, not traversal order
- Complete expected database states are content-addressed JSON files; browser and Java replay verify SHA-256 and compare every table and row after every interaction
- Numeric DISPLAY condition names preserve invalid and LOW-VALUES bytes under the disclosed EBCDIC comparison bound until source validation
- COPAUS2C fraud removal retains the AUTHFRDS audit row with AUTH_FRAUD=R through duplicate-insert UPDATE; it does not delete the row
- Blank submitted group becomes LOW-VALUES and differs from stored spaces; post-commit resubmission preserves this behavior, while a separate synthetic PROOFGRP account retains strict no-change/no-error/no-write assertions
- Visible terminal nulls project to blank cells; reference case artifacts retain exact symbolic-output hex and first-byte null selection
- Positive update inputs explicitly use synthetic SSN 123-45-6789, OR/97001 and phone 2 (206)555-0102; original public fixture bytes and invalid cases remain preserved
- COACTUPC account rewrite omits ZIP, preserved as source behavior
- COMEN01 invalid option emits an error then faults on a table subscript; compare the emitted frame and database, discard that session, and make no continuation claim
- BMS external constants use private symbolic bytes, not a native 3270 wire encoding
- CSUTLDTC executes from pinned source; its CEEDAYS port models documented Gregorian YYYYMMDD feedback and Lilian epoch; native LE execution remains absent
- SEND TEXT terminal responses have no BMS fields; complete text and ended state are compared
- Menu options 3-10 route to one not-in-this-slice endpoint; those destination services and their screens are excluded, and boundary interactions are counted separately

Out of scope:
- other fifteen maps and their services
- native CICS, IMS and DB2 execution
- production unloads or production data
- release or z/OS acceptance
- real signatures, import, activation or Phase 2

Prepared as an unsigned Factory review request for Howard. No signature, import, activation or Phase 2 authority.

JSON SHA-256: 958741da798d0e30e1527afbd88236f3a999dc6fe5952f00e925092f1ce09cc4
