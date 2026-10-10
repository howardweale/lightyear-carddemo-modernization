# Factory 2.1: executable public CardDemo twin

This PR adds an engineering-only GnuCOBOL build and run path for the pinned
Apache-2.0 CBACT04C (INTCALC) and CBTRN02C (POSTTRAN) programs. Original COBOL
and copybook bytes are verified against the existing CardDemo bindings at commit
`59cc6c2fd7ebd7ef7925cad552a01a4b8b6e4d5e`, then compiled without business edits.
CICS programs, JES/JCL orchestration, native VSAM semantics, Db2 and z/OS runtime
services remain outside this twin. No historical B06 evidence is changed.

## Reproduction

Use Ubuntu 24.04 (GitHub Actions or an Ubuntu Multipass VM), not Windows Docker.
Install `gnucobol3=3.1.2-5.1ubuntu1` and `libfaketime=0.9.10-2.1`; Python 3.11 or later requires no extra packages.
Run with `PYTHONPATH=src:.`:

```sh
python -B -m unittest discover -s tests -p test_legacy_twin.py -v
python -B -m tools.check_legacy_twin work/factory-twin-new
```

Output directories must not exist. The command builds both programs twice in
separate clean directories and requires identical executable hashes, then runs
both public INTCALC rehearsals, the discriminating and missing-disclosure cases,
and the public POSTTRAN rehearsal. GitHub workflow `Factory legacy twin` runs
these checks without containers, models, customer data or a native B06 window.

## Adaptation boundary

Compilation uses fixed-format originals, IBM dialect, EBCDIC zoned-display signs
and optimization `-O2`. Generated free-format adapters load/dump actual GnuCOBOL
indexed files with each original program's primary and alternate keys. Strict
existing copybook decoding converts pinned public cp037 fixtures to ASCII display
records; sequential files retain fixed record widths without line delimiters.
No Python business logic executes inside the twin. INTCALC receives its original
length-prefixed linkage parameter through a wrapper. `CEE3ABD` is an explicit
RC12 stop shim, not an emulation of Language Environment abends. `COB_CURRENT_DATE`
fixes the fixture clock; acceptance checks the generated timestamp.

Build receipts bind compiler/runtime identification, package version, flags,
original source hashes, generated adapter hashes and executable hashes. Run
receipts bind the build receipt, all input/output hashes, return code and clock.
Logs and partial outputs survive failures. An `engineering.json` marker is written
before compilation/execution, so the existing evidence boundary also refuses raw
child artifacts even if their receipt is omitted. Receipts are digest sealed, **unsigned**,
and tagged `engineering` / `executable-twin`; they do not authenticate a z/OS
observation or grant qualification/measurement credit. Record comparison and
three-way adjudication are separate workstream 2.2; running is not equivalence.

## Validation and remaining limits

Hosted acceptance is required before this milestone is considered executed.
The CI artifact retains both builds and each run, including negative-case logs.
POSTTRAN permits source return code 4 for rejected input; this is not a failed
compiler or a silently accepted equivalence result. Synthetic POSTTRAN after-images
contain a deliberately planted decoding-rehearsal reject, not a native expected
answer, and are never asserted as twin truth. GnuCOBOL/compiler platform differences
remain unresolved until separately probed. No default oracle is changed.

The next milestone compares twin, Python and Java field by field and records every
disagreement. Coverage instrumentation and thresholds follow that reconciliation.
Merge requires Howard's approval of the exact commit.

Sources: [Ubuntu noble package](https://packages.ubuntu.com/noble/gnucobol3),
[GnuCOBOL manual](https://gnucobol.sourceforge.io/doc/gnucobol.html), and existing
`spec/mainframe/public-source/README.md` / copybook LICENSE and NOTICE.

## Source boundary and VM status

The pinned upstream Git tree is `a1253e31c839f78d1f185b01771ba956da63b005`.
Original source provenance and Apache-2.0 license hashes appear in build receipts.
The primary `app/cbl` online program inventory is excluded: COACTUPC, COACTVWC,
COADM01C, COBIL00C, COBSWAIT, COCRDLIC, COCRDSLC, COCRDUPC, COMEN01C, CORPT00C,
COSGN00C, COTRN00C, COTRN01C, COTRN02C, COUSR00C, COUSR01C, COUSR02C and COUSR03C.
The optional IMS/Db2/MQ and transaction-type extensions are excluded too.
Proposed later record harness: extract a reviewed business paragraph behind a
COMMAREA-shaped fixed-record input/output adapter, with explicit CICS READ/WRITE
and response-code stubs; assert map/screen/terminal statements are unreachable.
Until independently reviewed against original execution, that extracted harness
would be a reference model, not a confirmed executable twin.

Multipass is not installed at the checked local paths. No VM run is claimed and
no machine software was installed. The same Ubuntu command is supplied above;
VM execution remains outstanding alongside hosted CI acceptance.

## Reproducibility finding

The first hosted build (run 38088492240) compiled both unchanged programs, then
correctly failed exact binary comparison. Preserved binaries differ in embedded
compilation timestamps. GnuCOBOL 3.1.2 does not honor `SOURCE_DATE_EPOCH` for those
timestamps (support was added in 3.2). The pinned compiler is now invoked with a
pinned, hash-recorded libfaketime adapter for **compiler subprocesses only**,
fixing metadata time at 2022-07-18 UTC. Application execution and timeout clocks
do not inherit the preload. No binary bytes or checks are edited after compilation.
Both clean builds must still match exactly. The first failed artifact is preserved.
See [GnuCOBOL release notes](https://sourceforge.net/projects/gnucobol/files/gnucobol/)
and [libfaketime scope documentation](https://github.com/wolfcw/libfaketime).

The compiler-clock run 38089237223 removed all timestamp differences; the only
remaining differing bytes were the linker's 20-byte GNU build ID (offsets 888–907
in each ELF binary). Linking now explicitly uses `--build-id=none`, recorded in
flags. Binary comparison still covers every byte, with no post-build stripping
or normalization by this driver.

The first real scenario executions also exposed a clock-adapter defect:
`COB_CURRENT_DATE` without a fractional part leaves live nanoseconds in 3.1.2.
Both INTCALC transaction timestamps consequently differed from Python/Java;
all other compared output fields matched. The adapter now supplies an explicit
nine-digit zero fraction. Outputs/fixtures are not rewritten and the exact
transaction-timestamp assertion remains required. Original mismatch artifacts
are retained under hosted run 38088862638.
