# Frozen B06 practice r10 terminal review

The single authorized run finished in **387.672 seconds**. Capture, inventory,
producer and offline replay completed. The corrected six-check audit completed;
overall acceptance remains **FAILED** with `frozen-practice-six-checks-not-satisfied`.
No system-bundle URL error recurred. Zero model calls, databases or native pairs;
network disabled. Operator review, not independent attestation.

## Checks

| Check | Result |
| --- | --- |
| Census | PASS: 350 = 1 system + 203 /root/.m2 + 44 /application + 102 /tmp |
| Temporary bundles | PASS: 102/102 qualified source-only |
| Historical application content | BLOCKED: 4 bundles match both r4/r5b; 40 historical copies unavailable |
| Tycho | PASS: captured properties, resolved test plugin, single bound Equinox launcher |
| Warning baseline | PASS: 74 severity lines, zero new normalized messages, no structured error file |
| Frozen bytes | PASS: all 776 hashes unchanged |
| Cleanup | PASS: runner and independent owned-label container/network/volume lists confirm absence |

76 offline regression tests passed using frozen production imports before launch.
Public commit, plan and all 776 executable inputs were byte-verified before launch.
No Tower request or further practice was started. Prior failures remain preserved.

## Supplemental complete r9/r10 comparison

This comparison is separate from the frozen acceptance rule; it does not replace
r4/r5b or authorize any baseline change. All **44/44 entry sets are identical**,
but only **22/44 bundles** have identical normalized content. Full per-bundle
entry counts and changed paths are in review.json.

Twenty-one source bundles differ in Eclipse-SourceBundle's host version qualifier
and the timestamp comment in OSGI-INF/l10n/bundle-src.properties. These are not
normalizations permitted by the current rule. The org.idempiere.test folder
also differs in seven retained entries: target/MANIFEST.MF,
target/local-artifacts.properties, target/org.idempiere.test-13.0.0-SNAPSHOT.jar,
target/org.idempiere.test-13.0.0-SNAPSHOT-sources.jar, target/p2artifacts.xml,
target/p2content.xml and target/sourcebundle-l10n-gen/OSGI-INF/l10n/bundle-src.properties.
Sample literal metadata diffs are retained. No entry was silently excluded or
normalized to make the comparison pass.

The fidelity fix restores all 39 prior missing entries. The four old comparable
bundles still match with UI 1577, server 141, webservices 62 and Ant 65 entries.
Missing old captures and newly demonstrated build-dependent resource differences
both remain blockers. Repeating the same build cannot repair either requirement.
A build-once/reuse strategy would preserve strict resource identity; an alternative
requires an explicitly approved prospective identity/baseline amendment. Neither
has been applied here.

## Binding hashes

- public_commit: `f3dd63efb0263c08afe48c1066c919ef39f6eabf`
- source_commit: `c90723b8dfdad4db6beba5e2e74554e844d6965e`
- snapshot_sha256: `db6cc35a7927b26987c1a052149ba818ca006f9fb5430dc8207c01a9f7b1e3d3`
- plan_sha256: `397102089f2979d3d36637bab6551348ab3e6b489a875daac906b96ffdbf05c7`
- practice-report.json: `20bd1f0e7800f9aa595bb45236ba3f39c9bb6fee9570b5a4f20ac714679b556c`
- six-checks.json: `c84a6c677a280d99baea8349a9602b1049be887f460bced438c0e2de052b73d0`
- Terminal review: `a6a528bb0b2a0a476bc1751ba35fdf8e9898798b193b9a4120143940646127a6`
