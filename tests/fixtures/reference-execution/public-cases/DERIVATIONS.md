# Public case set: hand derivations (Claude)

Derived from the public CBACT04C source and copybooks only. Not from the Python oracle, GnuCOBOL output, or any hidden or retired case.

Conventions: stdout is the program DISPLAY output as ASCII with LF line ends; stderr is empty; exit is 0 on normal end and 12 on CEE3ABD. Output files are cp037 fixed-length records. Two things the source leaves undetermined are written as spaces here and named as conventions, not derivations: TRAN-DESC bytes 25-100 (STRING does not clear the rest of the field) and the 20-byte TRAN-RECORD FILLER (never set). For the three abend cases no output files are derived, because what persists after CEE3ABD is not determined by the source.

## PC-01

Empty TCATBALF. Two accounts present.

Processing date 2026111400, timestamp 2026-11-14-08.30.15.120000 (written to transactions as 2026-11-14-08.30.15.120000).

- No balance records: nothing processed.

Result: exit 0; 0 transaction record(s); 2 account record(s) in key order.
- ACCT 00000000011 balance 1500.00 cycle credit 123.45 debit 67.89
- ACCT 00000000022 balance 2500.00 cycle credit 123.45 debit 67.89

## PC-02

One account, one balance 1000.00, rate 12.00 (exact result).

Processing date 2026111400, timestamp 2026-11-14-08.30.15.120000 (written to transactions as 2026-11-14-08.30.15.120000).

- 1300 acct 00000000011 cat 0001: 1000.00 * 12.00 / 1200 = 10.0000 -> WS-MONTHLY-INT 10.00; WS-TOTAL-INT 10.00; TRAN-ID suffix 000001
- End of file reached inside the loop: the ELSE branch is not entered, so the last account (00000000011) is not rewritten.

Result: exit 0; 1 transaction record(s); 1 account record(s) in key order.
- TRAN-ID 2026111400000001 amount 10.00 card 4111000000000011
- ACCT 00000000011 balance 1500.00 cycle credit 123.45 debit 67.89

## PC-03

One account, one balance 250.75, rate 21.00 (fraction discarded).

Processing date 2026111400, timestamp 2026-11-14-08.30.15.120000 (written to transactions as 2026-11-14-08.30.15.120000).

- 1300 acct 00000000011 cat 0001: 250.75 * 21.00 / 1200 = 4.388125 -> WS-MONTHLY-INT 4.38; WS-TOTAL-INT 4.38; TRAN-ID suffix 000001
- End of file reached inside the loop: the ELSE branch is not entered, so the last account (00000000011) is not rewritten.

Result: exit 0; 1 transaction record(s); 1 account record(s) in key order.
- TRAN-ID 2026111400000001 amount 4.38 card 4111000000000011
- ACCT 00000000011 balance 1500.00 cycle credit 123.45 debit 67.89

## PC-04

One account, one balance -250.75, rate 21.00 (negative, fraction discarded).

Processing date 2026111400, timestamp 2026-11-14-08.30.15.120000 (written to transactions as 2026-11-14-08.30.15.120000).

- 1300 acct 00000000011 cat 0001: -250.75 * 21.00 / 1200 = -4.388125 -> WS-MONTHLY-INT -4.38; WS-TOTAL-INT -4.38; TRAN-ID suffix 000001
- End of file reached inside the loop: the ELSE branch is not entered, so the last account (00000000011) is not rewritten.

Result: exit 0; 1 transaction record(s); 1 account record(s) in key order.
- TRAN-ID 2026111400000001 amount -4.38 card 4111000000000011
- ACCT 00000000011 balance 1500.00 cycle credit 123.45 debit 67.89

## PC-05

One account, three categories, balances 100.10, 200.20, 300.30, rates 18.00, 21.00, 24.99.

Processing date 2026111400, timestamp 2026-11-14-08.30.15.120000 (written to transactions as 2026-11-14-08.30.15.120000).

- 1300 acct 00000000011 cat 0001: 100.10 * 18.00 / 1200 = 1.5015 -> WS-MONTHLY-INT 1.50; WS-TOTAL-INT 1.50; TRAN-ID suffix 000001
- 1300 acct 00000000011 cat 0002: 200.20 * 21.00 / 1200 = 3.5035 -> WS-MONTHLY-INT 3.50; WS-TOTAL-INT 5.00; TRAN-ID suffix 000002
- 1300 acct 00000000011 cat 0003: 300.30 * 24.99 / 1200 = 6.2537475 -> WS-MONTHLY-INT 6.25; WS-TOTAL-INT 11.25; TRAN-ID suffix 000003
- End of file reached inside the loop: the ELSE branch is not entered, so the last account (00000000011) is not rewritten.

