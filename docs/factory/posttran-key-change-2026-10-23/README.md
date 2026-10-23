# POSTTRAN original executable: public authority change only

Prepared 23 October 2026 under Howard's explicit key-only decision. This is
an unsigned preparation for review by Monday 26 October at 12:00 Pacific.
It grants no signing, execution, model use, repair or release authority.

The executable pin in `amendment.json` has the original sealed executable
as its sole parent. Its entire tree differs at exactly one path: the public
Tower key. That PEM is the exact LF-terminated public value Howard posted
on [PR 415](https://github.com/howardweale/lightyear-carddemo-modernization/pull/415#issuecomment-6368416273).
The original executable is the one named by the historical October 16
request, before the later release-projection binding amendment. Neither
that later amendment nor the seven current-main differences is adopted.

The public key is outside the original plan's 182-file inventory. Therefore
the plan bytes and its seal stay unchanged. In particular, the existing
attempt-reservation tag name stays unchanged: changing the key must never
reset or create a second attempt namespace. The candidate and provenance
remain byte-identical; generation attempt 1, zero retries, zero model calls,
and no candidate repair remain mandatory.

`seven-bindings-not-adopted.json` retains the old/current hashes solely as
a dated reference. Static call-path review found no demonstrated defect
among those seven requiring adoption for this original execution. This is
not a claim that application equivalence has already been measured.

## What the PR checks

The main-based review PR adds records, a read-only Git-object validator,
and a separate CI workflow. It does not replace main's public key or any
frozen file. The original executable is retained on a separate immutable
branch for inspection; it is not proposed as a merge into current main.

CI verifies the complete key-only tree, all 182 bindings, candidate bytes,
original plan seal and new unsigned request. In a disposable worktree of
the exact executable it runs the original signed-authorization tests and
the eight original reservation-boundary rehearsals. Those tests create
only disposable fixture authorities and intercept the tag transport.
They do not use Howard's key or contact a Tower. Application compilation,
candidate execution, twin execution and real attempt reservation are absent.

The same workflow downloads the retained compiler ZIP as inert bytes,
checks its API digest, size and preparation provenance, then hashes the
inner image without extracting or loading it. It refuses less than 24 hours
of remaining retention. The proof artifact is produced only after the
selected rehearsal tests and image verification succeed. These are selected
authorization tests, not a claim that the entire historical suite was run.

## Review and later handoff

`unsigned-request.json` retains the original plan hash, observer hash,
candidate/image hashes, one-run cap and original authorization window. Only
its executable/source commit references point to the key-only executable.
The amendment records the posted journal observation; Howard must verify
the appropriate journal head at signing time. No journal export is done here.

Readiness remains false pending final-head CI review and Howard's approval.
No existing approval transfers. Any later execution head must descend from
the key-only executable and add only the request/proof files permitted by
the unchanged original verifier. Packaging that future execution PR is not
performed or authorized by this preparation. Do not merge current main into
that executable or substitute the main-based review PR as the run checkout.

The artifact expires on 30 October at 07:46 Pacific; its 24-hour margin makes
29 October at 07:46 Pacific an exclusive deadline. Neither date is extended.
Monday's review remains contingent on passing CI and fresh artifact checks.
