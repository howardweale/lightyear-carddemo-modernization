# K1 Java static-analysis baseline draft

This draft captures Checkstyle, Error Prone and SpotBugs evidence for the CardDemo
service's tracked production Java sources. It changes no production Java, original
POM, original test, mutation threshold, dated receipt or frozen binding. Scanning
fenced sources is read-only; their remediation remains held behind the freeze.
The separate formatter PR remains responsible for its formatting and proof results.

## Before this draft can be approved

1. All three CI scanners must run with their pinned versions and detect their
   synthetic negative controls. Checkstyle must detect a multi-statement line and
   wildcard import; Error Prone must detect a discarded exception; SpotBugs must
   detect string reference comparison.
2. Review the exact checkout, source hashes, logs and reports retained in the three
   `java-analysis-*` artifacts. A missing report, compilation failure, missing
   class or parser refusal is incomplete evidence, not zero findings.
3. Publish the actual baseline and an idiomatic-index result for that measured
   head. The committed placeholder is **pending**, not an approved empty baseline.
   The baseline job deliberately refuses until reviewed results replace it. No
   findings are automatically accepted by the capture step.
4. Re-run CI on the final head. New rule/location findings fail; duplicate-count
   increases fail. A baseline already present on the trusted event base can only
   shrink. Location changes caused by formatting require review, not silent
   rebaselining. Howard approves the exact final green head.

Checkstyle covers naming, one statement per line and wildcard imports. Error
Prone retains enabled checks while collecting errors as warnings so the complete
finding inventory reaches the baseline gate. This does not waive a finding.
SpotBugs uses maximum effort and the low threshold, refusing analysis errors.
Security issues still require security review; this quality baseline does not
approve or suppress P1 CodeQL findings.

The scanner runner creates an exclusive disposable POM beside the original only
inside CI, preserving the original dependency and proof configuration. It uses a
fresh output directory and removes the disposable POM after the scanner. The
original POM and all production source hashes are checked again afterwards.
No tests or scanners run on the operator's machine. Existing proof jobs remain
required; scanner success does not substitute for parity or mutation proof.

Idiomatic-index change at publication: no engine, identifier or readable-test
change; static-analysis counts are unmeasured until CI artifacts are reviewed.
The mojibake guard remains the existing Java text check, independent of these
scanners. No factory execution, signing, model calls or spending is authorized.

Configuration follows the primary documentation for
[Error Prone](https://errorprone.info/docs/installation),
[Checkstyle's Maven report](https://maven.apache.org/plugins/maven-checkstyle-plugin/checkstyle-mojo.html)
and [SpotBugs' Maven report](https://spotbugs.github.io/spotbugs-maven-plugin/spotbugs-mojo.html).
