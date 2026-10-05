# Spec: graph context tools for Lightyear Verify

**Status:** approved for implementation by Howard, October 5, 2026
**Suggested repo path:** `docs/verify/specs/graph-context-tools.md`
**Owner:** Codex. Review: Howard (operator review; not independent attestation).

## 1. Purpose

Give any AI agent using Lightyear Verify **just-in-time, read-only access to the modernization knowledge graph**. Instead of loading large inputs up front, the agent asks targeted questions while it works:
- "what is this field?"
- "which paragraphs read or write it?"
- "what does this program call?"

Two goals:
1. **Faster, cheaper repair.** When the judge names a divergent field, the agent can find the code that computes it without pulling raw records. In the October 4 Claude Code test, `decode_records` consumed 54% of the agent's usage.
2. **Product differentiation.** The graph tags every fact with its provenance (observed, asserted, inferred or verified) and carries a verification layer. Agents see not only what the code says but what has been proven.

## 2. Hard constraints (non-negotiable)

1. **No B06 impact.** Do not modify any `tools/ms94_b06_*` file, `tools/ms94_builder_mcp*`, `tools/journey_builder_mcp.py`, the B06 builder boundary, `template-r1`, B05 evidence or `work/ms94`. The B06 builder's capabilities stay frozen. Work on a separate branch. Run no Docker and touch no B06 files during B06 Docker windows.
2. **Zero model calls** in implementation and tests. Any live agent test (section 9) needs Howard's commit-specific approval.
3. **Zero added leakage.** The agent may only see a **projection** of the graph that contains nothing it couldn't already legitimately see: structure and approved source. No legacy runtime outputs, expected values, holdouts, reference records, test oracles, value samples or distributions, and nothing marked `inspector_private`. The published leakage bound (about 2,046 bits in field mode, under 26 bits in confidential mode over 5 attempts) must stay unchanged, and the spec must say why it does.
4. **Off by default.** If no approved projection is configured, the graph tools are **not registered at all**, so the tool list is identical to today's 10 tools and existing smoke results stay valid.
5. **Agent side holds no secrets.** The toolkit loads only the approved projection file. It never contacts the knowledge graph source, the evidence pack or the judge's private data.
6. **Maintec and private customer data** never enter a projection or a published artifact. Only hashes are published.

## 3. Current state (for orientation)

- The graph lives in `knowledge/`. `graph.snapshot.json.gz` holds 11,336 nodes and 13,491 edges for CardDemo, with the ontology in `knowledge/ontology/relationships.json` and the evidence pack in `knowledge/evidence/source.pack.json.gz`.
- `src/lightyear_knowledge_graph/explorer.py` → `GraphExplorerIndex` already provides `search`, `node`, `neighborhood` and `trace`. It has audience filtering (`implementer` hides `inspector_private`) and `customer_id` scoping. **Reuse it; don't write a second graph engine.**
- `src/lightyear_factory/context.py` → `GraphContextAssembler` builds up-front context packages. It stays unchanged.
- The Verify agent-side toolkit is `src/lightyear_toolkit/mcp.py` (10 tools). The judge is `src/lightyear_judge/` (separate OS user). Control Tower kinds are in `src/lightyear_control_tower/kinds.py`.

## 4. Design overview

```
Operator side (trusted)                          Agent side (no secrets)
------------------------                         -----------------------
knowledge graph + evidence pack
   │  lightyear-verify graph-project  (policy, lane, mode)
   ▼
projection.json.gz + manifest  ──► leak check (as judge user, vs lane reference)
   │                                   │
   └──────► Control Tower decision: verify-graph-projection (approved)
                                       │
           judge records approved projection hash in every receipt
                                       │
                                       ▼
                         toolkit verifies manifest + Tower proof at start,
                         then serves 5 read-only graph tools from the projection
```

## 5. Part A: projection builder and leak check (operator side)

### 5.1 Projection policy (`verify/graph-projection-policy.json`, versioned and hashed)

Deny by default, with explicit allowlists:
- **Node kinds allowed (both modes):** `source_file`, `cobol_program`, `cobol_paragraph`, `cobol_field`, `copybook`, `cobol_file_handle`, `jcl_job`, `jcl_step`, `jcl_dd_name`, `jcl_dd_allocation`, `dataset`, `vsam_cluster`, `vsam_component`, `vsam_path`, `vsam_alternate_index`, `cics_transaction`, `cics_program_resource`, `cics_file_resource`, `cics_command`, `bms_map`, `bms_mapset`, `bms_field`, `db2_table`, `db2_column`, `db2_constraint`, `db2_index`, `db2_dcl`, `db2_sql_statement`, `ims_*` structural kinds, `assembler_*` structural kinds, `java_type`, `java_method`, `modernization_workload`, `business_rule`.
  - `business_rule` only where the rule's provenance is `observed` from source, or `asserted` in a reviewed mapping. Never rules derived from runtime observation.