Result: exit 0; 3 transaction record(s); 1 account record(s) in key order.
- TRAN-ID 2026111400000001 amount 1.50 card 4111000000000011
- TRAN-ID 2026111400000002 amount 3.50 card 4111000000000011
- TRAN-ID 2026111400000003 amount 6.25 card 4111000000000011
- ACCT 00000000011 balance 1500.00 cycle credit 123.45 debit 67.89

## PC-06

Two accounts, two categories each, mixed positive balances and rates.

Processing date 2026111400, timestamp 2026-11-14-08.30.15.120000 (written to transactions as 2026-11-14-08.30.15.120000).

- 1300 acct 00000000011 cat 0001: 1234.56 * 19.99 / 1200 = 20.565712 -> WS-MONTHLY-INT 20.56; WS-TOTAL-INT 20.56; TRAN-ID suffix 000001
- 1300 acct 00000000011 cat 0002: 987.65 * 7.25 / 1200 = 5.967052083333333333333333333 -> WS-MONTHLY-INT 5.96; WS-TOTAL-INT 26.52; TRAN-ID suffix 000002
- 1050-UPDATE-ACCOUNT 00000000011: ACCT-CURR-BAL 1500.00 + WS-TOTAL-INT 26.52 = 1526.52; cycle credit and debit set to 0
- 1300 acct 00000000022 cat 0001: 4321.09 * 19.99 / 1200 = 71.98215758333333333333333333 -> WS-MONTHLY-INT 71.98; WS-TOTAL-INT 71.98; TRAN-ID suffix 000003
- 1300 acct 00000000022 cat 0002: 0.07 * 7.25 / 1200 = 0.0004229166666666666666666666667 -> WS-MONTHLY-INT 0.00; WS-TOTAL-INT 71.98; TRAN-ID suffix 000004
- End of file reached inside the loop: the ELSE branch is not entered, so the last account (00000000022) is not rewritten.

Result: exit 0; 4 transaction record(s); 2 account record(s) in key order.
- TRAN-ID 2026111400000001 amount 20.56 card 4111000000000011
- TRAN-ID 2026111400000002 amount 5.96 card 4111000000000011
- TRAN-ID 2026111400000003 amount 71.98 card 4111000000000022
- TRAN-ID 2026111400000004 amount 0.00 card 4111000000000022
- ACCT 00000000011 balance 1526.52 cycle credit 0.00 debit 0.00
- ACCT 00000000022 balance 2500.00 cycle credit 123.45 debit 67.89

## PC-07

Three accounts; the middle account's only category has rate 0.00.

Processing date 2026111400, timestamp 2026-11-14-08.30.15.120000 (written to transactions as 2026-11-14-08.30.15.120000).

- 1300 acct 00000000011 cat 0001: 600.00 * 15.00 / 1200 = 7.5000 -> WS-MONTHLY-INT 7.50; WS-TOTAL-INT 7.50; TRAN-ID suffix 000001
- 1050-UPDATE-ACCOUNT 00000000011: ACCT-CURR-BAL 1500.00 + WS-TOTAL-INT 7.50 = 1507.50; cycle credit and debit set to 0
- acct 00000000022 cat 0002: DIS-INT-RATE = 0, no transaction
- 1050-UPDATE-ACCOUNT 00000000022: ACCT-CURR-BAL 2500.00 + WS-TOTAL-INT 0 = 2500.00; cycle credit and debit set to 0
- 1300 acct 00000000033 cat 0001: 800.00 * 15.00 / 1200 = 10.0000 -> WS-MONTHLY-INT 10.00; WS-TOTAL-INT 10.00; TRAN-ID suffix 000002
- End of file reached inside the loop: the ELSE branch is not entered, so the last account (00000000033) is not rewritten.

Result: exit 0; 2 transaction record(s); 3 account record(s) in key order.
- TRAN-ID 2026111400000001 amount 7.50 card 4111000000000011
- TRAN-ID 2026111400000002 amount 10.00 card 4111000000000033
- ACCT 00000000011 balance 1507.50 cycle credit 0.00 debit 0.00
- ACCT 00000000022 balance 2500.00 cycle credit 0.00 debit 0.00
- ACCT 00000000033 balance 3500.00 cycle credit 123.45 debit 67.89

## PC-08

Three accounts; every rate 0.00.

Processing date 2026111400, timestamp 2026-11-14-08.30.15.120000 (written to transactions as 2026-11-14-08.30.15.120000).

