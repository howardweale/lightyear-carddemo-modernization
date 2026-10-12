# Alternatives and twin follow-up milestone — 2026-10-11

B4 uses the exact retained-image Linux JDK. Its public synthetic JLI/CDS and dump
matrix finished24cells: eight variants × three repetitions, no native application
runs or containers. [Aggregate results and limitations](../b06-retained-jdk-alternatives-milestone.md)
include all image/layer/JDK hashes and the comparison with Windows Corretto.
The contingent count-only design is prepared, unsubmitted and blocked on Part6's
explicit no-cause result, missing frozen training/runtime bindings and fresh approval.

B5 adds a mixed-key indexed probe using actual production LYKEY projection;
ASCII is expected to disagree with the cp037 order. It checks NEXT, START, random
READ, duplicate, EOF and REWRITE, while leaving logical bytes unchanged. The old
54/54 decimal-key receipt is preserved and labelled **no regression from cp037
key mode**. Neither that receipt nor this host probe removes the decimal-only
restriction or demonstrates z/OS equivalence.

The pinned Ubuntu container recipe and GitHub workflow produce one machine's
clean ASCII/cp037 binary hashes. A comparison tool requires a genuinely separate
operator-machine receipt with the same source/image/installer and complete binary
set. The second machine remains an external prerequisite; no result is invented.
[Procedure](two-machine-twin-reproduction.md) records that limit explicitly.

The [ZD&T design](zdt-calibration-design.md) covers the proposed emulated-z/OS
rung, preregistered INTCALC/POSTTRAN and COBDATFT/MVSWAIT assemble-bind-caller steps,
which limits each can resolve, host/USB requirements and required written IBM
licensing clarification. No purchase, run or machine setup is authorized here.

Focused host tests validate discriminator expectations and receipt rejection of
same-host, changed-head, altered and mismatched-binary evidence. Actual indexed
execution and one-machine build results are recorded separately from these tests;
final-head CI must complete green and Howard must approve that commit before merge.
