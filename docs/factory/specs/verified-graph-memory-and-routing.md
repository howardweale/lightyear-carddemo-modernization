# Spec: verified graph memory, hybrid search and evidence-based model routing

**Status:** approved in principle by Howard, October 6, 2026. Implementation starts after the B06 launch.
**Suggested repo path:** `docs/factory/specs/verified-graph-memory-and-routing.md`
**Depends on:** `docs/verify/specs/graph-context-tools.md`, which provides the graph projection, leak check and read-only graph tools.
**Owner:** Codex. Review: Howard (operator review; not independent attestation).

## 0. Why, and what we deliberately do differently

Competitors describe four capabilities:
1. a "self-reinforcing" knowledge graph that stores feedback and conventions on the code nodes they apply to;
2. swarm orchestration at massive scale;
3. hybrid graph and vector navigation;
4. multi-model routing backed by private evaluations.

Lightyear builds 1, 3 and 4, with one principle that sets us apart: **nothing becomes trusted memory because it was repeated; it becomes trusted because a person approved it and the independent judge's outcomes don't contradict it.** "Self-reinforcing" without verification also reinforces mistakes. Ours is **self-verifying**.

Capability 2 (tens of thousands of agents) is **out of scope**. Our throughput limit is verification capacity (native runs, Docker hours, evidence and replay), not generation. Section 6 only defines a seam for modest, verification-bounded parallelism.

## 1. Hard constraints (apply to every phase)

1. **No impact on calibration campaigns.** Do not modify B05/B06 files, the B06 builder boundary, `template-r1`, `work/ms94`, or any `tools/ms94_b06_*`, `tools/ms94_builder_mcp*` or `tools/journey_builder_mcp.py` file. Campaign builders never receive annotations, hybrid search or routed models. Campaigns pin one client and one model.
2. **Zero model calls** in implementation and tests. Evaluation runs (Phase 3) need Howard's commit-specific approval with a stated budget.
3. **Zero added leakage.**
   - Anything shown to an implementing agent passes the graph-projection policy and leak check from the dependency spec.
   - Sealed-holdout content never enters memory. Keep the existing `SEALED_CLASS` exclusion.
   - Annotations derived from judge outcomes carry only closed diagnostic categories and node IDs, never values.
4. **Provenance is mandatory.** Every annotation carries one of `observed`, `asserted`, `inferred` or `verified`. Only Control Tower decisions can move an annotation to `asserted` or `verified`. Agents can only propose `inferred`.
5. **Canonical graph identity doesn't churn.** Annotations live in their own append-only, content-addressed ledger and are joined to graph nodes when read, the same way runtime evidence is joined today. They never mutate `graph.snapshot.json.gz`.
6. **Customer isolation.** Every annotation has a `customer_id`. Retrieval never crosses customers unless an annotation is explicitly published as `portable` through a Tower decision, and then only after private terms are removed.

## 2. What exists today (build on it, don't duplicate)

- **Graph and explorer:** `knowledge/`, and `src/lightyear_knowledge_graph/explorer.py` (`search`, `node`, `neighborhood`, `trace`, audience filtering).
- **Context assembly:** `src/lightyear_factory/context.py` (`GraphContextAssembler`, role projections, `attach_semantic_memory`).
- **Semantic memory:** `src/lightyear_factory/memory.py` stores verified experiences, lessons, edit templates and negative memory, with a 24 KB cap and sealed holdouts excluded. It is retrieval-scored and global, **not anchored to nodes**.
- **Portfolio orchestration:** `src/lightyear_factory/portfolio.py` (`plan_portfolio`, graph-distance conflict detection, `PortfolioRunner`).
- **Providers and evaluations:**
  - `src/lightyear_factory/providers.py` (the `ModelProvider` protocol, `OpenAIResponsesProvider`, `BoundedModelProvider` budgets);
  - `src/lightyear_factory/evals.py` (`run_model_evaluation`, public-calibration and sealed-holdout classes, leak checks, receipts).
- **Control Tower:** `src/lightyear_control_tower/kinds.py` (closed decision-kind registry).

