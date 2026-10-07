# T-SQL procedure verification: native implementation milestone

October 7, 2026. Operator review; not independent attestation.

Implemented ScriptDom inventory, native SQL Server/PostgreSQL adapters, fresh
backup/template resets, all-table and protocol capture, signed evidence and
database-free replay. The public corpus covers 42 procedures and 25 trap families.
Explicit asset-bound mappings and native procedural coverage are implemented.
The three return-contract twins have prospective corrections with new evidence;
all original failures and source bundles remain preserved.

The latest approved-VM run completed 100 pairs: 36 equivalent, 40 divergent,
24 insufficient-evidence. All 40 non-policy wrong twins were rejected. All 100
final pairs and seven native collector controls passed independent offline replay;
owned-resource cleanup was verified. The scoped offline suite passed 73 tests.
Zero model calls; no Windows Docker or B06 resource use.

**This is implementation progress, not completed M0 qualification.** Four correct
twins match observations but lack sufficient coverage proof; twenty repeated
ambiguous-choice policy cases remain held. Customer policies, certificate release,
security/concurrency/performance claims and the reset-only benchmark remain open.

- [Native results, costs, limitations and full hashes](../data-modernization/tsql-procedures/coverage-results.md)
- [Every pair's verdict, coverage and manifest hash](../data-modernization/tsql-procedures/coverage-results-summary.json)
- [Coverage and mapping contract](../data-modernization/tsql-procedures/coverage-and-mappings.md)
- [Historical original native results](../data-modernization/tsql-procedures/native-results.md)

Publication contains implementation, authored public fixtures and hash-only result
summaries. Raw archives, database captures, VM credentials and recorder private
keys are excluded. CI repeats the offline public-fixture suite on Linux and Windows;
it does not launch native database qualification or call a model.
