# Java quality fence

The required documentation/lint job derives this fence from the trusted base
commit's original COPAU judge freeze, its additive amendment, F2 request bindings,
worker manifest and all retained shared-support inventories. It protects whole
authorization and original Java-test directories against new files too.
Deleted paths, both sides of renames, and file-mode changes are checked.

The same check applies to every PR, so relabelling a K PR does not bypass it.
The lint entry point runs the base version of the checker, reading base records;
only the first installation bootstraps from its candidate version. Changes to
the CI entry point still require normal review. The retained inventory is a
dated observation; each CI run recomputes the live fence and prints its digest,
source-record hashes, counts and blocked paths.

K5, K7 and formatting of fenced files stay draft PRs. Run their complete proof
jobs; an expected fence refusal is a merge blocker, never a reason to cancel
those jobs or weaken the original frozen-judge check. No date automatically
releases the fence. After run verification is complete and after 31 October,
rebase on post-run main and obtain a separately reviewed policy change plus
Howard's approval of each exact final green head. No unfreeze/refreeze now.

K1 starts with unfenced files. Keep formatting-only changes separate from
behaviour or build-policy changes. K2 rendering needs its own final proof.
Every K approval packet in issue #436 must state its idiomatic-index before and
after, measured proof run links and exact head. This infrastructure has zero
production-Java and engine-count change; it does not claim an idiomatic gain.

CI tests cover synthetic record derivation, binding refusal, new files, retained
support unions and actual Git renames/PR-side record tampering. No local tests,
private reads, signing, model calls or factory execution are part of this work.
POSTTRAN and the private answer-key helper retain scheduling priority.
