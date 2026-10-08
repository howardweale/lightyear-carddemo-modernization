# Coverage-v2 native qualification

October 7, 2026 PDT (October 8 UTC). Operator review; not independent attestation.
Zero model calls. Native execution used only the approved dedicated Linux VM.

**Nine of nine collector controls passed**, with independent offline replay on
Linux and Windows. The controls cover straight-line statements, both branch
edges, a missing edge, a hit and a missing error handler, scalar and table
declarations, a non-`dbo` schema, and exclusion of views from procedural parsing.
Negative controls passed by remaining coverage-ineligible. These are collector
controls, not nine business-equivalence successes. The handler-hit pair's
divergent business verdict is preserved and is not its instrumentation verdict.

The nine-control run took 37.521 seconds; Linux offline replay took 0.111 seconds
plus 0.107 seconds for control acceptance. Owned-label container, network and
volume queries confirmed absence for successful attempt 004 and failed attempts
002 and 003. Preparation total monotonic duration was not measured.

A separate fresh six-pair consumption check bound this exact qualification,
collector, bridge, image digests and schemas. The correct integer-division cases
and ordered-result twin were equivalent (3); all corresponding wrong cases were
divergent (3). All six pairs replayed independently on Linux and Windows. Native
execution and cleanup took 28.777 seconds; Linux replay took 0.230 seconds.
Actual owned-resource absence was verified. This is a focused integration check,
not a rerun of the 108-pair M0 corpus.

| Binding | SHA-256 |
| --- | --- |
| Control report content | `71509165a577f3245b4449e9232e6ef6d71fd7e6069ff54a68d4243f4a2647bf` |
| Collector bytes | `12f72289492b875afde7d7e46410b2950a58bb395a2328927e76035d845ab8d7` |
| Linux control audit and cleanup | `8af3177cb179bebdc5b4d633f1b06893a3d04ddde77d13d47e73afa3cb9044b8` |
| Windows control audit | `6371349424b17ce0835932380737aeb1ae5ead4d59b100231ed1c8421b54b282` |
| Consumption report content | `044cef66bbb415cb7872b1456843dc371df8ace0e8425036b72a9c5c0032d38c` |

[Machine-readable results](coverage-v2-results.json) include public-key, bridge,
image and per-control manifest hashes and the consumption audits. Raw evidence,
database captures and private recorder keys stay local. Run-local signatures
are experimental recording evidence, not Tower authorization.

All earlier attempts remain preserved: 001 failed before Docker on a missing
helper import; 002 failed on missing fixture session settings; 003 completed
seven controls, failed the eighth on absent schema creation, and left the ninth
unstarted. Corrections used fresh source/output directories. No failed slot or
signed artifact was overwritten.

Revision 1 and its seven-control evidence remain unchanged. Revision 2 requires
its own nine exact control sources, declared `dbo`/`business` schemas, collector
hash, bridge and image identities. It cannot borrow revision 1's qualification.
Coverage proves procedural statements/branches and conservative handler gates;
it does not prove arbitrary SQL expression, dynamic SQL or customer dependency
coverage. Customer admission and policy/release decisions remain outstanding.
