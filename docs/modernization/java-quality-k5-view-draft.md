# K5 account-view typed orchestration — held draft

Do not merge until the factory run verification is complete AND after 31 October.
Rebase on post-run main and obtain fresh proof and exact-head approval. Commarea
is F2-bound: this draft does not authorize an exception, unfreeze or refreeze.
The unchanged frozen-judge and F2 preservation gates must continue blocking it.

This is the account-view increment of K5, not completion for every service.
All eleven common-area names used by COACTVWC move into a closed typed adapter.
Its get/set/MOVE methods forward to the original storage behavior. The original
field resolver is reused for startup validation without decoding request bytes.
Four generated source constants are validated and loaded once at construction.
Missing/ambiguous names and malformed constants refuse before any request.

The original service is reconstructed by a closed reverse mapping, with full
adapter hashes, before the existing byte-exact service/oracle check. Existing
whole-screen, storage, database-read-order and original-COBOL projection tests
stay unchanged. Three added JUnit fixtures cover adapter bytes and startup
refusals; two Python refusal fixtures supplement them. Independent CI retains
the existing account-view mutation gate and adds a nonempty 90% all-generated,
KILLED-only gate for CommonArea and AccountViewConstants. Full-slice proof is
still required. No runtime result is claimed before actual CI completes.

Idiomatic-index delta: account-view orchestration CDEMO string literals become
zero; paragraph/engine counts are unchanged. Other orchestration services still
need subsequent K5 increments. The new generic adapter must not be used to
change authorization-screen Java. POSTTRAN and the private helper retain priority.
No local tests, models, real signing, Tower actions or private material.
