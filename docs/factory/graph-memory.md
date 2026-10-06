# Verified graph memory and routing

The features here are opt-in factory/Verify facilities. Campaign builders keep
their existing inputs and pinned models. Zero Docker and zero model calls were
used to implement and test these features. Operator review, not independent
attestation. No evaluation or routing-performance claim has been made.

## Annotation workflow

`factory/annotations/ledger.jsonl` is host-owned deployment data. Each event is
signed and linked to the previous event; replay derives state without changing
the canonical graph. Keep the ledger signing key, independent judge key and Tower
key separate, outside builder-readable directories. The ledger writer is a host
service, never an agent with direct signing-key access.

Create host-owned trust JSON with PEM **paths** for `ledger_key`, `tower_key` and
`judge_key`, plus `scope`, `inventory_sha256` and the current `trusted_head` obtained
from the Tower. Key contents are never copied into requests or agent contexts.
For the new scope, grant Howard's existing authenticated identity
`knowledge-approver` using the Console's local `grant-roles` administration CLI.
Do not give this role to service or agent identities. No live role was granted by
this implementation.

```powershell
lightyear-factory annotate --trust C:/secure/knowledge-trust.json --signing-key C:/secure/ledger.pem add --anchor legacy:cobol-paragraph:CBACT04C:1300-COMPUTE-INTEREST --type convention --customer carddemo-reference --review-after 2026-11-01 --text "Review the approved rounding convention before editing."
lightyear-factory annotate --trust C:/secure/knowledge-trust.json health
lightyear-factory annotate --trust C:/secure/knowledge-trust.json replay
```

The specification's `asserted-pending` is represented as **status proposed,
provenance observed** for operator input; the four-value provenance enum is kept.
Agent, repair and review imports remain inferred. No repeated text grants trust.

The judge-side `leak_certificate()` scans the complete annotation against the
private protected-value inventory and, for portability, private customer terms.
Only a safe signed certificate is exported: no matches, locations or values.
An implementer approval binds the annotation bytes and certificate bytes. Use
`annotate review-requests --tower-root ... --leak-checks ...` to publish exact
requests locally to Tower, then `annotate apply --event approve --payload ...`
with the returned proof and host-pinned current journal head. `reject`, `retire`
and `supersede` are events too; replacement content gets a new annotation ID.
There is no overwrite or silent repair of a damaged ledger.

Five distinct independently replayed passing runs on the same anchors, with no
matching-anchor failure, create eligibility and a `graph-annotation-verified`
request. A person still decides. More than 20% failures over at least five runs
flags the annotation. Flagged and expired entries are excluded by retrieval.
These outcome associations are **correlation, not causation**.

`KnowledgeService.sync()` (also `annotate sync --input ... --tower-root ...`)
imports verified normalization/attempt-review decisions into inferred proposals,
ingests independent judge replay attestations bound to the exact run receipt and
context, and emits eligibility/flagged review requests. Repeated imports are
idempotent; conflicting outcomes are refused. Call it after judge replay, not on
the basis of an agent's verdict. Its input bundle stays host-private, including
protected-value watch lists. It never creates or signs a judge attestation.

The judge attestation schema is `annotation-outcome/1`: signed by the configured
judge key, with `evaluation_class=public-calibration`, `independently_replayed`,
`run_id`, `run_receipt_sha256`, `customer_id`, `status`, affected `anchors`, and
`context` containing `annotation_ids` and `full_context_sha256`; `context_sha256`
hashes that context object. Sealed holdouts are rejected. Repair proposals accept
only the enumerated closed categories and generic text; no patch is imported.

`annotate import-reviews --repository owner/repo --pr NUMBER --source-commit SHA
--graph projection.json --proposal proposal.json` uses read-only `gh api`. Only
right-side comments at the specified commit, mapped to known file/line ranges,
are proposed. Comments are untrusted inferred text, bounded to 600 characters.
They require the same leak scan and human approval as any other proposal.

Factory integrations can call `annotation_tools.propose()` as their write tool;
it refuses Verify, campaign and sealed-holdout execution kinds. Verify MCP exposes
only the read-only `graph_guidance` tool and never registers this write operation.

## Context and search

The old context schema 1.0 and default lexical behavior are preserved. To enable
annotations use work-order metadata `context_schema: "1.1"` and `customer_id`, and
`lightyear-factory run --approved-projection binding.json`. The host-owned binding
contains a projection directory, Tower proof and trusted keys/head. Schema 1.1
loads only that approved projection. Annotated factory runs exclude the older
global semantic-memory projection. The run receipt binds included IDs and the
context hash. Planner/builder role projections preserve the binding.