- acct 00000000011 cat 0001: DIS-INT-RATE = 0, no transaction
- 1050-UPDATE-ACCOUNT 00000000011: ACCT-CURR-BAL 1500.00 + WS-TOTAL-INT 0 = 1500.00; cycle credit and debit set to 0
- acct 00000000022 cat 0001: DIS-INT-RATE = 0, no transaction
- 1050-UPDATE-ACCOUNT 00000000022: ACCT-CURR-BAL 2500.00 + WS-TOTAL-INT 0 = 2500.00; cycle credit and debit set to 0
- acct 00000000033 cat 0001: DIS-INT-RATE = 0, no transaction
- End of file reached inside the loop: the ELSE branch is not entered, so the last account (00000000033) is not rewritten.

Result: exit 0; 0 transaction record(s); 3 account record(s) in key order.
- ACCT 00000000011 balance 1500.00 cycle credit 0.00 debit 0.00
- ACCT 00000000022 balance 2500.00 cycle credit 0.00 debit 0.00
- ACCT 00000000033 balance 3500.00 cycle credit 123.45 debit 67.89

## PC-09

Two accounts; first account's group SILVER has no DISCGRP row, DEFAULT row exists.

Processing date 2026111400, timestamp 2026-11-14-08.30.15.120000 (written to transactions as 2026-11-14-08.30.15.120000).

- 1300 acct 00000000011 cat 0001: 400.00 * 24.00 / 1200 = 8.0000 -> WS-MONTHLY-INT 8.00; WS-TOTAL-INT 8.00; TRAN-ID suffix 000001
- 1050-UPDATE-ACCOUNT 00000000011: ACCT-CURR-BAL 1500.00 + WS-TOTAL-INT 8.00 = 1508.00; cycle credit and debit set to 0
- 1300 acct 00000000022 cat 0001: 500.00 * 18.00 / 1200 = 7.5000 -> WS-MONTHLY-INT 7.50; WS-TOTAL-INT 7.50; TRAN-ID suffix 000002
- End of file reached inside the loop: the ELSE branch is not entered, so the last account (00000000022) is not rewritten.

Result: exit 0; 2 transaction record(s); 2 account record(s) in key order.
- TRAN-ID 2026111400000001 amount 8.00 card 4111000000000011
- TRAN-ID 2026111400000002 amount 7.50 card 4111000000000022
- ACCT 00000000011 balance 1508.00 cycle credit 0.00 debit 0.00
- ACCT 00000000022 balance 2500.00 cycle credit 123.45 debit 67.89

## PC-10

As PC-09 but no DEFAULT row either.

Processing date 2026111400, timestamp 2026-11-14-08.30.15.120000 (written to transactions as 2026-11-14-08.30.15.120000).


Result: exit 12 (abend). Last stdout lines: TRY WITH DEFAULT GROUP CODE / ERROR READING DEFAULT DISCLOSURE GROUP / FILE STATUS IS: NNNN0023 / ABENDING PROGRAM

## PC-11

TCATBALF references an account id absent from ACCTFILE (second of two accounts).

Processing date 2026111400, timestamp 2026-11-14-08.30.15.120000 (written to transactions as 2026-11-14-08.30.15.120000).

- 1300 acct 00000000011 cat 0001: 400.00 * 18.00 / 1200 = 6.0000 -> WS-MONTHLY-INT 6.00; WS-TOTAL-INT 6.00; TRAN-ID suffix 000001
- 1050-UPDATE-ACCOUNT 00000000011: ACCT-CURR-BAL 1500.00 + WS-TOTAL-INT 6.00 = 1506.00; cycle credit and debit set to 0

Result: exit 12 (abend). Last stdout lines: ACCOUNT NOT FOUND: 00000000022 / ERROR READING ACCOUNT FILE / FILE STATUS IS: NNNN0023 / ABENDING PROGRAM

## PC-12

TCATBALF references an account present in ACCTFILE but absent from XREFFILE.

Processing date 2026111400, timestamp 2026-11-14-08.30.15.120000 (written to transactions as 2026-11-14-08.30.15.120000).


Result: exit 12 (abend). Last stdout lines: ACCOUNT NOT FOUND: 00000000011 / ERROR READING XREF FILE / FILE STATUS IS: NNNN0023 / ABENDING PROGRAM

## PC-13

One account, balance 999999999.99, rate 9999.99.

Processing date 2026111400, timestamp 2026-11-14-08.30.15.120000 (written to transactions as 2026-11-14-08.30.15.120000).

