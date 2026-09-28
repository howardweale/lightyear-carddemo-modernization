# MS93 bounded qualification evidence

This compact publication preserves all nine native qualification attempts,
including one execution failure and one insufficient-evidence result. Four
business-failure results are deliberate negative controls. Three positive
references passed. None is an autonomous factory success.

`attempts/` contains each plan, complete gate, signed result and signed cleanup.
`publication.json` binds their file hashes. The three aggregate reports retain
the original reference acceptance, all-attempt status and judge v3 reassessment.
Development investigation and diagnostic replay records are included separately.

**Full captures and frozen source archives remain locally in the run directories
named by qualification-status.json. They are not included in this compact Git
publication.** Inspecting signed results does not re-execute the full judge. With
the original runs available, the tools documented in the qualification README
verify the archived evidence and perform a separate disposable-workspace replay.

Public key SHA-256:
`c2fbae3453e8bcae03e0830a9eb83f310f027ad51929deee967ecee1a41f399f`.
The signature is operator attribution and tamper evidence, not independent attestation.

See [MS93](../../milestones/MS-93/MS-93.md) and the
[implementation guide](../../../factory/idempiere/qualification/README.md).
