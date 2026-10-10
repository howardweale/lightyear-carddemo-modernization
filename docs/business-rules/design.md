# Business Rules design and inventory

The supplied October 9 specification described 34 curated rules across five
CardDemo workloads, including nine INTCALC rules. The implementation extends
those existing mapping records, adds one INTCALC emission rule, and adds five
public T-SQL procedure rules: 40 rules in total. Existing statement-only entries
remain valid and receive `untested` with `no executable form`. The executable INTCALC variant is generated from the original curated mapping
under `knowledge/mappings/carddemo-intcalc-executable.json` and selected explicitly.
Its rule IDs are unchanged. The default mapping and historical graph/evidence
snapshots remain byte-identical; no separate registry is introduced.

Howard authorized implementation and confirmed public-only agent statuses,
sequence predicates in scope, named customer approvers, and no partnership
agreement dependency. That last answer does not authorize reading private
partner data. This release uses only explicit public fixtures/captures. Optional
model drafting is not implemented or enabled.

## Language and trust boundaries

The language is bounded JSON data, never Python/JavaScript/SQL evaluation.
It supports expressions, ordered first-match decision tables with mandatory
else, record predicates, and ordered sequence predicates. Numeric arithmetic
uses exact fractions. Source PIC bindings determine receiving-field precision,
scale, sign, and overflow. Explicit assignment nodes encode intermediate COBOL
receiving fields; truncation is toward zero, and ROUNDED is half away from zero.
Edited PIC clauses and unsupported expressions fail closed. It is a deliberately
restricted COBOL arithmetic subset, not a general COBOL interpreter.

The deterministic evaluator returns verified, contradicted, untested, or
indeterminate. Unsupported/missing inputs cannot become passes. Existing
Ed25519 judge signing binds the rule set, ordered record content, evaluator
version, and implementation digest (source normalized only for Git CRLF/LF).
Replay rejects changed rules, records, signatures, or evaluator implementations.

Runtime-derived rule proposals are not source authority. Public graph statuses
are allowed only after replay and existing projection approval. Expected record
values are never attached to the projection. Private receipts contain counts
and hashes; public scenarios are refused for private receipts. Model-proposed
rules are excluded from exports, catalogue totals, and agent context.

## Public inputs and gaps

The INTCALC adapter reads stored before/after bytes from the repository's
`synthetic-public-rehearsal` fixture. It does not generate expected outputs from
the rule expressions. Fifty ordered records exercise fallback rates and zero
interest amounts. Direct disclosure-group selection and zero-rate suppression
are unexercised, so those two rules are untested. Synthetic evidence cannot
establish mainframe or native equivalence.

Five T-SQL procedures cover LEN trailing spaces, ISNULL result length, MONEY
scale, negative ROUND precision, and DATEDIFF day boundaries. Their rules are
anchored to hash-bound public SQL assets. Historical source/correct/wrong native
captures are authenticated against the published run-010 report and key, then
replayed using the existing native comparator. Only reduced public records and
receipt/hash bindings enter this package. No native run is launched.

## Coverage and mutations

The COBOL scanner records program, paragraph, construct, and line span for IF,
EVALUATE/WHEN, PERFORM UNTIL/VARYING, SEARCH, AT END, and INVALID KEY. It ignores
comments and literals. It is lexical coverage, not a control-flow theorem:
overlapping source anchors count as explained. Coverage is reported, not gated.

Mutations modify the modern Java implementation at exact reviewed anchors:
comparison boundary, rounding, operand order, dropped branch, and scale, plus
the one-cent smoke case and a codec scale case. A kill requires existing judge
comparison divergence naming a rule output. Compile failures refuse the run;
execution failures are retained separately and are not counted as kills.
Surviving mutations remain visible as data-coverage findings.

## Delivery limits

The acceptance Tower decision is made by a temporary demo customer under a
temporary test authority. It proves role, workload, signature, and hash-binding
enforcement; it is not Howard's or a customer's real keep/fix decision. Real
customer data ingestion, real corrected candidate runs, optional model drafting,
third-party DMN-engine certification, and B06 qualification are not claimed.
