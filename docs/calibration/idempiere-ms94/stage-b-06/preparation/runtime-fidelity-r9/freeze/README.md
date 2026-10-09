# Frozen runtime practice r9 — awaiting Docker approval

Implementation commit: `4b81aa53eeb4f6529ddcbf89531499556d6beb8b`.
Common plan content hash: `7c9d17040760c29a49f6208249d02412cf944bfb9584a3eb9eb426a902ae65a9`.
Executable snapshot hash: `95759f307c69d02207495838624fdbebbccbd1c5b988f25d6cab2e865778d6ea`.
All 776 files were copied directly from committed Git objects (including the
committed warning baseline and historical-content hash maps). The public plan
is [plan.json](plan.json); [offline-check.json](offline-check.json) records
106 tests passed in 16.735 seconds using frozen production imports. No Docker
or model calls. Source-byte differences are rejected before and after practice.

## Proposed one-shot practice

One pinned-image container; maximum 45 minutes plus 10 minutes cleanup reserve.
No network, database containers, native pairs or model calls. Only its owned
resources may be removed. Fresh output directory and a one-time claim; no retry.
No production signing key or Tower authority is used by practice. Evidence
requires the same common plan and executable bytes with a separate Tower window.

**Howard's approval of this practice is required before running.** No request
has been inserted into Tower. Use this exact frozen command only after approval:

```powershell
$repo = 'C:/Users/howar/.codex/worktrees/tsql-m0-review/lightyear-carddemo-modernization'
Set-Location "$repo/work/b06-runtime-snapshots/fidelity-r9"
$env:PYTHONPATH='src;.'
$env:PYTHONUTF8='1'
& 'C:/Users/howar/OneDrive/Documents/ChatGPT/lightyear-carddemo-modernization/work/idempiere-runtime-evidence/work/native-venv/Scripts/python.exe' -B -m tools.b06_image_artifacts.runtime_practice run --plan "$repo/docs/calibration/idempiere-ms94/stage-b-06/preparation/runtime-fidelity-r9/freeze/plan.json" --snapshot . --output "$repo/work/b06-frozen-practice-r9" --run
```

All six checks will be recorded separately from pipeline completion. Missing
historical evidence counts as a failed acceptance check: r4/r5b retain only
4/44 full application contents. No future practice can recreate the missing
40 historical captures. This plan deliberately does not weaken that requirement
or assume a replacement baseline. It cannot authorize Tower until the required
evidence exists or Howard explicitly approves a prospective new baseline and
corresponding fresh plan/practice. Any code change invalidates this freeze for
subsequent evidence use. Operator review, not independent attestation.
