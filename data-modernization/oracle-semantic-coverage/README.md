# Oracle Semantic Coverage Program

MS #50 replaces a small-fixture headline with an architect-facing, evidence-levelled coverage
contract. The catalog contains 500 behavior contracts and 2,000 case specifications across ten
Oracle domains. Oracle Database 19c is the installed-base baseline and Oracle AI Database 26ai is
the current long-term-release delta. The pinned Sample Schemas v23.3 remain source examples; their
release identifier is not treated as the database compatibility target.

The coverage matrix deliberately separates four different counts:

- **Catalogued:** 500 behaviors and 2,000 specified cases.
- **Bounded-model verified:** eight behaviors and 24 cases inherited from MS #49.
- **Native Oracle verified:** zero until an authorized Oracle execution receipt exists.
- **Target equivalent:** zero until source-versus-target comparisons pass.

Catalogued does not mean supported. A specified case is not an executed test, bounded-model evidence
is not native Oracle evidence, and native Oracle evidence alone does not prove migration equivalence.

```bash
PYTHONPATH=src python3 -m lightyear_data build-oracle-semantic-coverage
PYTHONPATH=src python3 -m lightyear_data verify-oracle-semantic-coverage
./data-modernization.sh oracle-coverage
```

The next MS #50 increments implement the core SQL/type cases, PL/SQL cases, transaction/CDC cases,
and then native Oracle 19c/26ai execution receipts. iDempiere Control Tower projection follows only
after the coverage program can state which Oracle behaviors are catalogued, executed, verified,
equivalent, unsupported, or deferred.