Build a fresh projection using the existing judge `graph-project` command with
`--annotation-ledger`, `--annotation-trust` and optionally `--hybrid`. Follow with
the existing **full** `graph-leak-check` and Tower projection approval. Annotations
and the complete search index are inside `projection.json.gz`, so the manifest,
leak certificate and Verify receipt's `context_projection_sha256` cover both.
Regenerate/reapprove projections after ledger changes. An immutable projection
is a reviewed snapshot, not a live view of later outcomes; revoke its approval
and reload the reader when guidance is retired or flagged. Hosts must refresh
Tower heads, not accept a head supplied by an agent.

Guidance includes node anchors or CONTAINS ancestors, ordered by specificity,
verified/asserted provenance and observed outcome strength, capped at 4 KB.
`inspector_private`, expired and flagged entries are excluded. Inferred material
requires **both** an operator-approved projection built with `--include-inferred`
and the work order's `include_inferred_annotations: true`; Verify guidance always
excludes inferred items.

`graph_search(mode="hybrid", anchor=...)` combines deterministic BM25, local
feature-hash vector ranking and graph distance using reciprocal ranks. Results
carry lexical matches, a similarity bucket, graph paths and exact source ranges.
The default vector provider is an explicitly versioned vocabulary/feature-hash
baseline, **not** a pretrained embedding model; semantic quality beyond the
public acceptance query remains unmeasured. It downloads nothing. The provider
protocol admits separately configured implementations; external embedding needs
a customer/mode-bound Tower proof and is always forbidden in confidential mode.
The bundled Verify reader uses only the local provider and refuses an index
requiring an unconfigured provider.

## Providers, matrix and routing

`additional_providers.AnthropicMessagesProvider` and `GeminiProvider` implement
the same structured-result contract as OpenAI and run behind
`BoundedModelProvider` through the opt-in `AccountedModelProvider` subclass.
The original provider module remains byte-identical to its historical
calibration binding. Model identifiers and positive prices are configuration;
credentials come from `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` or `OPENAI_API_KEY`.
Malformed/refused/truncated output is a result error and cannot trigger fallback.
Transport failures retain call evidence and are conservatively charged against
the shared budget. This can overestimate failed-call cost; it is deliberately
not a billing claim. No provider API was called during tests.

`lightyear-factory run --provider configured --model-config host.json` uses
`model_config.load_router`. The JSON has `models` (configuration ID → provider,
model, input/output USD per million and max output tokens), `default`, optional
`policy`, `matrix_receipt`, `approval` proof and host `trust`. Raw credentials are
refused. The existing hardened executor needs a dedicated secret-store adapter
for these providers; the CLI fails closed rather than reusing its OpenAI lease.

`evaluation_matrix.run_matrix()` requires an exact commit-specific Tower campaign
authorization binding the matrix, models, dollar budget and public commit. The
trust config pins Howard's operator ID. Every cell invokes the existing
`run_model_evaluation`; sealed catalogs use the existing authenticated envelope.
No implicit retries or resume are permitted. Task type describes the cell's
work objective, not isolated skill at a single role. Receipts bind catalog,
evaluation, runs and each model-call record; missing/mismatched evidence fails.
Metrics include pass rate, first-attempt passes, false accepts, tokens/cost per
verified task, run wall time, separate elapsed model time and closed categories (holdout categories stay
private). Runtime/mainframe qualification remains a separate claim.

`factory/routing/policy.json` ships with no routes. A route only takes effect with
a Tower `model-routing-policy` decision backed by the matrix and a review date at
most 90 days from issue. Otherwise the single default model is used. Routes name
primary/fallback configuration IDs and supporting matrix receipt hashes. Fallback
is only for provider errors, uses the **same** budget and never follows a failed
business verdict. Every choice is recorded in the factory receipt. Campaign code
does not import or invoke this router.

API references used for implementation (offline fixtures are not live validation):
[Anthropic structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)
and [Gemini structured outputs](https://ai.google.dev/gemini-api/docs/structured-output).

## Tower and parallelism

Tower's Graph memory tab uses the existing review and decision paths, including
bulk review with one authenticated, hash-bound decision per item. Status is an
optional signed `factory-knowledge-status/1` export generated by `annotate
status-export`; configure `factory/knowledge-console.json` with `scope`, relative
`status_file` and `public_key`. To reveal proposal text, also pin
`judge_public_key` and `inventory_sha256`. Verified-promotion requests use the
optional `annotation_certificates` map (annotation ID to relative certificate
path). Without a matching, signed, eligible leak certificate, the review is
hash-only. It reports provenance/status counts, flagged and
expiring entries, routing usage and search index/provider identities. Status is
informational; admission always verifies the underlying proofs.

No production parallel runner was added. See [the queue seam](specs/parallel-work-queue.md).
