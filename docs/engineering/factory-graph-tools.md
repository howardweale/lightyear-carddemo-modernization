# Factory graph tools (G2)

Work orders default to packed graph context. Opt-in on-demand context uses the
existing approved projection, workspace read manifest, isolation scanner and
model admission. It adds no network endpoint and requires network denial.

```json
{
  "metadata": {
    "context_schema": "1.1",
    "customer_id": "carddemo-reference",
    "graph": "on-demand",
    "graph_policy": {
      "projection_sha256": "<exact approved projection digest>",
      "response_bytes": 8192,
      "call_budget": 8
    }
  }
}
```

The controller binds this policy to the work order and run before planning.
Planner and failure Analyst can request graph_search, graph_neighbors,
graph_node, graph_references and graph_guidance. Builder receives only selected
evidence capsules. Tool requests use one structured request per model turn;
every turn retains the existing model time, token, byte, call and cost budgets.
The graph budget is shared across roles and repair attempts, with a maximum of
32 queries and 32 KiB per complete disclosed result. Search is lexical.

Approval, customer, projection digest, expiry and guidance revocations are
checked. All projection members and every complete query result pass the
controller isolation scanner. Private state, reference traces, session answers,
prior receipts and judge-verdict access are refused. A refused query stops the
session; no rejected contents are written to the public ledger.

Returned node IDs can extend the controller's bounded context from the same
approved snapshot. Returned capsule IDs remain subject to ordinary plan
validation and Builder context limits. Tool responses cannot supply replacement
source nodes. The expanded context is retained as a controller artifact.

The hash-chained run ledger records role, attempt, tool, scanned arguments,
result hash and byte size. Plan policy and run/build receipt graph mode and
counts are controller-derived; factory-build-receipt/1 checks the persisted
ledger and scan evidence. Existing production qualification requirements remain
in force. Packed work orders retain the original response schemas.

CI runs test_factory_graph_tools with the existing factory boundary fixtures:
Planner query/citation, Analyst references, shared-budget refusal, encoded
canary refusal, private-category and Builder refusal, packed fallback, projection
binding, response cap and ledger tampering. These use scripted providers,
ephemeral fixture approval and synthetic gates. They make no paid model calls,
do not activate a graph, and cannot establish production factory acceptance.
Actual operator trust, activation and a separately approved evaluation remain
required before live use.
