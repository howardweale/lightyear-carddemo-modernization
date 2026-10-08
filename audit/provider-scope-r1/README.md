# Approved provider-scope static audit

This unsigned, simulated audit binds the current factory/execution/policy.json through its deterministic conformance receipt. Promotion remains BLOCKED. It records no new runtime enforcement, model call, native qualification or operator decision.

The historical v0.19 demo remains byte-identical and is reproduced with audit/fixtures/ms39-execution-conformance.json. Its default CLI input is explicitly historical; supply --execution-receipt for a current or live audit. The source-only pilot continues to bind the original demo dossier without an evidence-release change.

Reproduce this version with:

    python -m lightyear_audit build --execution-receipt factory/execution/conformance.receipt.json --release release:carddemo-intcalc:provider-scope-r1 --output work/provider-scope-audit/audit.snapshot.json.gz --dossier-json work/provider-scope-audit/dossier.json --dossier-markdown work/provider-scope-audit/dossier.md

The regression test verifies both versions reproduce separately. Neither fixture is independent attestation.
