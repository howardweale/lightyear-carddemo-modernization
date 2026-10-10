# B06 engineering-mode preparation milestone — October 10, 2026

Implemented a separate Oracle-only retained-reference debugging entry point on
top of #293, with a standing approval, ten-attempt ceiling, calendar exclusions,
owned cleanup, consumed failed attempts and explicit uncredited artifact labels.
There is no per-attempt freeze/Tower request or automatic retry. The run log and
alternative-design investigation register are prepared.

Validation: 41 focused tests passed in 1.963 seconds: engineering contracts and
Oracle-only mocked setup/cleanup, pure alternative-record accounting, existing
controller, measurement admission, qualification driver and group-request tests.
No JVM, Docker command, model call or native workload ran as part of these tests.
One initial test used a 25-hour window and hit the calendar cap before the overlap
guard; its fixture was corrected to remain within 24 hours. Production guards were
not weakened. Static source inspection verified installed JDK dump property names.

The real native path is not yet proven. The proposed standing window and all image,
time/resource/output limits are in `b06-engineering-mode.md`; approval is pending.
No standing approval receipt was created. The current unmatched-return diagnostic
and all historical evidence remain untouched in their own worktrees.

Part 2 has no before/after native measurements yet. The report explicitly marks
call reductions, coverage and classification counts as pending. Those experiments
must wait for an evidence-free gap and the relevant approval. Changing the retained
image or native JVM options would need an explicit amendment; the baseline approval
does not authorize an unreviewed alternative runtime. No merge is authorized.
