# Public INTCALC candidate gate - C1 proposal r3, NOT-P5

Planned credential-free runner and verifier-only case freeze for an opaque Java
artifact. The same file contract applies to model-written and third-party code.
No provider, model, admission credential, signing or spend is included.

## Verifier-only case definition

The governing specification has SHA256
dbd33179d7eb5e79054e0048cb4cb38fd392adc2f3de5048c5c5eea7905ac143.
Its text, deterministic case definitions, hand-derived values and generator are
not committed here. The workflow downloads an exact-hash verifier-only Release
bundle into RUNNER_TEMP outside the repository and model workspace. No case,
answer, oracle result, comparison table or failure detail belongs in any model
role or MODEL-CONTEXT.zip, including repair feedback.

CI runs only the unchanged oracle as the reference, independently for ten cases:
NZ-POSTTRAN, TRUNCATION, DEFAULT, ZERO-RATE, ACCOUNT-BREAK, FINAL-ACCOUNT,
EMPTY-INPUT, ERR-NO-RATE, ERR-NO-ACCOUNT and ERR-NO-XREF. The last three expect an
oracle exception with a diagnostic. Their future candidate contract is non-zero
exit plus non-empty stderr; partial outputs are retained but not compared.

The new case-manifest.json pins all inputs, expected outputs, oracle observations
and the hand-versus-oracle cross-check. SHA256SUMS.json inventories every output.
Generation uses exclusive new directories. Any disagreement remains a FINDING;
the workflow fails after retaining the report. No oracle, comparator or spec is
changed to reconcile it. Candidate execution refuses a finding-bearing manifest.
The oracle is a public Python reference model, not z/OS evidence.

## Original deadline and black-box execution

A later independently reviewed binding separately pins the frozen case manifest,
Java OCI image, JAR, exact command, DD codec/layout, date/timestamp and one original
suite deadline. Replacing a candidate does not regenerate expected answers.
The input DDs are ACCTFILE300, TCATBALF50, DISCGRP50, XREFFILE50; outputs are
ACCTFILE300 and TRANSACT350. Records are concatenated cp037 with no newline framing.

The runner uses a digest-pinned local JRE image without pulling during a case,
network access, capabilities or writable root. Inputs/JAR are read-only. A local
32MiB tmpfs volume holds output; scratch is separate bounded tmpfs. After candidate
pause is observed, a trusted collector container mounts the same volume read-only
and runs its pinned-image tar, never docker cp. Candidate and collector are non-root.
Commands, exit, bounded stdout/stderr, raw archive, inventory and cleanup are retained.
Missing/extra/partial/unreadable output or decoder rejection fails only that case.
Infrastructure, original deadline or unconfirmed cleanup stops later cases.
No native owner/guardian-death proof is claimed.
First and repair attempts retain separate exclusive directories and tables.
This module does not grant another attempt.

## Exact treatment of unassigned bytes

Current policy remains strict: TRANSACT bytes56-131 (inclusive, description tail)
and330-349 (inclusive, filler) are verdict-bearing in #539's unchanged exact
comparison. All bytes and differences remain visible. The unchanged semantic
comparator ignores filler, but the exact half still prevents MATCH if it differs.
The description is not an ignored semantic field. Unsupported bytes can produce
a decoding/comparison fault, which also cannot pass.

Claude recommends report-only treatment until z/OS evidence; that recommendation
is recorded for exact review, not silently enabled. Every case result carries the
current byte policy. Oracle bytes in both regions are separately retained as hex.
No masking, normalization or comparator change is in this proposal.

## CI scope and remaining readiness

The workflow first freezes unchanged oracle results and hand-derived cross-check.
Post-POSTTRAN source text is provenance-checked before exact LRECL line conversion
to cp037; source and derived hashes, category key order and ACCT/XREF membership
are recorded/checked. Binding/refusal tests include candidate failures continuing
and infrastructure failures stopping. CI then pulls a digest-pinned JRE, uses
trusted javac/jar commands on the tiny public fixture and runs the real container
runner. Empty-input must MATCH; NZ must differ; all ten cases must be attempted.
Real container execution is pending CI, not established by static review.
No mock result counts as conversion or P5. The frozen manifest and actual row
table are pending CI and review, not claimed produced by static checks.
C1's schema always sets qualified=false and production_controller_receipt=false.
C2 preview-only policy needs separate exact approval before implementation or
credential creation. The externally authored intake page supersedes our earlier
intake deliverable; no replacement intake page is authored here.

## Source build and JAR binding

The model supplies Java source, never a trusted executable or build script. A later
trusted Factory build stage (C2/run-packet work, not implemented here) runs the
fixed javac --release 21 command requiring exact review on an exact source inventory without
verifier assets, then packages those classes with trusted jar --main-class Main.
The build receipt must bind every source hash, toolchain identity, exact commands,
compiler outcomes, class inventory and final JAR hash. Howard reviews that receipt
and artifact hash as part of the frozen run packet; C1 requires the same artifact
hash in its binding, which requires separate exact approval. A hash link alone does not authenticate
an untrusted builder. Third-party opaque artifacts use the same runner contract;
source-build provenance is UNKNOWN unless separately supplied and reviewed.

The B model-context contract uses javac --release 21 and java -cp CLASSES Main. Packaging the same classes
with jar --main-class Main yields C1 java -jar /candidate.jar with the same application
arguments and no dependencies or manifest Class-Path. This packaging adaptation is
a verifier/build-side proposal for exact review; B model context remains unchanged.
The CI fixture records source/JAR hashes, commands and tool versions. It proves
plumbing only, not that any model-written source has been built or converted.
The unused execute_case java parameter is removed; the exact command and Java
entrypoint are validated once against COMMAND before any candidate starts.

## Permanent verifier dependency and ERR-case limit

Release `full-intcalc-c1-proposal-r3` is a permanent CI dependency. Do not delete
or edit that Release or its assets. The workflow retains its exact ZIP SHA256;
any future replacement requires a separately reviewed dependency change.

ERR cases establish non-zero candidate exit plus a non-empty diagnostic only.
They do not establish the cause of the failure or prove that the candidate
detected the same missing input as the oracle. Reserved Docker exec statuses
125/126/127 and Docker-daemon error diagnostics are infrastructure refusals;
they never score EXPECTED_REFUSAL. Candidate timeout scores TIMEOUT and later
cases stay NOT_RUN. If cleanup is also unconfirmed, runtime.json retains that
fact; TIMEOUT is not a cleanup-success claim.

Planned runtime.json evidence includes elapsed milliseconds for every Docker
operation and cleanup step, including exceptions. The shared cleanup allowance
remains five seconds. On container-cleanup-unconfirmed, report those timings;
do not extend the allowance without exact review.

Planned build tooling uses exact setup-java Temurin version 21.0.9+10.0.LTS;
build-receipt.json records that requested pin and the actual javac/jar version
output and binary hashes. Repository-wide discovery skips the frozen-dependent
test class only when C1_FROZEN is absent or not a directory. Dedicated C1 CI
requires all eighteen tests, including the original fourteen, with zero skips.
No oracle, comparator, hidden-case definition or STRICT byte policy is changed.
