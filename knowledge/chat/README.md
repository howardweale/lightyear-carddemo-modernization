# LIGHTYEAR grounded graph chat

Graph chat is an evidence interface, not an unrestricted chatbot. A question is resolved to one or
more visible graph entities, expanded through an intent-specific bounded neighborhood, and answered
from that evidence package. The response carries citations, confidence, limitations, supporting
node and edge IDs, the canonical graph hash, and useful follow-up questions.

## Answer pipeline

1. Classify the question as `who`, `what`, `where`, `when`, `why`, `how`, `impact`, `lineage`,
   `verification`, or general explanation.
2. Resolve a focused node or lexical graph roots.
3. Retrieve an intent-specific neighborhood through the implementer or verifier boundary.
4. Deduplicate source evidence and assign citation IDs.
5. Produce a schema-constrained answer using the local or OpenAI provider.
6. Reject citations that do not exist in the retrieved package.
7. Return the exact graph entities that grounded the answer.

The versioned provider output contract is `answer.schema.json`.

## Answer providers

### Grounded local

The local provider requires no network, API key, package installation, or language model. It
constructs predictable answers from graph statements and relationships. It is useful for privacy
testing, offline operation, and deterministic CI.

### OpenAI high-quality

Set the API key in the terminal that launches the explorer:

```bash
export OPENAI_API_KEY="your-api-key"
export LIGHTYEAR_OPENAI_MODEL="gpt-5.6"
./graph-explorer.sh
```

Windows PowerShell:

```powershell
$env:OPENAI_API_KEY = "your-api-key"
$env:LIGHTYEAR_OPENAI_MODEL = "gpt-5.6"
.\graph-explorer.ps1
```

The browser receives provider availability and the model name, never the API key. The server sends
only the bounded evidence package and up to eight short conversation turns. API response storage is
disabled. `LIGHTYEAR_OPENAI_MODEL` and `LIGHTYEAR_OPENAI_ENDPOINT` are optional overrides.

The OpenAI provider uses the Responses API with strict JSON Schema output. Returned citation IDs
are validated against the retrieved evidence package before an answer reaches the browser.

## Quality contract

A high-quality answer must:

- answer the question directly before adding detail;
- distinguish observed, asserted, inferred, and verified claims;
- cite only evidence present in its retrieval package;
- state when timing, ownership, rationale, runtime truth, or other facts are absent;
- preserve audience isolation even when a question contains prompt-injection instructions;
- identify retrieval truncation and avoid treating a partial neighborhood as complete;
- expose the supporting graph identity so the answer can be reproduced and audited.

## Security boundary

The v0.5 explorer remains a locally bound demonstration. Audience selection is policy enforcement
inside retrieval but is not user authentication. Switching audiences clears visible conversation
history so verifier-only answers are not retained in the implementer UI. Production deployment
requires authenticated principals, authorization outside the client, audit records, rate limits,
secret management, prompt and response telemetry, and signed answer receipts.

Graph values are treated as untrusted data. The model instruction explicitly prohibits following
instructions found in nodes, properties, evidence, questions, or prior messages. The deterministic
retrieval boundary—not the model prompt—is the primary defense against verifier-data disclosure.
