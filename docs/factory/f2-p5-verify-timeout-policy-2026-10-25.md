# Planned PR 455 Windows timeout binding

Planned: a separate exact-head merge review activates this binding from trusted main.
This proposal is preparation only. It records Howard's request for a Windows-only
60-to-90-minute verification timeout and does not claim exact-byte publication or
merge approval has occurred. The agent shares Howard's GitHub identity; the
operator-chat attribution is not independent authentication.

The binding permits only PR 455, regular-file mode 100644, the exact preimage and
postimage hashes, and the single timeout expression. Linux remains at 35 minutes.
Every other job, permission, step and test is identical. The existing P5 workflow
binding and all existing synthetic tests remain. A candidate cannot supply or
modify the trusted binding, and an extra workflow or permission changes the hash
and is refused. No source exception, judge fence or POSTTRAN scope is broadened.

Planned: publication and merge require separate exact-byte approvals. Merge must
precede the Monday 08:00 PT freeze; if green readiness is not attainable by about
Sunday 18:00 PT, the first run moves to Friday. The four-shard split is deferred
until after the first run. This binding grants no run or gap-acceptance authority.
