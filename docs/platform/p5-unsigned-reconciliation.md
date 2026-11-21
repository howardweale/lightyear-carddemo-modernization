# Proposed abort-only reconciliation

This is an unpublished review proposal, not an instruction to run the command now.
No key is created or used. Not signed: any receipt by machine. No admission or model is constructed.

After an interrupted controller has exited, the proposed command accepts an existing
run directory and independently reviewed public bindings:

```powershell
$env:PYTHONPATH = 'src;.'
python -B -m lightyear_factory.cli reconcile-interrupted `
  --runs-root '<existing controller runs root>' `
  --run-id '<existing attempt ID>' `
  --work-order-sha256 '<reviewed order SHA-256>' `
  --consumed-nonce-sha256 '<reviewed consumed nonce SHA-256>' `
  --sealed-workspace-sha256 '<reviewed workspace manifest exact-byte SHA-256>'
```

It appends exactly one terminal event to events.jsonl, retaining the original prefix.
Status is `interrupted; awaiting human attestation`. The nonce stays consumed.
A second invocation refuses. A live controller, terminal record, mismatched binding,
invalid hash chain, incomplete evidence or missing consumed nonce causes refusal.
There is no resume, retry, re-admission or signing option.

The shadow accounting ledger contains counts, cost, duration and transport hashes,
never prompt/response content. In-flight final usage remains explicitly unknown;
the record is not proof that billing is complete. Preserve all evidence on refusal.
Hash chaining detects inconsistencies but does not authenticate a complete owner rewrite.

Human attestation is still blocked: the current Tower factory-review registry has no
interruption-attestation kind. This proposal includes no Tower change, relabeled backfill, internal signing shortcut or new gap-acceptance claim. Howard must decide the next step.

The immutable historical orchestrator mismatch is identified in the dated exception
proposal. Planned: recompute a new F2 request only after approved merge, from frozen main.
request_ready stays false until CI validates all fields. No run authority is granted.