- 1300 acct 00000000011 cat 0001: 999999999.99 * 9999.99 / 1200 = 8333324999.91666675 -> WS-MONTHLY-INT 333324999.91; WS-TOTAL-INT 333324999.91; TRAN-ID suffix 000001
- End of file reached inside the loop: the ELSE branch is not entered, so the last account (00000000011) is not rewritten.

Result: exit 0; 1 transaction record(s); 1 account record(s) in key order.
- TRAN-ID 2026111400000001 amount 333324999.91 card 4111000000000011
- ACCT 00000000011 balance 1500.00 cycle credit 123.45 debit 67.89

## PC-14

Four accounts, twelve balance rows in total, all non-zero rates (suffix sequence).

Processing date 2026111400, timestamp 2026-11-14-23.59.59.987654 (written to transactions as 2026-11-14-23.59.59.980000).

- 1300 acct 00000000011 cat 0001: 101.01 * 12.50 / 1200 = 1.0521875 -> WS-MONTHLY-INT 1.05; WS-TOTAL-INT 1.05; TRAN-ID suffix 000001
- 1300 acct 00000000011 cat 0002: 202.02 * 17.75 / 1200 = 2.9882125 -> WS-MONTHLY-INT 2.98; WS-TOTAL-INT 4.03; TRAN-ID suffix 000002
- 1300 acct 00000000011 cat 0003: 303.03 * 22.25 / 1200 = 5.61868125 -> WS-MONTHLY-INT 5.61; WS-TOTAL-INT 9.64; TRAN-ID suffix 000003
- 1050-UPDATE-ACCOUNT 00000000011: ACCT-CURR-BAL 1500.00 + WS-TOTAL-INT 9.64 = 1509.64; cycle credit and debit set to 0
- 1300 acct 00000000022 cat 0001: 404.04 * 12.50 / 1200 = 4.20875 -> WS-MONTHLY-INT 4.20; WS-TOTAL-INT 4.20; TRAN-ID suffix 000004
- 1300 acct 00000000022 cat 0002: 505.05 * 17.75 / 1200 = 7.47053125 -> WS-MONTHLY-INT 7.47; WS-TOTAL-INT 11.67; TRAN-ID suffix 000005
- 1300 acct 00000000022 cat 0003: 606.06 * 22.25 / 1200 = 11.2373625 -> WS-MONTHLY-INT 11.23; WS-TOTAL-INT 22.90; TRAN-ID suffix 000006
- 1050-UPDATE-ACCOUNT 00000000022: ACCT-CURR-BAL 2500.00 + WS-TOTAL-INT 22.90 = 2522.90; cycle credit and debit set to 0
- 1300 acct 00000000033 cat 0001: 707.07 * 12.50 / 1200 = 7.3653125 -> WS-MONTHLY-INT 7.36; WS-TOTAL-INT 7.36; TRAN-ID suffix 000007
- 1300 acct 00000000033 cat 0002: 808.08 * 17.75 / 1200 = 11.95285 -> WS-MONTHLY-INT 11.95; WS-TOTAL-INT 19.31; TRAN-ID suffix 000008
- 1300 acct 00000000033 cat 0003: 909.09 * 22.25 / 1200 = 16.85604375 -> WS-MONTHLY-INT 16.85; WS-TOTAL-INT 36.16; TRAN-ID suffix 000009
- 1050-UPDATE-ACCOUNT 00000000033: ACCT-CURR-BAL 3500.00 + WS-TOTAL-INT 36.16 = 3536.16; cycle credit and debit set to 0
- 1300 acct 00000000044 cat 0001: 1010.10 * 12.50 / 1200 = 10.521875 -> WS-MONTHLY-INT 10.52; WS-TOTAL-INT 10.52; TRAN-ID suffix 000010
- 1300 acct 00000000044 cat 0002: 1111.11 * 17.75 / 1200 = 16.43516875 -> WS-MONTHLY-INT 16.43; WS-TOTAL-INT 26.95; TRAN-ID suffix 000011
- 1300 acct 00000000044 cat 0003: 1212.12 * 22.25 / 1200 = 22.474725 -> WS-MONTHLY-INT 22.47; WS-TOTAL-INT 49.42; TRAN-ID suffix 000012
- End of file reached inside the loop: the ELSE branch is not entered, so the last account (00000000044) is not rewritten.