- **Node kinds always excluded:** anything from the operational/runtime layer (`executions`, `traces`, `observed outputs`), `verification_scenario` expected values, `test_case` bodies that embed expected values, any node or property marked `inspector_private`, and any node whose provenance chain includes runtime capture or reference data.
- **Relations allowed:** the structural ones (`CONTAINS`, `CALLS`, `USES_COPYBOOK`, `HAS_FIELD`, `READS`, `WRITES`, `READS_WRITES`, `EXECUTES`, `HAS_DD`, `ALLOCATES`, `ISSUES*`, `USES_*`, `STARTS_PROGRAM`, `REFERENCES_COLUMN`, `WRITES_TABLE`, `IMPLEMENTED_BY`, `RESOLVES_TO`, `DEPENDS_ON`, `DECLARES`, `BINDS`, `HAS_RULE`). `VERIFIED_BY` is allowed only as a bare edge to a scenario **id**, with no expected values.
- **Property allowlist** per node kind: id, kind, name, `statement` (source text), line range, PIC/usage/length for fields, provenance tag, `customer_id`. All other properties are dropped.
- **Source excerpts:** only from files the lane already exposes to the agent, capped at 120 lines per excerpt.
- **Modes:**
  - `field`: everything above.
  - `confidential`: structure only. Source excerpts only for the program(s) in the lane. Node `name`s kept. Any literal values in `statement` text that match the leak check's watch-list are redacted (section 5.3).

### 5.2 CLI

```
lightyear-verify graph-project \
  --graph knowledge/graph.snapshot.json.gz \
  --evidence knowledge/evidence/source.pack.json.gz \
  --policy verify/graph-projection-policy.json \
  --lane <lane-id> --mode field|confidential --customer-id <id> \
  --out <new-dir>
```

**Output:**
- `projection.json.gz`: deterministic and sorted.
- `projection-manifest.json`, which records:
  - the hashes of the graph, evidence pack, policy and projection;
  - the lane, mode and `customer_id`;
  - included counts by kind and relation;
  - excluded counts by reason;
  - `model_calls: 0`.

  It is signed with the existing operator key.

**Rules:**
- Refuse to overwrite an existing output directory.
- The same inputs must produce byte-identical output.

### 5.3 Leak check (runs as the judge user)

```
lightyear-verify graph-leak-check --projection <dir> --lane <lane-id>
```

- Builds a watch-list from the lane's reference outputs and private inputs: string tokens of 6 or more characters, numbers with 4 or more significant digits, and dates/timestamps.
- Scans every string in the projection.
- Writes `leak-check.json`: watch-list size, matches with node id, property and **hash of the matched value only** (never the value), and pass/fail.
- **Any match fails the check.** A match whose value also appears verbatim in approved source (a literal constant in COBOL, for instance) is reported as `source-literal` and **still needs explicit operator approval** through the Tower decision. It is never auto-accepted.
- The watch-list and raw values stay on the judge side. The output contains hashes and counts only.

## 6. Part B: agent-side graph tools (toolkit)

Add to `src/lightyear_toolkit/`, registered **only if** `--graph-projection <dir>` and `--graph-decision <proof.json>` are supplied and both verify at startup:
- the manifest signature;
- the projection file hash;
- the Tower decision `verify-graph-projection` with outcome `approved`, bound to the projection, policy, leak-check and lane hashes;
- the review date not passed.

If any check fails, the server starts **without** graph tools and logs one line saying why.

All tools are read-only (`readOnlyHint=True`, `openWorldHint=False`) and return compact JSON. Size rules:
- **Default response cap:** 8 KB. **Hard cap:** 32 KB.
- Lists are paginated with an opaque `cursor`.
- Every response includes `projection_sha256` and a `truncated` flag.

| Tool | Arguments | Returns |
|---|---|---|
| `graph_search` | `query: str`, `kind: str = ""`, `limit: int = 10` (max 25), `cursor` | id, kind, name, one-line summary, provenance |
| `graph_node` | `node_id: str`, `include_source: bool = false` | allowlisted properties, provenance, optional source excerpt (capped) |
| `graph_neighbors` | `node_id`, `relations: list[str] = []`, `direction: in\|out\|both`, `depth: 1\|2`, `limit: int = 25`, `cursor` | edges (relation, direction, neighbour id/kind/name) |
| `graph_references` | `node_id` (a field or copybook field) | paragraphs/programs whose approved source text references the field name, with line ranges. Provenance `observed (lexical)`; capped at 50 |
| `explain_divergence` | `attempt_id` | For each field the **verdict already named** (read via the existing judge client), the matching graph node(s), their copybook, and the paragraphs that reference them. Built only from the agent-visible verdict plus the projection, so it adds no information about values |

**Implementation notes:**
- Build on `GraphExplorerIndex` with `audience="implementer"`, pointed at the projection instead of the full snapshot. If the explorer can't load a projection directly, add a small loader. Do not fork the search logic.
- `explain_divergence` must work in confidential mode, where the verdict names only the output file. In that case it returns the file's record layout (copybook) and the paragraphs that write to that file, nothing more.
- Write a local, append-only query log (tool, arguments hash, response bytes, timestamp) in the agent workspace. It is **informational and untrusted** and never used as evidence.

