# GnuCOBOL twin limits and promotion register

This register applies to the public pinned CardDemo engineering twin. It is not
an authorised z/OS baseline. Every new build/run receipt binds this file's SHA-256
and path. Tower review must inspect that bound register alongside the receipt;
no existing Tower deployment, signed evidence or historical receipt is rewritten.

| Adapter/emulation | z/OS behavior represented | Status and boundary |
|---|---|---|
| Indexed-file load/dump bridge | VSAM keyed READ/WRITE/REWRITE and ordered access | Unknown equivalence. GnuCOBOL uses its native indexed backend, not VSAM. Observed 00/10/22/23/35 codes are engineering probes only; locking, concurrent update, recovery and extended VSAM statuses remain unknown. |
| CEE3ABD shim | LE abnormal termination | Known different: prints a code and exits RC12; does not implement LE condition handling, dump or abend propagation. |
| INTCALC parameter wrapper | JCL PARM with binary length and ten-byte date | Public source layout confirmed; runtime calling-convention equivalence unknown. Missing/malformed processing dates now refuse. POSTTRAN explicitly does not use this parameter. |
| ASCII fixed-record conversion | EBCDIC copybook data | Known different character representation. Zoned numeric signs preserve declared encoding; alphanumeric collation differs. No binary equivalence claim across platforms. |
| Runtime clock | CURRENT-DATE / generated TRAN-PROC-TS | GnuCOBOL COB_CURRENT_DATE is pinned and output is probed. z/OS timezone/precision behavior unconfirmed. Compiler-only libfaketime pins embedded compile timestamps and never changes the machine clock. |
| File-status mapping | Enterprise COBOL/VSAM result codes | Happy, missing, duplicate and EOF paths probed; not a complete z/OS status mapping. Unexpected codes remain failures. |
| Program collating sequence experiment | EBCDIC alphanumeric comparisons and SORT/MERGE | Native ASCII A-before-a is **known-different-from-zos**. Separate generated probe evaluates PROGRAM COLLATING SEQUENCE EBCDIC on 3.1.2; does not rewrite pinned originals. Indexed-file key order must be reported independently. |
| Java comparison harness | Deployed candidate service | Pure calculation uses a documented inert annotation stub; a separate real Spring Boot application-context test exercises the injected service and batch-job wiring. No POSTTRAN Java candidate is present. |

## Collation scope

The public source inventory here contains five programs: CBACT04C, CBTRN02C,
CBTRN03C, CBSTM03A and CBSTM03B. All compare character flags/file statuses or keys.
CBACT04C performs disclosure-key equality and indexed iteration; CBTRN02C compares
expiry and transaction dates at line 414 and uses indexed account/category keys;
CBTRN03C compares report date ranges; CBSTM03A compares card keys and dispatch/DD
names; CBSTM03B dispatches DD and operation names. Equality of consistently
transcoded characters is order-insensitive. Mixed letter/digit indexed iteration,
relational comparisons and external JCL SORT can differ. This is the bounded
pinned inventory, not a claim to inventory every upstream online program.

The probe records ordinary comparison, SORT, MERGE and indexed READ NEXT order
under both native and explicit EBCDIC program collation. Program collation alone
must not be treated as fixing native indexed backend order. Keeping all EBCDIC
bytes end-to-end would also require compatible numeric/display runtime semantics
and adapters; it is not enabled by -fsign=EBCDIC. No source translation is made.
[GnuCOBOL 3.1 quick reference](https://gnucobol.sourceforge.io/HTML/gnucobqr.html)
and [programmer guide](https://gnucobol.sourceforge.io/HTML/gnucobpg.html) describe
these separate mechanisms; CI results establish this pinned build's behavior.

## POSTTRAN, provisional answer key

Howard selected the executable twin, with no hand-written Python POSTTRAN oracle.
Every new receipt is `oracle_class: executable-twin`, `oracle_status: provisional`,
`zos_confirmation: false`, `releasable: false`. CICS, DB2 and IMS are out of scope.

CBTRN02C character conditions comprise END-OF-FILE='Y'/'N' (202-205), file status
00/10/23 and numeric-class checks, WS-CREATE-TRANCAT-REC='Y' (495), and the sole
relational character condition ACCT-EXPIRAION-DATE >= DALYTRAN-ORIG-TS(1:10) (414).
There is no SORT/MERGE statement in CBTRN02C. Amount/limit/counter conditions are
numeric. The diagnostic path requires valid fixed ISO dates and decimal-only
physical indexed keys. For these restricted domains ASCII/cp037 order agrees;
other domains stop before execution. This does not establish general EBCDIC
collation. Rejection codes 100/101/102/103 are tied to missing card, missing
account, over-limit, and expired account; 103 overwrites 102 in source order.
Code109 represents an unsuccessful REWRITE and cannot be justified from input
conditions alone: any such result remains unresolved, never silently accepted.

Checks independently conserve input/posted/rejected IDs, amounts, account/cycle
and category deltas, rejected input contents, posted identifiers and pinned
processing timestamps. They validate outcomes rather than generate answer files.
Two separate executions must have identical output hashes. A deterministic
public review sheet includes every observed rejection reason and posted amount
extremes. An empty decision/signature is explicitly pending, not attestation.

Promotion is blocked on missing Java second opinion, signed human review,
full scenario-engine reconciliation, and unresolved platform behavior. Any
candidate integration must invoke the same invariant checker; absent integration
is not a passing candidate. No default-to-twin disagreement resolution.

## Reproduction limits

Hosted runner performs two clean builds. Multipass was absent from PATH and the
standard installation location during this review; no VM run or binary hash
comparison is claimed. On an authorised Ubuntu24.04 amd64 VM, run the same pinned
installer and `python -B -m tools.check_legacy_twin <fresh-output>`. Compare every
`reproducible_binaries` key/digest with hosted acceptance.json; retain both host
receipts. Matching compiler packages alone do not pin linker, libc, architecture
or all transitive build inputs, so a mismatch needs investigation rather than an
assumption of compiler nondeterminism.

## Observed pinned 3.1.2 collation result

[Hosted experiment](https://github.com/howardweale/lightyear-carddemo-modernization/actions/runs/38095372644): native runtime-data and literal comparisons both A-before-a; explicit EBCDIC runtime-data comparison a-before-A, but literal comparison still A-before-a. SORT changed from0Aa to aA0; MERGE of two valid one-record inputs changed fromAa to aA. Indexed READ NEXT remained0Aa in both. Thus program collation alone is insufficient for general z/OS equivalence. [Observed results](review-304-307-observed-results.json) retain the source and artifact hashes. Original source remains unchanged.
