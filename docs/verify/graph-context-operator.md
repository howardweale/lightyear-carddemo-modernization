# Optional Verify graph context

Operator review; not independent attestation. No Docker or model calls are
needed to prepare projections. Default startup remains the original ten tools.
The projection is a public-source aid, not a new oracle or a qualification claim.

## Build and check

The versioned policy is `verify/graph-projection-policy.json`. Its initial lane
is public CardDemo INTCALC only. Approved file hashes bind source excerpts;
the evidence pack can deny visibility but cannot substitute its own source
text. Unknown kinds, properties, sources and provenance are excluded.
Only explicitly enumerated IMS/assembler kinds and relations are allowed:
there are no permissive prefix wildcards. Runtime dependencies are transitively
excluded. A reviewed asserted rule needs an explicit mapping ID.

Use an existing operator signing key, never an agent-readable key:

```sh
lightyear-verify graph-project \
  --graph knowledge/graph.snapshot.json.gz \
  --evidence knowledge/evidence/source.pack.json.gz \
  --policy verify/graph-projection-policy.json --source-root . \
  --lane INTCALC --mode confidential --customer-id carddemo-reference \
  --signing-key /operator/authority.pem --out /operator/projection-new
```

Outputs are deterministic and an existing directory is refused. Confidential
mode removes statement properties, permits excerpts only for lane programs,
and redacts **all** string/numeric literals. This intentional strengthening
of the spec avoids disclosing private watch-list membership through selective
redaction. The builder never needs the private watch-list.

As the judge user, with the private evaluation directory and existing judge
key, scan decoded lane inputs/reference outputs:

```sh
lightyear-verify graph-leak-check \
  --projection /operator/projection-new --lane INTCALC \
  --policy verify/graph-projection-policy.json --source-root . \
  --evaluation /judge/evaluation --signing-key /judge/authority.pem \
  --operator-public-key /operator/authority.public.pem \
  --tower-root /operator/tower --scope verify-intcalc
```

No values or watch-list are printed. Every match fails the scan. Non-source
matches prohibit release. A source-literal exception remains failed until
Howard explicitly acknowledges each `source-literal:<value-sha256>` in the
signed Tower decision's reason. The request includes manifest counts and
the hash-only leak summary. Review dates expire at the start of the named UTC
date. No campaign key or agent approval can substitute for Tower.

Retain `leak-check.json` on the judge/operator side; it includes watch-list
counts and match locations. A signed `graph-leak-certificate.json` exposes
only eligibility, the report/projection/lane/evaluation-inventory hashes, and public-literal
exceptions. Copy to the agent only the projection, manifest, certificate and
approved Tower proof. Do not copy the source graph, evidence pack, watch-list,
raw leak report, private records, keys or evaluation captures. This separation
prevents report counts/locations becoming an extra private-data channel.
The scan rejects runs from another lane and a changing evaluation inventory.
Judge initialization checks the signed scan's inventory hash against its own
evaluation files; a scan of a different dataset cannot admit context.

## Configure the two sides

In the operator-owned judge task config set `context_projection_sha256` to
the manifest's projection file hash and `graph_context` to:

```json
{
  "directory": "/operator/projection-new",
  "decision": "/operator/projection-proof.json",
  "trust": {
    "operator_key": "<trusted PEM public key>",
    "judge_key": "<trusted PEM public key>",
    "tower_key": "<trusted PEM public key>",
    "trusted_head": "<current Tower journal head obtained out of band>",
    "scope": "verify-intcalc",
    "lane_sha256": "<manifest lane hash>",
    "customer_id": "carddemo-reference",
    "mode": "confidential"
  }
}
```

Put the same public `trust` object under `graph_trust` in the agent's
operator-bound public manifest. Keys and the current head come from trusted
configuration, never from the proof being verified. Do not update a running
task's signed config. Rejected/expired decisions require a new reviewed
configuration, preserving prior receipts. A status-only pending/rejected
projection can be shown before admission; it grants no tool access.

```sh
lightyear-verify-mcp --workspace /agent/public \
  --public-manifest /agent/public.json --judge-url http://127.0.0.1:8770 \
  --graph-projection /agent/context --graph-decision /agent/context-proof.json
```

Startup validates signatures, exact hashes, lane/mode/customer, expiry and
Tower scope/head; it also checks the judge's configured context. Failure
registers only the original ten tools and emits one closed stderr line.
Expiry during service removes graph tools on the next tools/list and rejects
graph calls. No network graph lookup exists. The agent-local query log
(`graph-queries.jsonl`) is append-only informational telemetry and untrusted.

## Receipts, UI and response sizes

Receipt v2 includes `context_projection_sha256` in both private and public
signed bodies. Replay compares it to the signed task config. v1 retains its
original signed bytes with null context implied; full historical replay still
requires the original hash-bound executable, not a bypass of implementation
verification. The hash states approved available context, not proof that the
agent queried or understood it. Tower displays the context alongside each
attempt and a projection state/counts/hash/decision card.

Graph responses default to 8 KiB, never above 32 KiB. Search and neighbors
use query-bound opaque cursors; references/explanations cap at 50 per page and
also accept an optional cursor so byte truncation never strands later items. An oversized
item returns an explicit truncated summary rather than exceeding the budget.
Lexical references are labelled observed (lexical), not semantic dependency
proof. Bare VERIFIED_BY links contain only explicitly approved public scenario
IDs; no scenario bodies or expected values are loaded.

The original decode tool signature/default output stays byte-compatible when
graph tools are off. With graph enabled, `decode_records` adds offset, limit
(50 default, 200 maximum), exact field-path projection and summary. Summary
counts/min/max/distinct values describe **all bound public development records**,
never evaluation data. This avoids silently changing existing smoke clients.

Only hashes of generated artifacts should be committed/published. No Maintec
or private customer source/data is supported by this policy. Live model tests
need commit-specific approval; see the [A/B draft](specs/graph-context-ab.md).
