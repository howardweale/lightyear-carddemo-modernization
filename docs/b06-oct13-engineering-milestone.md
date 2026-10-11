# B06 October 13 engineering preparation milestone

Prepared offline on October 11, 2026. Native execution remains unauthorized.
This branch implements Howard's A6/B3 decision for two consumed Oracle-only J1
attempts on October 13, 9 AM-noon PDT. The old October 12 proposal is superseded;
old approvals cannot open this branch's execution context.

## Changes and exact-source limitation

The accepted baseline observer source `02b2f7fd4080bfbcd821ef51147c455d7f57620eac797b809d406d73f935c64b`
did not record genuine class-input witnesses for every generation entry. B3.4
explicitly asks for missing witnesses to be added and the r6 host memory test to
be repeated. This branch therefore changes the observer; it does **not** satisfy
B3.1's simultaneous unchanged-source wording. The final exact-go request must
identify the changed source and its new evidence. No source substitution is
silently authorized.

The new witness reads actual receiver fields: LambdaMetafactory targetClass,
ClassDefiner lookup.lookupClass, and InvokerBytecodeGenerator MethodType return
and parameter classes. ClassLoader.defineClass records the exact byte slice hash
and defining loader, explicitly classified as unresolved bytecode input. Caller
stacks are never promoted to class inputs or proof of application provenance.

The runner binds Howard's literal exact-go line, actual clean implementation
checkout, unsigned request seal, source/classes, native template, and every file
in the new asset index. An unlisted file or changed hash refuses before Docker.
The first reservation must leave 8,400 seconds; the second must leave 4,200.
Failure consumes the attempt; no replacement, retry or automatic second attempt.

## Preserved first witness run

The [first witness host result](b06-oct13-host-witness-r1.json) completed 40,985
generation entries at 192 MiB without OOM, with every new input witness validated.
It **failed** the unchanged flat-heap criterion: slope 0.175978 bytes/emitted
record, Newey-West 95% interval [0.032609, 0.319348]. Its result and raw local
outputs are preserved. A completed workload and a small absolute heap are not a
substitute for the predeclared acceptance rule.

Source review found that the initial encoder called the general definition
encoder, which invokes `remember(t)` and can materialize extra JDI mirrors and
bytecode data. A narrower encoder preserves the same class-object ID, class,
loader, and signature fields without those side effects. A proxy-JDI regression
forbids the extra operations, and real-host JDI witness tests pass. This is a
concrete correction, not a proven explanation of the measured slope. The [second named same-workload run](b06-oct13-host-witness-r2.json) passed the
unchanged criterion: 40,985 generation entries / 517,283 emitted records,
1,195.937 seconds, no OOM, peak after-GC heap 6,170,168 bytes. Its slope is
**Ã¢Ë†â€™0.076915 bytes per emitted record**, Newey-West 95% interval
**[Ã¢Ë†â€™0.227845, 0.074015]**, using 469 samples after the original 50,000-record
warmup. The accepted baseline's slope was +0.046911 bytes per emitted record,
95% interval [Ã¢Ë†â€™0.133845, 0.227666], on the same unit and acceptance method.

All 40,985 input witnesses validated: 12,608 application-derived inputs,
25,374 bootstrap-only captured-input candidates, and 3,003 explicitly unresolved
bytecode inputs; none were missing. Bootstrap-only captured inputs do not prove
image independence. The first result is not relabeled; the second run shows this
changed implementation passes the host criterion, without independently proving
the first run's retained-heap slope was caused by the removed lookup side effect.

The exact-go gate also checks a digest-bound host result matching the source and
all compiled observer classes. A failed memory result remains blocked even if
someone supplies the exact-go text. Host evidence never grants native credit.

## Cap projection and limits

The [projection](b06-oct13-cap-projection.json) authenticates the preserved native
prefix, retains every old audit row in its compression estimate, then adds all
host metadata as an allowance. At 37,000 entries it estimates 98,265 ordinary
records, 984,688 metadata records, 179.35 MiB metadata and 5.11 GiB total private
output. Attempt two fits the preapproved 150,000 / 1,500,000 / 384 MiB ceilings
in this scenario. Its first projected resource stop is about 56,363 entries. The pending projection uses the maximum observed host
sample (243), rather than only the last sample.

These are linear scenarios, not worst-case bounds. Time to 37,000 within the
60-minute work budget is unproven. Strict refusal, the ten-return diagnostic cap,
payload tails, pending-state pressure or actual output/free-space guards can stop
earlier. Non-stream captures/logs are unmeasured: 1 GiB is a conservative scenario
reserve, not a measured upper bound. An automatic approval review rejected a
historical directory-size read; that read was not retried indirectly.

The separately approved whitelist copy preserved the original strict snapshot
and produced new owned asset roots. Historical native outputs, signing keys and
credentials are excluded. No native application, Docker command, model call,
signing operation or machine configuration change occurred.

## Replacement request preparation

Cross-review caught three pre-execution boundary defects: attempt two was rejected
by an application-level comparison against strict-only limits; a child checked
selected plan fields rather than the complete derived plan; and prior-attempt
advancement trusted receipt presence without verifying signatures and all artifact
hashes. Implementation `62eafdaf29dce1d40603d38c3a394f150b98f686` corrects all three.
The full-plan handoff, resource boundaries, signed cleanup/terminal/inventory and
consumed sequence are checked before effects. Read-only cross-review found no
further actionable issue in these paths; 78 focused tests passed in 10.331 seconds.

The unapproved `bd53f4ccc4baa48e473e596d484429b62a2f3d7586b8ef549e05ae7a80e11de0`
request and its earlier delivery record remain superseded, with no execution.
New successor assets bind 111,311 files, 872 source files and the unchanged 14
host-proven observer classes. Preparation took 182.281 seconds. The complete
replacement plan, fresh delivery record and unsigned request seal are published
with this milestone. Final-head CI and Howard's separate commit-specific merge
approval remain required. No merge or execution is part of this preparation.

The replacement full plan was delivered on **2026-10-11T22:19:17Z**. Its unsigned
request seal is `107c20733d9bc7862461b6e13ba4c180cdf1dad160f51be410c5523587900f35`;
file SHA-256 is `663fa537b827dbdf71be14e27cce9a5f26155dea6c19671765e7fa7f5e344fc9`.
The execution implementation remains `62eafdaf29dce1d40603d38c3a394f150b98f686`;
subsequent documentation commits are publication identities only. The final
Windows fixture correction resolves its temporary assets path exactly as the
production supervisor already does. Earlier Windows fixture failures and the
external Trivy HTTP 403 failure are preserved; fresh source-head Windows
synthetic, pinned Linux host-JDI and cloudbank SQL recovery checks succeeded.
