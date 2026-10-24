# P1 scanner integration and baseline procedure

The always-triggered P1 workflow is selected by the existing required-CI gate.
It measures Ruff lint/format and mypy on tracked `src/` Python files, pip-audit
across every declared default/optional dependency group and requirements file,
OWASP Dependency-Check across every tracked `*pom.xml`, Gitleaks on the PR range,
and CodeQL on Python, Java and JavaScript. No scanner runs locally during review.
Missing tools, unresolved dependency groups, skipped packages, invalid reports,
missing controls, failed analysis and incomplete scans cannot report clean.

Pinned versions are Ruff 0.17.2, mypy 2.4.0, pip-audit 2.10.1, Dependency-Check
13.0.0, Gitleaks 8.30.1 and CodeQL bundle 2.27.3. The CodeQL action has an exact
commit pin. CI verifies the Gitleaks and CodeQL distribution sizes and SHA-256
digests before use. The Maven plugin comes from the normal Maven repository
resolution with an exact version; no local compiler or package installation is
part of this change.

Real-tool controls plant a synthetic fake-token pattern, a vulnerable Python
pin, a vulnerable Maven pin, an unused import, a format defect, a type error,
and a language-specific CodeQL vulnerability. These probes are inert input;
their application code never runs. The CodeQL reducers require the expected
built-in query result before removing the exact synthetic probe from counts.

## Public evidence and findings

CI artifacts contain counts, severity, source-bound paths, execution state and
opaque quality fingerprints. Raw messages, SARIF, snippets, secrets, package
vulnerability descriptions and scanner stderr remain temporary runner data.
CodeQL database/SARIF uploads are off; only the reduced artifacts are public.
A scanner finding blocks the gate. Report any real secret or critical finding
privately to Howard immediately; do not put its details in a PR comment.

The first Gitleaks integration run measures the complete fetched public Git
history as well as the PR range. Its reviewed count/path report will become a
dated retained receipt; the history bootstrap must then be removed in the next
revision, leaving required PR-range scanning. No history scan has run yet.

## Initial baseline and subsequent changes

The measurement job retains `summary.json` and `baseline-proposal.json` even
when the baseline gate fails. No fabricated zero baseline is present. Review
the real artifact and its exact checkout/run/attempt/source hashes, then commit
the approved initial quality findings as `p1-quality-baseline.json` and publish
the one-page severity summary on #436. That work is still pending CI.

For bootstrap only, when the trusted base has no baseline, CI independently
scans the exact base checkout with the same tools. A proposed baseline cannot
contain allowances outside that measurement or omit current findings. After
the first merge, only the committed trusted-base baseline is authoritative,
and its allowance set may only shrink. There is no security-findings baseline.

## Dependabot and slot policy

The configuration enumerates pip, Maven, Actions and the two npm projects.
Version-update PR creation is initially paused with a zero limit to preserve
Howard's eight-open-PR ceiling. This is **not active dependency-update coverage**.
Activation and its shared slot budget remain a review decision; do not claim
P1 complete while this is unresolved. This PR does not enable repository
security-update settings or change branch protection. Maven templates with
nonstandard filenames are covered by the scanner inventory, not a claim that
Dependabot supports every template filename.

The combined COPAU/F2/POSTTRAN guard runs in required lint, using trusted-base
checker bytes after bootstrap. No clock-based unlock, candidate exception,
seven-binding adoption, signing, factory run or model spend is introduced.
Java idiomatic-index change: zero. Ten-minute checks remain off.
