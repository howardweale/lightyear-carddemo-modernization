# Draft successor for the held F2 policy

This main-based proposal separates the existing exact-byte validator and its refusal tests from PR #455. The candidate branch cannot authorize its own fenced source changes. The original raw Java fence is unchanged; this draft does not clear #455.

The 24-path runtime manifest remains pending-exact-hash-approval, with approval and approved_change_commit null. It supplies no runtime exception. Howard's earlier publication receipt is historical and explicitly limited to PR #455 publication and CI; it is not a policy activation or run approval. New run-bound bytes require their own exact-hash decision. The configured route is still an unpublished proposal and is not covered by these runtime hashes.

CI should exercise the copied synthetic policy refusals through the existing full test discovery. Tests cover pending approval, hash/mode/path/PR/provenance substitution, extra violations and judge/POSTTRAN exclusion. No workflow or source runtime is changed. Test results for this new main-based composition are pending; earlier PR results do not establish its correctness.

Do not merge until composition review, terminal CI and exact final-head approval. Refresh the complete configured/runtime hash set and its provenance before any activation request. Main policy must merge before #455; resulting main must then validate before package freeze and explicit GO. No signing, nonce use, model call, spend, waiver or execution authority is granted.