Result: exit 0; 12 transaction record(s); 4 account record(s) in key order.
- TRAN-ID 2026111400000001 amount 1.05 card 4111000000000011
- TRAN-ID 2026111400000002 amount 2.98 card 4111000000000011
- TRAN-ID 2026111400000003 amount 5.61 card 4111000000000011
- TRAN-ID 2026111400000004 amount 4.20 card 4111000000000022
- TRAN-ID 2026111400000005 amount 7.47 card 4111000000000022
- TRAN-ID 2026111400000006 amount 11.23 card 4111000000000022
- TRAN-ID 2026111400000007 amount 7.36 card 4111000000000033
- TRAN-ID 2026111400000008 amount 11.95 card 4111000000000033
- TRAN-ID 2026111400000009 amount 16.85 card 4111000000000033
- TRAN-ID 2026111400000010 amount 10.52 card 4111000000000044
- TRAN-ID 2026111400000011 amount 16.43 card 4111000000000044
- TRAN-ID 2026111400000012 amount 22.47 card 4111000000000044
- ACCT 00000000011 balance 1509.64 cycle credit 0.00 debit 0.00
- ACCT 00000000022 balance 2522.90 cycle credit 0.00 debit 0.00
- ACCT 00000000033 balance 3536.16 cycle credit 0.00 debit 0.00
- ACCT 00000000044 balance 4500.00 cycle credit 123.45 debit 67.89

## PC-15

Two accounts; ACCT-CURR-BAL negative on the first, interest positive.

Processing date 2026111400, timestamp 2026-11-14-08.30.15.120000 (written to transactions as 2026-11-14-08.30.15.120000).

- 1300 acct 00000000011 cat 0001: 740.40 * 20.00 / 1200 = 12.3400 -> WS-MONTHLY-INT 12.34; WS-TOTAL-INT 12.34; TRAN-ID suffix 000001
- 1050-UPDATE-ACCOUNT 00000000011: ACCT-CURR-BAL -500.00 + WS-TOTAL-INT 12.34 = -487.66; cycle credit and debit set to 0
- 1300 acct 00000000022 cat 0001: 500.00 * 20.00 / 1200 = 8.333333333333333333333333333 -> WS-MONTHLY-INT 8.33; WS-TOTAL-INT 8.33; TRAN-ID suffix 000002
- End of file reached inside the loop: the ELSE branch is not entered, so the last account (00000000022) is not rewritten.

Result: exit 0; 2 transaction record(s); 2 account record(s) in key order.
- TRAN-ID 2026111400000001 amount 12.34 card 4111000000000011
- TRAN-ID 2026111400000002 amount 8.33 card 4111000000000022
- ACCT 00000000011 balance -487.66 cycle credit 0.00 debit 0.00
- ACCT 00000000022 balance 2500.00 cycle credit 123.45 debit 67.89

## PC-16

Two accounts, TCATBALF.bin rows supplied in descending key order.

Processing date 2026111400, timestamp 2026-11-14-08.30.15.120000 (written to transactions as 2026-11-14-08.30.15.120000).

- 1300 acct 00000000011 cat 0001: 50.00 * 12.00 / 1200 = 0.5000 -> WS-MONTHLY-INT 0.50; WS-TOTAL-INT 0.50; TRAN-ID suffix 000001
- 1300 acct 00000000011 cat 0002: 150.00 * 24.00 / 1200 = 3.0000 -> WS-MONTHLY-INT 3.00; WS-TOTAL-INT 3.50; TRAN-ID suffix 000002
- 1050-UPDATE-ACCOUNT 00000000011: ACCT-CURR-BAL 1500.00 + WS-TOTAL-INT 3.50 = 1503.50; cycle credit and debit set to 0
- 1300 acct 00000000022 cat 0001: 250.00 * 12.00 / 1200 = 2.5000 -> WS-MONTHLY-INT 2.50; WS-TOTAL-INT 2.50; TRAN-ID suffix 000003
- 1300 acct 00000000022 cat 0002: 350.00 * 24.00 / 1200 = 7.0000 -> WS-MONTHLY-INT 7.00; WS-TOTAL-INT 9.50; TRAN-ID suffix 000004
- End of file reached inside the loop: the ELSE branch is not entered, so the last account (00000000022) is not rewritten.

Result: exit 0; 4 transaction record(s); 2 account record(s) in key order.
- TRAN-ID 2026111400000001 amount 0.50 card 4111000000000011
- TRAN-ID 2026111400000002 amount 3.00 card 4111000000000011
- TRAN-ID 2026111400000003 amount 2.50 card 4111000000000022
- TRAN-ID 2026111400000004 amount 7.00 card 4111000000000022
- ACCT 00000000011 balance 1503.50 cycle credit 0.00 debit 0.00
- ACCT 00000000022 balance 2500.00 cycle credit 123.45 debit 67.89