## 3. Phase 1: verified graph annotations (the "self-verifying" memory)

### 3.1 Data model

`factory/annotations/ledger.jsonl` is append-only. Each line is a signed event: `create`, `approve`, `reject`, `retire`, `supersede` or `outcome`. The current state is derived by replaying the ledger. The annotation shape:

```json
{
  "id": "ann:<sha256 of canonical body>",
  "customer_id": "carddemo-reference",
  "anchors": ["legacy:cobol-paragraph:CBACT04C:1300-COMPUTE-INTEREST"],
  "scope": "node | subtree | workload | customer",
  "type": "convention | pitfall | review-finding | decision | preference",
  "text": "≤ 600 chars, plain language, no data values",
  "source": "human-review | code-review | tower-decision | judge-outcome | factory-run | agent-proposed",
  "provenance": "observed | asserted | inferred | verified",
  "evidence": [{"kind": "receipt|pr-review|tower-decision|run", "sha256": "..."}],
  "visibility": "implementer | inspector_private",
  "portable": false,
  "review_after": "YYYY-MM-DD",
  "created_by": "operator | agent:<role>"
}
```

- `subtree` scope applies to the anchor and everything it `CONTAINS`. For example, a program-level convention applies to all its paragraphs.
- The `text` must pass the leak check before it can be approved for implementer visibility.

### 3.2 Where annotations come from

1. **Operator CLI:** `lightyear-factory annotate add --anchor … --type convention --text …`. This creates a `proposed` annotation with provenance `asserted-pending`.
2. **Control Tower decisions.** Approved `verify-normalization`, `normalization` and `verify-attempt-review` decisions automatically **propose** annotations anchored to the affected nodes. The decision's reason becomes the text, after the leak check.
3. **Repair outcomes.** When a run resolves a closed diagnostic category on a node, for example `candidate-runtime-exception`, `posting-sequence-misuse` or a divergent field, propose a `pitfall` with provenance `inferred`. It holds the category, the node ID and a short generic description, with no values and no patch text.
4. **Code review import (phase 1b).** Import GitHub PR review comments on modernized code with `gh api`, map them to nodes by file and line using the graph's source ranges, and propose them as `review-finding` annotations with provenance `inferred`.
5. **Agent-proposed.** Agents may propose annotations through a write tool **only in factory runs, never in Verify or campaign runs**. These stay `inferred` until a person approves them.

### 3.3 Promotion and demotion (the governor)

- **`proposed` → `asserted`:** a Tower decision `graph-annotation` with outcome `approved`. Required fields: reason, `named_owner`, `review_after`.
- **`asserted` → `verified`:** automatic *eligibility*, then a human decision. An annotation becomes eligible when it was in context for at least **N = 5** independently verified passing runs on its anchors, and **zero** failing runs whose closed diagnostic touches the same anchors while it was in context. Eligibility creates a Tower request; a person makes the change.
- **Demotion:** if the failure-after-apply rate on an annotation's anchors exceeds 20% over at least 5 runs, mark it `flagged`. Retrieval excludes flagged annotations and a Tower review is requested. Annotations past `review_after` are also excluded until re-approved.
- **Outcome attribution:** every run's context package records the IDs of annotations it included, hashed into the run receipt. The judge's outcome writes `outcome` events to the ledger keyed by those IDs. **This is correlation, not causation. Record it that way and never auto-promote on it.**

### 3.4 Retrieval (proximal, bounded)

- **`GraphContextAssembler`:** add an `annotations` section behind a version flag (`context_schema 1.1`). The default stays 1.0 so existing qualification runs reproduce.
  - **Which annotations:** those whose anchors are in the approved roots, or are ancestors of them through `CONTAINS`.
  - **Order:** scope specificity (node, then subtree, then workload, then customer), then provenance (verified, then asserted; inferred never included unless the order opts in), then outcome strength.
  - **Cap:** 4 KB, with a `truncated` flag.
