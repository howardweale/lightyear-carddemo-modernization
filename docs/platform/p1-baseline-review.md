# P1 measured baseline for review

Measurement: [run 40050331083, attempt 1](https://github.com/howardweale/lightyear-carddemo-modernization/actions/runs/40050331083).
PR head `fb05494da6d66c7bba8a064e902443cf2b0d43bf`; synthetic merge `7a19c52368fbb5c1b63b784e63025c5d9fef8b06`; main `811c2aff2fe2be37b1aa1d9b5aa7ec3f312e9d5e`.
All 558 tracked Python files under src/ bind to inventory SHA-256 `1d42311df8ea90bb2bb185b11fdc4f49223e2fc55ef30c82fb30195b389752ae`.
Artifact 12542809819 ZIP SHA-256 `dac265e9cab8890e0703e356e33ec94fe26fac84e501a8520e3b2eee8705f74d`.

| Tool | Severity | Count |
| --- | --- | --- |
| Ruff lint | warning | 2393 |
| Ruff format | warning / unformatted files | 490 |
| mypy | error | 403 |

This is an initial baseline proposal, not a claim of clean source. The baseline
contains only paths, severities and opaque finding fingerprints. CI independently
scans the trusted comparison base before bootstrap, rejects new findings and
permits later baselines only to shrink. Review this proposal with the final head.
No security finding receives a baseline allowance.

The same run's pip-audit report covers all ten manifest/groups with zero findings.
Gitleaks reports zero PR-diff matches and 2058 full-history matches; these require
classification and are not confirmed credentials. Public reports contain counts
and paths only. CodeQL controls failed while automatic diff-informed analysis was
active; full analysis is now explicit so out-of-diff controls and source remain
in scope. Fresh controls and complete findings still must pass. Dependency-Check
stopped on certificate validation during database update, with no report; bounded
endpoint-category diagnostics identify the next repair without disabling TLS.

An old event-base comparison incorrectly includes the already merged P4 proposal.
The comparison helper binds GitHub event identity, both merge parents, ancestry
and exact merge tree before choosing its actual first parent. Candidate changes
and receipt dependencies remain checked; dated main records remain untouched.
No main integration commit, suppression, scanner bypass or fence change is made.
Idiomatic-index change: zero. Ten-minute checks remain off.
