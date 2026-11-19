# Fenced formatting preparation — held draft

Do not merge before the factory run's verification completes AND after 31 October.
Rebase onto post-run main, regenerate the scope, and obtain exact-head approval.
No freeze record changes, exception approval, unfreeze or refreeze are authorized.

This first draft commit prepares a pinned, CI-only formatter and an exact 30-file
scope from the current freeze/F2 fence. It does not yet contain reformatted Java.
Google Java Format is selected for a single deterministic style with minimal
configuration. Spotless 2.43.0 / google-java-format 1.24.0 are pinned; import
reordering, string reflow and Javadoc rewriting are disabled. No clean-up,
unused-import removal or semantic refactoring step is enabled.

CI produces an inert patch and SHA-bound before/after manifest. Review the exact
artifact against its run/head/source hashes, then publish the accepted changes
as ONE formatting-only commit with no other changes. Run full CI on that actual
formatted head. Patch preparation is not equivalence proof or merge readiness.
The original frozen checks must refuse changed bound Java until the later review;
they are not bypassed or updated here. Full 678-interaction/database-after-state,
whole-storage and mutation proofs remain required on the eventual formatted head.

AuthorizationRecords, AuthorizationTest and the authorization package are excluded
because authorization Java is reserved for the factory. SourceEdits.java stays
byte-identical as the independent oracle. Remaining Java under the fence is
explicitly listed; all other tracked files must remain unchanged after formatting.

Idiomatic-index change at this preparatory head: zero source/engine change.
Actual formatted-file and line counts await the reviewed CI patch. K1 static
analysis and unfenced formatting remain separate work. POSTTRAN and #446 retain
priority. No local formatter, Java, tests, models, signing or Tower actions.