- **Verify graph tools:** add a sixth read-only tool, `graph_guidance(node_id)`. It returns approved annotations for that node and its ancestors, with the same ordering and cap, and only those included in the approved projection. In other words, annotations go through the same projection and leak check as the rest of the graph.
- **Exclusions:** `inspector_private` and `sealed-holdout` items are never included.

### 3.5 Phase 1 tests (offline)

- Ledger replay is deterministic. Tampered or out-of-order events are rejected.
- Leak check: a planted reference value in the text blocks approval for implementer visibility.
- Retrieval: ordering, the scope rules (subtree through `CONTAINS`), the 4 KB cap, and exclusion of flagged, expired and inferred annotations by default.
- Promotion: eligibility after N passes; a failure on the same anchors blocks it. Demotion at the threshold. There's no path to `verified` without a Tower decision.
- Customer isolation: no cross-customer retrieval unless `portable` was approved.
- Context schema 1.0 output is byte-identical to today.

## 4. Phase 2: hybrid search (lexical, vector and graph)

### 4.1 Index

- Build a **search index over the approved projection only**: node names, `statement` text, source excerpts and approved annotation text.
- **Lexical:** BM25, deterministic, standard library or a small vetted dependency.
- **Vector (optional, pluggable):** an `EmbeddingProvider` protocol. The default implementation is **local**, so no customer text leaves the environment. Any external embedding API needs a Tower decision (`embedding-provider-approval`) per customer and mode. In confidential mode, external embeddings are forbidden.
- The index files are content-addressed. The index hash is recorded in the projection manifest and in Verify receipts (`context_projection_sha256` covers it).

### 4.2 Query

- `graph_search` gains `mode: lexical | hybrid` (default `lexical`) and `anchor: node_id` (optional).
- **Hybrid scoring:** a reciprocal-rank fusion of BM25 and vector rank, re-ranked by graph distance from the anchor (CALLS, CONTAINS, USES_COPYBOOK, HAS_FIELD, READS, WRITES).
- Each result includes `why`: lexical terms matched, vector similarity bucket, graph path to the anchor. The results then resolve to exact nodes and line ranges, so the vector side only gives direction and the graph and source give the truth.

### 4.3 Phase 2 tests

- The index is deterministic for the same inputs and provider version.
- No index content comes from outside the projection.
- Confidential mode refuses non-local providers.
- On the public CardDemo graph, `hybrid` search for "monthly interest on account balance" returns the `CBACT04C` interest paragraph in the top 3. `lexical` search is unchanged by default.
- Response caps and pagination behave the same as in the graph-tools spec.

## 5. Phase 3: provider-neutral evaluations and evidence-based routing

### 5.1 Providers

- Implement `AnthropicMessagesProvider` and `GeminiProvider` alongside `OpenAIResponsesProvider`, all behind `BoundedModelProvider`, with the same call, byte, token and cost limits and the same model-call evidence records.
- **Model identifiers are configuration, never hard-coded.** Credentials come from the environment or a secret store, never from the repo.

### 5.2 Evaluation matrix

- **Task types:**
  - `plan`
  - `implement`
  - `repair-from-closed-diagnostic`
  - `review`
  - `normalization-proposal`
- **Workloads:** INTCALC, POSTTRAN, CREASTMT and ACCTPL1 (the existing qualification cells).
- **Classes:** public-calibration and sealed-holdout (existing).
- **Metrics:**
  - pass rate within the attempt budget;
  - first-attempt pass;
  - false-acceptance (must be 0);
  - tokens and cost per verified task;
  - wall time;
  - closed-diagnostic categories hit.
- Each cell produces an evaluation receipt using the existing `run_model_evaluation` path. A matrix receipt aggregates them and binds every run, model-call record and catalog hash.
- **No run happens without Howard's commit-specific approval of the matrix, the models and a dollar budget.**

### 5.3 Routing policy

- `factory/routing/policy.json` maps each task type to a primary and a fallback model (configuration identifiers). Each entry cites the matrix receipt hashes that justify it.
- A routing policy only takes effect after a Tower decision, `model-routing-policy`, is approved, with `review_after` no more than 90 days out. An expired policy falls back to the single default model.
- **Router:** chooses by task type, records `{task_type, model, policy_sha256}` in each run receipt, and falls back only on provider errors, never on bad results. Retries for bad results are the judge's attempt budget, not model-shopping.
- **Calibration campaigns never use the router.**

