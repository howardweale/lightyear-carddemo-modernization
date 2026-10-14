# Nineteen low-diversity fields — October 12

Seven proposed constants need Howard’s decision. Twelve fields need variation. No policy exception is applied automatically. New variants are engineering inputs; only the fresh compiled campaign can establish output diversity.

| Program | Field | Classification | Reason |
|---|---|---|---|
| INTCALC | `ACCTFILE:ACCOUNT-RECORD.ACCT-ACTIVE-STATUS` | needs-variation | Input field is carried into the account/posted/rejected record; the corpus supplied only one value. Vary the input while preserving record widths and valid keys. |
| INTCALC | `TRANSACT:TRAN-RECORD.TRAN-CAT-CD` | constant-by-design | CBACT04C.cbl:483 unconditionally assigns MOVE '05' for each generated interest transaction. |
| INTCALC | `TRANSACT:TRAN-RECORD.TRAN-MERCHANT-CITY` | constant-by-design | CBACT04C.cbl:493 unconditionally assigns MOVE SPACES for each generated interest transaction. |
| INTCALC | `TRANSACT:TRAN-RECORD.TRAN-MERCHANT-ID` | constant-by-design | CBACT04C.cbl:491 unconditionally assigns MOVE 0 for each generated interest transaction. |
| INTCALC | `TRANSACT:TRAN-RECORD.TRAN-MERCHANT-NAME` | constant-by-design | CBACT04C.cbl:492 unconditionally assigns MOVE SPACES for each generated interest transaction. |
| INTCALC | `TRANSACT:TRAN-RECORD.TRAN-MERCHANT-ZIP` | constant-by-design | CBACT04C.cbl:494 unconditionally assigns MOVE SPACES for each generated interest transaction. |
| INTCALC | `TRANSACT:TRAN-RECORD.TRAN-ORIG-TS` | needs-variation | Explicit runtime clock, derived from CURRENT-DATE; vary the admitted whole-second clock. |
| INTCALC | `TRANSACT:TRAN-RECORD.TRAN-PROC-TS` | needs-variation | Explicit runtime clock, derived from CURRENT-DATE; vary the admitted whole-second clock. |
| INTCALC | `TRANSACT:TRAN-RECORD.TRAN-SOURCE` | constant-by-design | CBACT04C.cbl:484 unconditionally assigns MOVE 'System' for each generated interest transaction. |
| INTCALC | `TRANSACT:TRAN-RECORD.TRAN-TYPE-CD` | constant-by-design | CBACT04C.cbl:482 unconditionally assigns MOVE '01' for each generated interest transaction. |
| POSTTRAN | `ACCTFILE:ACCOUNT-RECORD.ACCT-ACTIVE-STATUS` | needs-variation | Input field is carried into the account/posted/rejected record; the corpus supplied only one value. Vary the input while preserving record widths and valid keys. |
| POSTTRAN | `ACCTFILE:ACCOUNT-RECORD.ACCT-GROUP-ID` | needs-variation | Input field is carried into the account/posted/rejected record; the corpus supplied only one value. Vary the input while preserving record widths and valid keys. |
| POSTTRAN | `DALYREJS:REJECT-RECORD.DALYTRAN-RECORD.DALYTRAN-CAT-CD` | needs-variation | Input field is carried into the account/posted/rejected record; the corpus supplied only one value. Vary the input while preserving record widths and valid keys. |
| POSTTRAN | `DALYREJS:REJECT-RECORD.DALYTRAN-RECORD.DALYTRAN-MERCHANT-ID` | needs-variation | Input field is carried into the account/posted/rejected record; the corpus supplied only one value. Vary the input while preserving record widths and valid keys. |
| POSTTRAN | `DALYREJS:REJECT-RECORD.DALYTRAN-RECORD.DALYTRAN-PROC-TS` | needs-variation | Input field is carried into the account/posted/rejected record; the corpus supplied only one value. Vary the input while preserving record widths and valid keys. |
| POSTTRAN | `DALYREJS:REJECT-RECORD.DALYTRAN-RECORD.DALYTRAN-SOURCE` | needs-variation | Input field is carried into the account/posted/rejected record; the corpus supplied only one value. Vary the input while preserving record widths and valid keys. |
| POSTTRAN | `DALYREJS:REJECT-RECORD.DALYTRAN-RECORD.DALYTRAN-TYPE-CD` | needs-variation | Input field is carried into the account/posted/rejected record; the corpus supplied only one value. Vary the input while preserving record widths and valid keys. |
| POSTTRAN | `TRANFILE:TRAN-RECORD.TRAN-MERCHANT-ID` | needs-variation | Input field is carried into the account/posted/rejected record; the corpus supplied only one value. Vary the input while preserving record widths and valid keys. |
| POSTTRAN | `TRANFILE:TRAN-RECORD.TRAN-PROC-TS` | needs-variation | Explicit runtime clock, derived from CURRENT-DATE; vary the admitted whole-second clock. |
