# Multi-workload factory qualification (v0.26)

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
