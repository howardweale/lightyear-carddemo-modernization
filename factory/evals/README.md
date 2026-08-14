# LIGHTYEAR model work-cell evaluations

The v0.13 evaluation plane measures whether a model-backed work cell can repair an isolated defect
without giving the worker acceptance authority or private gate output.

`carddemo-v0.12-public.json` contains 36 public calibration cases across copybook layout, field
mapping, decimal behavior, interest and disclosure policy, transaction contracts, runtime shapes,
dataset/JCL names, and the final-account boundary. Each case is applied to a fresh workspace and
must fail the private baseline before a repair can count.

## Evidence classes

| Class | Location | Valid claim |
|---|---|---|
| `public-calibration` | May be committed with the factory | Measures repeatable mechanics and visible-suite model behavior |
| `sealed-holdout` | Retained by an independent evaluator | Measures blind generalization for the supplied catalog identity |

Changing the label does not make a public suite private. In a real evaluation, retain the holdout
catalog outside the repository, provide it only to the controller at launch, and prevent planner,
builder, provider tooling, and prompts from reading it. The evaluation receipt records the catalog
hash, class, aggregate score, per-case receipt hashes, token use, and false acceptance without
including the mutation text. The controller also requires a valid external envelope before it will
run any catalog labeled `sealed-holdout`; changing the label is not admission.

## Scoring

A case is autonomously repaired only when:

1. the mutated baseline fails the private gate;
2. at least one bounded model patch is applied;
3. the independent gate subsequently passes; and
4. the final factory receipt is internally valid.

Baseline rejection, autonomous repair, and false acceptance are recorded independently. The public
suite's default threshold is 70% repair with zero false acceptance. Passing either evaluation class
does not prove z/OS equivalence.

Cases may use `reject-and-repair` or `accept-unchanged`. Clean cases prove that the work cell can
recognize correct code and stop with zero edits. The factory-quality gate additionally requires a
minimum case and category count, clean cases, evidence-scored cases, baseline rejection, repair,
first-attempt repair, evidence precision, correct no-change, zero privacy leaks, zero unauthorized
edit attempts, zero false acceptances, and bounded average input tokens.

## Commands

```bash
./model-workcell.sh validate
./model-workcell.sh evaluate
./quality-gate.sh sign /secure/evaluator/holdout.json /secure/evaluator/holdout.envelope.json independent-evaluator
./quality-gate.sh evaluate /secure/evaluator/holdout.envelope.json
```

Model credentials and optional price inputs remain environment-only. Run artifacts are written
under `work/model-evaluation-*` and should be retained with the corresponding audit snapshot in a
production deployment.