### 5.4 Phase 3 tests (offline, with fake providers)

- Each provider honours the `BoundedModelProvider` limits and produces correct evidence records, using recorded fixtures with no network.
- Routing:
  - an unapproved or expired policy means default-only;
  - the receipt records the choice;
  - fallback happens on provider error only.
- Matrix aggregation rejects any run missing a model-call record or with a catalog mismatch.
- Sealed-holdout results never enter annotations or memory.

## 6. Phase 4 (deferred): verification-bounded parallelism (seam only)

Do **not** build swarm orchestration. Define only the seam:
- a durable work queue in the factory store, with leases, heartbeats and idempotent claims;
- conflict detection using `portfolio.py` graph distances;
- a global concurrency limit equal to available **verification** capacity (native runner slots), not model capacity.

Target: tens of parallel work orders. Write the design note `docs/factory/specs/parallel-work-queue.md` and an interface with an in-memory implementation and tests. No production runner.

## 7. Control Tower changes

Add these decision kinds to `kinds.py`. No change to any B06 kind or flow.

```python
K("graph-annotation", ("approved", "rejected", "retired"),
  ("knowledge-approver",), ("annotation", "leak_check"),
  required_fields=("reason", "named_owner", "review_after"),
  consumer="factory-annotation-ledger"),
K("graph-annotation-verified", ("verified", "rejected"),
  ("knowledge-approver",), ("annotation", "outcome_summary"),
  required_fields=("reason",), consumer="factory-annotation-ledger"),
K("embedding-provider-approval", ("approved", "rejected"),
  ("campaign-authorizer",), ("provider", "customer", "mode"),
  required_fields=("reason", "review_after"), consumer="hybrid-index-build"),
K("model-routing-policy", ("approved", "rejected"),
  ("campaign-authorizer",), ("policy", "matrix_receipt"),
  required_fields=("reason", "review_after"), consumer="factory-model-router"),
```

- **New role:** `knowledge-approver`. Map it to Howard initially.
- **Annotation review queue:**
  - shows proposed, eligible-for-verified and flagged annotations, each with its anchors (linked to the graph explorer), source, evidence and leak-check result;
  - lets the reviewer approve, reject or retire in bulk.
- **Annotation health:** counts by provenance and status, flagged items, expiring items, and failure-after-apply rates.
- **Routing card:** the active policy, its review date, the receipts behind it, and the share of runs per model.
- **Search card:** the index hash per projection, and the embedding provider and its approval.

## 8. Deliverables and sequencing

| Phase | PRs | Target | Model calls |
|---|---|---|---|
| Prerequisite | Graph context tools (separate spec) | Oct | 0 |
| 1 | Annotation ledger and CLI; Tower kinds and queue; assembler 1.1; `graph_guidance` tool; proposals from Tower decisions and repairs | Nov | 0 |
| 1b | GitHub review-comment import | Nov | 0 |
| 2 | BM25 index, `EmbeddingProvider` (local default), hybrid `graph_search` | Nov–Dec | 0 |
| 3 | Anthropic and Gemini providers, matrix aggregation, router and Tower kind | Dec | 0 to build; evaluation runs need separate approval and budget |
| 4 | Design note and queue interface only | Later | 0 |

Each PR states:
- zero Docker and zero model calls (unless separately approved);
- no B05/B06 or frozen-path changes, enforced by a CI check on protected paths;
- operator review, not independent attestation.

## 9. Non-goals

- Swarms of thousands of agents. Generation without matching verification capacity only produces unverified code faster.
- Agents writing trusted memory directly. Agents can only propose `inferred` annotations.
- Cross-customer learning by default. Only Tower-approved `portable` annotations, with private terms removed.
- Routing inside calibration campaigns.
- Treating annotation-outcome correlation as causal proof. Causal claims need a pre-registered on/off comparison, using the A/B framework from the graph-tools spec.
