# Model evidence and multi-workload qualification (v0.26.1)

## Import the retained v0.12 live-model run

MS #26.1 adds a compatibility bridge for the exact retained v0.12 live OpenAI evaluation archive.
Keep the archive outside the repository and run:

```bash
./factory-qualification.sh history \
  /secure/archive/model-evaluation-20260813T072624Z.zip \
  work/legacy-model-evidence/historical-model-evidence.receipt.json
```

```powershell
.\factory-qualification.ps1 history `
  -LegacyArchive C:\secure\model-evaluation-20260813T072624Z.zip `
  -Output work\legacy-model-evidence\historical-model-evidence.receipt.json
```

The pinned archive records one successful `INTCALC` public-calibration repair by
`gpt-5.6-terra`: three model calls, 101,127 input tokens, 701 output tokens, and an estimated
$0.210666 cost. The importer validates the archive and evaluation identities, 17 content-addressed
objects, 10 referenced artifacts, the 12-event ledger, model-call request/response hashes,
workspace before/after reconstruction, and the original failed-baseline/passed-final gate sequence.
It rejects traversal, duplicate members or receipts, stale hashes, raw model payloads, secret-shaped
values, altered model identity, sealed relabelling, and manifest drift.

The resulting receipt is deliberately `verified` and `historical-only`. It is not qualification
input because the source is a public legacy-schema evaluation, its independent sealed binding and
current request manifest are absent, its average input use exceeds the current 75,000-token policy,
and it supplies neither two runs per workload nor an approved four-workload portfolio execution.
The archive itself and all provider credentials remain external and are never committed.

## MS #26 qualification contract

MS #26 turns the model work-cell and portfolio controller into a measurable qualification plane
for four bounded CardDemo workloads: `INTCALC`, `POSTTRAN`, `CREASTMT`, and `ACCTPL1`.

The checked-in public catalogs verify controller mechanics and deterministic private gates. They do
not qualify a model. Promotion requires at least two distinct, independently sealed, model-backed
evaluation runs for every workload plus a passed four-cell portfolio run admitted through its human
approval barrier.

## Qualification decision

The aggregator checks the exact evaluation, factory-run, model-call, portfolio-plan, and portfolio-
run identities. It reports repair, correct-no-change, first-attempt repair, false acceptance, false
rejection, escalation, retry, resume, latency, token, and cost metrics.

A receipt is `qualified` only when every policy check passes. A single critical false acceptance
always blocks promotion, regardless of aggregate repair rate. The receipt always keeps
`production_ready` and `mainframe_equivalent` false because model qualification is not native z/OS
equivalence evidence.

## Verify the committed mechanism

```bash
./factory-qualification.sh verify
```

```powershell
.\factory-qualification.ps1 verify
```

This validates all four public catalogs and executes the regression suite. The deterministic local
worker repairs all 23 published mutations, preserves all eight clean cases, and records zero false
acceptances. That is a mechanism test, not a model score.

## Issue a qualification receipt

Keep sealed catalogs and their signing key outside the repository. Run each workload at least twice
through the existing sealed evaluation controller, then pass the resulting eight or more exact
`evaluation.receipt.json` paths to:

```bash
./factory-qualification.sh qualify \
  work/portfolio/carddemo-plan.json \
  work/portfolio/carddemo-run/receipt.json \
  work/qualification.receipt.json \
  work/sealed/intcalc-1/evaluation.receipt.json \
  work/sealed/intcalc-2/evaluation.receipt.json \
  work/sealed/posttran-1/evaluation.receipt.json \
  work/sealed/posttran-2/evaluation.receipt.json \
  work/sealed/creastmt-1/evaluation.receipt.json \
  work/sealed/creastmt-2/evaluation.receipt.json \
  work/sealed/acctpl1-1/evaluation.receipt.json \
  work/sealed/acctpl1-2/evaluation.receipt.json
```

The command exits nonzero and emits a content-addressed `blocked` receipt when any threshold or
portfolio control is unsatisfied. Provider credentials, prompt bodies, private mutations, and raw
model responses are not copied into the aggregate receipt; their bounded evidence hashes remain
resolvable from the input run directories.

## Recovery and safety boundaries

Evaluation checkpoints resume without repeating completed cases. Portfolio checkpoints resume
without repeating passed work cells and re-run only blocked cells. Resumption increments a
receipted counter and fails closed on plan, policy, approval, or checkpoint drift.

Qualification remains bounded to these four curated candidate surfaces. It does not establish
general autonomous modernization quality, customer workload coverage, native compiler behavior,
operational fitness, production authorization, or mainframe equivalence.
