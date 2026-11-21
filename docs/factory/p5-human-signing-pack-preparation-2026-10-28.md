# One-signature public clean-control pack — preparation only

This is not ready to sign. The source/workflow integration is still an unpublished proposal. No proof, key, signature, Tower import or execution is produced by this helper.

The pack is built in two CI-only stages so Howard signs once after all executable inputs are fixed:

1. After exact source/workflow publication approval, run the unsigned input compiler in CI. It captures the native planner request without calling a provider and emits the public output script and public isolation document.
2. Review and commit those exact public documents at `docs/factory/p5-human-clean-control/public-outputs.json` and `public-isolation.json`. The four bound input documents are `scope.json`, `freeze.json`, `workspace.json` and `execution-policy.json` in the same directory. The worker and work order remain in `tests/fixtures/p5_public/human-clean-control/`.
3. Fix the executable commit containing all source, helpers, workflow and public inputs. No executable input can change after this point without a new plan and review.
4. In CI, use `tools.ci.p5_human_signing_pack` with that exact executable, a selected timezone-aware window no longer than the policy's 3,600 seconds, and a unique 64-character nonce digest. It verifies clean committed inputs, regenerates the public script for exact byte comparison, and writes only canonical `plan.json` and `contract.json` outside the checkout. The window and nonce are explicit inputs; no silent defaults are chosen.
5. Review the plan seal, canonical contract digest, executable, workflow hash, six source hashes and commits, public key hash, role actions, one-attempt/one-scripted-call limits and time window. The contract uses the existing `engineering-run-approval` kind and `campaign-authorizer` role. Every contract source has the installed Tower's exact three-field shape and a `docs/factory/` path.
6. Only after the complete pack is verified ready, Howard imports it into the existing Factory installation on port 8769 and records one decision. No machine signs and no second root is created.
7. Howard exports the genuine proof first, independently verifies the resulting current journal head with the installed `journal_head.py`, then verifies the decision against that head. The proof cannot supply its own trust anchor.
8. Only the plan, contract and genuine proof metadata may be added after the bound executable. Configure the final reviewed head, plan seal and independently verified journal head before the one authorized CI event. An ambiguous or consumed attempt stops; there is no automatic retry or resume.

The helper does not grant execution authority or create a proof placeholder. A successful clean-control component is not strict P5 green or a full production build receipt. The outstanding full-receipt gap remains explicit.
