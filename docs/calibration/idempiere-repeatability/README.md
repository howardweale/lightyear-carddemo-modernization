# MS92 retained experiment evidence

All 40 planned trials halted: zero first-try passes and zero repaired passes.
`report.json` is the original signed per-condition report. `trials/` contains
each signed trial result, plan, declaration, authorization and publication receipt.
The terminal records document verification of all 40 publications and cleanup of
all 78 native attempts.

`archive-index.json` binds the hashes and sizes of the 40 complete archives,
totalling 2,499,047,692 bytes. **The archives are retained locally at their indexed
paths and are not included in Git.** These compact records cannot replace the
archives for full provenance reconstruction. MS92 had no complete native gate
files; archive verification does not turn its halted attempts into passed gates.

Trusted public-key SHA-256:
`c2fbae3453e8bcae03e0830a9eb83f310f027ad51929deee967ecee1a41f399f`.
Establish trust in that operator key separately. No private signing key is published.

With an indexed full archive restored to its publication directory, use:

```powershell
$env:PYTHONPATH='src;.'
python -m tools.publish_measured_campaign verify --output <publication-directory> --trusted-key-sha256 c2fbae3453e8bcae03e0830a9eb83f310f027ad51929deee967ecee1a41f399f
```

See [MS92](../../milestones/MS-92/MS-92.md) for costs, interpretation and limits.