**Also in scope: `decode_records` paging.** Add `offset`, `limit` (default 50, max 200), `fields: list[str]` (projection) and `summary: bool` (counts, min/max and distinct counts per field instead of records). The default behaviour change must be backward-compatible for existing smoke scripts. If it can't be, keep the old default and document the new parameters.

## 7. Part C: judge receipts

- The operator configures the approved projection hash per lane in the judge's lane config.
- Every receipt (public and signed) gains `context_projection_sha256`, or `null` when graph tools are off.
- Replay must verify the field is present and matches the lane configuration in force at the time of the attempt.
- Bump the receipt schema version. Older receipts stay valid with `null` implied.

## 8. Control Tower changes

**Yes, three small changes. No change to any B06 kind or flow.**

1. **New decision kind** in `kinds.py`:

   ```python
   K(
       "verify-graph-projection",
       ("approved", "rejected"),
       ("qualification-approver",),
       ("projection", "policy", "leak_check", "lane"),
       required_fields=("reason", "named_owner", "review_after"),
       consumer="verify-toolkit-graph",
   )
   ```

   - The request evidence includes the manifest's included and excluded counts and the leak-check summary (hashes only).
   - Any `source-literal` matches must be listed so the operator approves them knowingly.
   - Expiry follows `review_after`. After that date the toolkit stops registering the graph tools until a new decision is made.

2. **Lane status card** (Verify view):
   - projection state: none / pending / approved / expired / rejected;
   - projection hash, mode, node and edge counts, excluded counts and leak-check result;
   - a link to the decision.

3. **Attempt detail:** show the receipt's `context_projection_sha256` next to the verdict, so a reviewer can see what context the agent had.

Out of scope for v1: Tower display of agent-side query usage, which is untrusted.

## 9. Measurement plan (zero-model prep only in this PR)

Add `docs/verify/specs/graph-context-ab.md`: a pre-registered comparison to run later, with Howard's approval.

- **Arms:** the same lanes and tasks, with graph tools **off** (today's 10 tools) and **on** (10 + 5, plus `decode_records` paging).
- **Agents:** Claude Code first; then ADK once its live test passes.
- **Metrics:** attempts to pass, model tokens and cost per verified program, share of runs passing within 5 attempts, and time to verdict.
- **Leakage check:** confirm the published leakage bound is unchanged, and confirm no projection access appears in the judge's view.
- **Sample size and stopping rules:** set before any run.

No model calls in this PR.

## 10. Tests (all offline)

1. **Default off:** without a projection, `tools/list` returns exactly today's 10 tools, byte-identical in names and schemas.
2. **Decision gate:** missing, rejected, expired, wrong-hash or wrong-lane decisions → no graph tools. A tampered projection file → no graph tools.
3. **Projection policy:** for each excluded kind, property and provenance, a fixture node is dropped. `inspector_private` is never present. Runtime-derived `business_rule` is dropped.
4. **Determinism:** two builds from the same inputs are byte-identical.
5. **Leak check:** planted watch-list values in a fixture projection are detected, with hashes only in the output. A source literal is reported as `source-literal` and fails without approval.
6. **Confidential mode:** source excerpts limited to the lane's programs, and watch-list literals redacted.
7. **Budgets:** responses are never over 32 KB, pagination covers the full result set, and `truncated` is set correctly.
8. **`explain_divergence`:**
   - Field mode: it maps verdict-named fields to nodes and paragraphs.
   - Confidential mode: it returns only the file layout and the writing paragraphs.
   - It never emits a value not present in the projection or the verdict.
9. **Receipts:** `context_projection_sha256` is present and replayable, and older receipts still verify.
10. **CardDemo fixture:** with a projection of the public CardDemo graph, `graph_references` on `ACCT-CURR-BAL` returns the interest-calculation paragraph(s) in `CBACT04C`.
11. **Regressions:**
    - The existing Verify acceptance suite, the smoke kit and all Tower tests pass.
    - **B06 tests pass, with zero changes to B06 files** (CI check: the diff touches no protected path).

## 11. Deliverables and PR breakdown

1. **PR A:** projection policy, `graph-project`, `graph-leak-check`, the Tower kind and lane card, and receipt field. Tests 2–6 and 9–11.
2. **PR B:** the five toolkit tools, `decode_records` paging and docs (`docs/verify/README.md` tool table, operator guide section on projections). Tests 1, 7, 8 and 10.
3. **PR C (docs only):** the A/B pre-registration draft.

Each PR states zero Docker, zero model calls and no B06 or frozen-path changes. Each records operator review, not independent attestation.

## 12. Non-goals

- No vector database, embeddings or semantic search. Lexical search and graph relations only in v1.
- No write tools: the agent can't add facts to the graph. Agent-proposed facts remain a future, Tower-gated `inferred` path.
- No change to the factory's `GraphContextAssembler` or to B05/B06 builders.
- No ingestion of Google MAT assessments in v1. Leave a projection-loader seam so a MAT-sourced graph can be added later.

## 13. Scheduling

Lower priority than the B06 critical path (runtime probe, J1 smoke, transport adapter, qualification). Proceed on a separate branch only while it doesn't compete with B06 work. Target: PR A and PR B merged by the end of October. The A/B run is to be scheduled after the B06 launch.
