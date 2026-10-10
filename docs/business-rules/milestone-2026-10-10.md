# Verified Business Rules implementation milestone — October 10, 2026

Implementation and offline acceptance are complete in the isolated
`codex/verified-business-rules` worktree, based on
`c4103b3e4a09c13deb580b233e2305f259729ecd`. Publication and merge require approval
of the final commit. B06 checkouts, frozen evidence, machine configuration,
Docker, and model endpoints were not changed or invoked.

## Results

| Check | Observed result |
| --- | --- |
| Focused evaluator, graph, projection, Tower and HTTP regression tests | 52 passed in 31.519 seconds |
| Toolkit compatibility regressions, including exact 10/16 tool schemas | 7 passed in 14.656 seconds |
| INTCALC executable rules | 10 signed statuses: 8 verified, 2 untested |
| Public T-SQL source / correct twins | 5 verified / 5 verified |
| Public T-SQL wrong twins | 5 contradicted |
| CBACT04C decision coverage | 16 of 47 explained (34.04%); all 31 gaps listed |
| Mutation rates | Seven verified service rules: 1/7 each; fixed-width codec rule: 0/1 |
| Monthly-interest one-cent mutant | Killed; named amount/account output fields diverged |
| Register seed | Signed test-customer `preserve` for source-final-account |
| Standalone public evidence replay | Four receipts, mutation signature and historical test Tower proof passed |
| Docker / model calls / qualification credit | 0 / 0 / none |

The direct disclosure-group and zero-rate rules are honestly untested. Most
mutants survive the limited fixture, and operand-swap produces an execution
failure that earns no kill. These findings prevent interpreting a verified
status as broad behavioural coverage.

The receipt content hash is
`e9584dca84b6da1cdfad80aa8edd3c76fb856dfd83070b1766d40e3f16a7b075`.
The INTCALC rule-set hash is
`00f6de34b1213e9a520ccc026e5bd8d4ea88fe010b786f413c4a4aacdd2f4019`.
The demo decision hash is
`278775d8deece0c9f6f980df34a03465a07c808fe9b4a78f40d8d1dbc36d3e26`.
[Artifact inventory](evidence/inventory.json) binds the 21 public acceptance
files, including records needed for offline replay. Only test public keys are
included; temporary private keys were destroyed.

## Delivered behaviour

Existing mapping extensions, exact numeric evaluation, sequence predicates,
signed checking/replay, COBOL decision coverage, modern Java mutation reports,
Tower catalogue/register and named-customer authorization, verified candidate
mode output, opt-in public graph enrichment, HTML/JSON/DMN/scenario exports, and
five public T-SQL rules are implemented. A dedicated lightweight offline CI job
replays the acceptance evidence. Remote CI has not run for this local commit.

The historical default graph/ontology and default-off Verify tool interfaces
remain unchanged. The integration does not arm, run, or authorize any B06
practice, census, qualification, or measurement. This is operator review of
public synthetic/historical evidence, not independent attestation.

## Remaining human decisions and external validation

The test-authority Tower proof satisfies the integration demonstration only.
Any production keep/fix decision must be made by an authorized human against
the exact production rule set and receipt. Publication and merge are separately
commit-specific. No private mLogica/customer batch is processed without explicit
data authorization. DMN XML is structurally checked; import into a particular
business-rules engine remains unclaimed.
