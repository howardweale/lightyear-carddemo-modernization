# Verified business rules

The existing curated mapping entries now support executable rules and earned,
signed statuses. This is an offline operator workflow. It adds no agent tools,
model calls, Docker runs, or production authorization.

Select `knowledge/mappings/carddemo-intcalc-executable.json` for executable
INTCALC rules. It is authored from the existing curated mapping with the same
rule IDs and added executable fields. The default `carddemo-intcalc.json` remains
byte-identical for historical graph and source-evidence reproducibility.

See [design and inventory](design.md), [milestone](milestone-2026-10-10.md), and
the [public acceptance catalogue](evidence/catalogue.html).

## Operator workflow

Install the existing `control-tower` optional dependency, or use an environment
with `cryptography`. Set `PYTHONPATH=src;.` on Windows (`src:.` on POSIX).
All output paths must be new. The commands below use the existing
`lightyear-judge` entrypoint; `python -m lightyear_judge.cli` is equivalent.

```text
lightyear-judge rule-check --mapping knowledge/mappings/carddemo-intcalc-executable.json --records public-records.json --judge-key operator/judge.pem --visibility public-development --output rule-receipt.json
lightyear-judge rule-replay --mapping knowledge/mappings/carddemo-intcalc-executable.json --records public-records.json --receipt rule-receipt.json --public-key operator/judge.public.pem --output replay.json
lightyear-judge rule-export --mapping knowledge/mappings/carddemo-intcalc-executable.json --records public-records.json --receipt rule-receipt.json --public-key operator/judge.public.pem --output exports
```

`rule-check` defaults to private visibility. Private receipts contain aggregate
counts, rule/source identifiers, and hashes, never record keys or values. Public
disagreements name the record key and output fields. Records are ordered JSON
objects with unique `key`, `input`, and `output`; sequence predicates additionally
receive `previous`, `next`, and `position`. The rule set, ordered records, and
evaluator implementation are bound into the receipt. Replay recomputes them.

To replay the checked-in public acceptance evidence, without the original SQL
capture archives or a Java build:

```text
python -B tools/replay_business_rules_demo.py
```

This verifies four rule receipts, the mutation signature, every artifact hash,
and the historical **test** Tower proof. The test public keys are not trusted
production authorities. No private key is distributed.

## Tower and candidate mode

`lightyear_business_rules.tower.write_request` accepts a public signed receipt,
its exact rule set and selected register rule, a trusted judge public key, and
an operator-selected Tower root/scope/proposer. It creates a request only;
it never grants roles or signs a decision. The Business Rules tab in the existing
decision console shows the receipt-backed catalogue. The existing review queue
records `preserve`, `fix`, or `investigate`, requiring an authorized business
owner with the matching workload grant, named owner, reason, and review date.
Named customer identities may hold that role.

After a decision, `rule-mode` takes the same mapping/records/receipt/public-key
arguments as replay, plus `--rule-id`, `--proof`, `--tower-public-key`,
`--tower-head`, `--tower-scope`, and a new `--output` file. The caller must obtain
the current authenticated Tower head. It verifies the proof and exact bindings
before emitting `source-faithful`, `corrected`, or `blocked`. For INTCALC's
`source-final-account` seed, `fix` maps to the existing Java policy `intended`.
The operator consumes this mode when preparing a candidate; it does not start
or change a running candidate. Other corrected behaviours require their own
implementation adapter. Private register ingestion is intentionally refused
until an authority-owned adapter is approved.

## Graph and exports

`build_graph(..., business_rules=True)` includes COBOL decision nodes and the
extension ontology returned by `business_rules_ontology()`. Validate that graph
against the extension ontology. The existing default ontology and historical
snapshot are unchanged. Rules without receipts remain `untested` in raw graphs.

The existing `graph-project` operator command optionally accepts all four of
`--rule-mapping` (repeatable), `--rule-records`, `--rule-receipt`, and
`--rule-public-key`. This extension requires field mode and a public-fixture
lane. Statuses require replay; executable constants must occur lexically in
approved source. The existing leak scan and Tower projection approval remain
required. Raw factory graph context strips executable/status fields. Confidential
projections retain their existing, stricter redaction policy. Default tool
interfaces are unchanged. Model-proposed rules remain quarantined and must be
reviewed and promoted through a separately approved workflow before use.

Exports include HTML/JSON, DMN 1.4 FIRST tables for the supported decision-table
subset, and public-only Given/When/Then records. Unsupported DMN expressions
fail closed. The XML is structurally tested; no third-party DMN engine import
has been certified.

## Rebuilding the public demo

`tools/business_rules_demo.py` requires a host JDK and the specifically approved
historical public SQL capture directory (`--public-tsql-captures`). It checks the
published source report/key hashes and authenticates saved native pairs before
reducing them to public scalar records. It compiles small Java mutations using
`javac`, with no Maven, Docker, database, model, or network invocation. It uses
a temporary test-only Tower authority and destroys its private keys. Respect
any active B06 load restriction before running it. Do not substitute private
customer/partner archives. The lightweight replay above needs neither a JDK
nor capture archives.

## Evidence strength

See the [evidence-strength milestone](evidence-strength-milestone.md) for per-rule old/new results. Agreement and evidence strength are distinct: exports and the Tower/graph catalogues mark weak verified rules explicitly. Plain verified totals count only discriminating rules; weak and not-assessed totals are separate. New signed assessments bind their original receipt and rule-scoped mutation report. Legacy receipts remain replayable using the byte-preserved v1 evaluator.

[New fixture catalogue](evidence-strength-v2/new-catalogue.html) · [old fixture reassessment](evidence-strength-v2/old-catalogue.html). Reference-model outputs are not legacy observations. Verification against Maintec mainframe outputs under separate authorization remains the ground truth; this work does not do it. The milestone's “What can be said publicly” section limits INTCALC claims to discriminating rules and preserves existing T-SQL claims.

Rebuild only outside a competing B06 native window, into NEW directories:

```text
python -B tools/build_discriminating_intcalc.py --output NEW_FIXTURE
python -B tools/rules_evidence_v2.py --output NEW_EVIDENCE --jdk JDK_ROOT
```

The evidence runner uses the checked-in fixture, compiles only small host Java variants and creates a disposable TEST authority. It never reads production signing authority or runs Docker. Do not replace historical evidence with regenerated outputs.

The corrected v2 assessment supersedes the preserved v1 extraction run. See the milestone for every rule’s old/new status and divergent/failure counts; four agreeing rules remain not-assessed because their mutation anchor or named output-field binding is unavailable.
