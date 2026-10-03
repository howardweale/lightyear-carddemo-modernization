# Pinned public EBCDIC/ASCII fixture disagreements

Commit: `59cc6c2fd7ebd7ef7925cad552a01a4b8b6e4d5e` in the public AWS CardDemo
repository. These are public synthetic fixtures, not Maintec records.

`bridge-self-test` verifies the checked-in fixture provenance hashes, decodes with
the strict copybooks, and proves an exact byte round trip back to EBCDIC. The bridge
keeps every source field and adds LF record separators for Java's `DatasetIo`.
It does not substitute the public ASCII fixture's values.

| Dataset | Difference in the same pinned source pair | Treatment |
| --- | --- | --- |
| TCATBALF | ASCII has CRLF delimiters except its final LF; EBCDIC is contiguous fixed records | Normalize record separators only for the self-test |
| CARDXREF | Each ASCII record omits its 14 trailing filler blanks | Pad only the expected public ASCII fixture in the self-test; the bridge retains the source's blanks |
| ACCTDATA | Record 49, `ACCOUNT-RECORD.ACCT-ADDR-ZIP`, differs substantively | Documented source-pair disagreement; no bridge correction |
| DISCGRP | Record 34, `DIS-GROUP-RECORD.DIS-INT-RATE`, differs substantively | Documented source-pair disagreement; no bridge correction |

The last two differences cannot be explained by line framing or code-page
conversion. They are discrepancies in the public input pair itself. The self-test
requires precisely those record/field differences against byte-hash-pinned files;
any additional difference fails. It reports `passed-with-documented-public-fixture-exceptions`,
not byte-identical ASCII fixtures. This exception list is **never used** to modify
Maintec data or normalize a Java-versus-z/OS verdict.

Source hashes, generated fixture hashes and the synthetic after-image recipe are
in [fixture provenance](../../tests/mainframe/fixtures/PROVENANCE.json). Rebuild
only from public Git blobs using `tools/build_zos_rehearsal.py`; do not use this
generator with a delivery. The local Python reference generates the fake
after-images. The two INTCALC runs then differ only in `TRAN-PROC-TS`.
