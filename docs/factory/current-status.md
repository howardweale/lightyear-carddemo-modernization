# Current factory status

Generated from named decision files, the keep-or-fix register and the latest bound receipts below. This view is documentation, not an execution approval. Historical milestones remain historical.

Decision time: 2026-10-11T14:00:00-07:00.

- B06: October 13, 9 AM-noon PDT request; delivery due Monday October 12, 5 PM PDT. Exact executable commit and request seal need Howard's one-line go. Engineering execution remains held.
- POSTTRAN: 10/10 unsigned operator acceptances received and bound to the historical sheet; Howard's signature remains outstanding.
- POSTTRAN Phase 1 plan: `bb53fd6de1afed29fc1064f986c6c2dadc5d709b93c9732c50a67077aaeb2919`. Operator attempt 1 completed at 2026-10-11T23:12:20.953571+00:00: 147242 input and 17969 output tokens. Receipt and artifact hashes verified locally; compilation and Phase 1 validation remain pending. Phase 2 is unapproved; no further model call is authorized by this status view.
- scenario-threshold/2: conditionally approved as amended, not effective until B1 completes, remaining equivalence arguments are accepted and the current-head compiled campaign satisfies the gate.
- Equivalence sample: AI-assisted operator review accepted by Howard; not independent human attestation. The TWO-BYTES mutant remains unresolved for z/OS-facing claims.
- B07: 72 analysis slots per arm, graph versus search, two runners, at most 14 calendar days. The power limitation requires review before freezing. Spending remains unapproved; B06 Part 6 and graph coverage precede trials.

## Recorded legacy dispositions

- REWRITE-109: keep-by-default
- CBACT04C-FINAL-ACCOUNT-EOF-ELSE: keep-by-default
- POSTTRAN-DUPLICATE-ID-NONATOMIC: keep
- POSTTRAN-CYCLE-DEBIT-SIGN: keep

## Evidence inputs

- [howard-decisions-2026-10-11b.json](howard-decisions-2026-10-11b.json): LF-normalized SHA-256 `74fe7a1d88d8740a7f3ba147dfcad8d9355c27c439f02cc5a85f7704b453b0e4`
- [keep-or-fix-register.json](keep-or-fix-register.json): LF-normalized SHA-256 `d92053ed3ba1d715df87c9a07e640c0f404bee2823a65c6bd9e38775c853a28a`
- [posttran-decisions-unsigned-2026-10-11.json](posttran-decisions-unsigned-2026-10-11.json): LF-normalized SHA-256 `02d506e550328e81fbe14e3dd508d0b688113c603933f7a330f182267dfb06dc`
- [dedicated-transport-plan-2026-10-11.json](posttran-second-opinion/dedicated-transport-plan-2026-10-11.json): LF-normalized SHA-256 `380eeedac982d0a0334456366dc205e102e9dd08a46a18d0fe03d6cc370f046a`
- [b07-prefreeze-power-2026-10-11.json](b07-prefreeze-power-2026-10-11.json): LF-normalized SHA-256 `fb0af41a345b7e40738b1368d2451a82b5e46379da27c223e80563aaf2c44f1c`
- [ci-times-316-320-2026-10-11.json](ci-times-316-320-2026-10-11.json): LF-normalized SHA-256 `03aeed2a2a72b29b9fdc2997e6ffdac6832f16306ccb140039a34c139f10e3cf`
- [attempt-1-public-summary-2026-10-11.json](posttran-second-opinion/attempt-1-public-summary-2026-10-11.json): LF-normalized SHA-256 `08cf36d5ad44dcc18ebfd7159008ad9db67825f5ecd063436d6fbc700682d83a`

Generated view seal: `67b8515528f580d4b76b62c1b3f0eb0716a6e7c06f92ca6ba6694e45a640871c`.

Regenerate with `python -B tools/build_factory_current_status.py`; CI uses `--check` to refuse stale output. Missing or changed source records require regeneration and review. No approval is inferred from a filename, unsigned acceptance or a green CI badge.
