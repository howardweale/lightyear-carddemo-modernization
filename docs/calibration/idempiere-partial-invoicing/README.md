# MS88 agent-built partial invoicing

Run `journey-be7ca0651d3c45a7bde77136a69006f1` passed **bounded partial-invoicing equivalence** on local Oracle 26ai Free and PostgreSQL 15.19. Both engines produced paid invoices of 19.35 and 38.69, with combined net 53.99, tax 4.05 and gross 58.04. Each lane verified twenty-eight accounting entries in twelve balanced groups, closing stock seven, and zero new application issues. The complete gate reported zero unresolved row differences. Seventeen raw trace differences remain recorded under existing explicit rules.

The final native run lasted from 23:14:55 to 23:20:39 UTC on 26 September 2026, recorded seventeen signed journal events and zero interventions outside designed stops, and completed cleanup. The builder receipt records five client invocations and four completed model turns across the attempt history. Its exact final Java hash is `4510cb8698b3f38098905e7e92578641daa3d7e8b3e7e191cd7176760a1975c4`.

## Review files

- [Native evidence archive](evidence.zip), [publication receipt](receipt.json) and [public key](authority.public.pem).
- [Exact generated Java harness](LightyearPartialInvoiceTest.java).
- [MS88 milestone](../../milestones/MS-88/MS-88.md), including the business contract, generation limits, failed attempts and remaining limits.
- [Signed earlier-failure summary](failed-attempts/summary.json), with the original failed native receipts, cleanup receipts and selected execution/readback diagnostics.
- Signed authorizations for the [third](authorizations/repair-authorization.json), [fourth](authorizations/single-call-repair-authorization.json) and [fifth](authorizations/no-reposting-repair-authorization.json) invocations. Each binds the reviewed prompt and declaration hashes.

## Offline verification

From the repository root, using Python with the control-tower dependencies:

```powershell
$env:PYTHONPATH = 'src'
python tools/publish_native_journeys.py verify --output docs/calibration/idempiere-partial-invoicing
```

Verification restores original evidence bytes from the lossless content-addressed archive, checks signatures and journal chains, binds the builder prompt/proposal/events/harness to the native plan and recomputes the independent partial-invoicing and cleanup gates. No database, Docker, model call or external network is required. The installed implementation must match the recorded plan; only Python checkout line-ending differences are accepted.

The receipt/public-key pair is the review trust anchor. These are local operator signatures, not independent third-party attestation. The archive excludes private keys, ephemeral credentials and retained database filesystem exports.

## Read the attempt history correctly

Five client invocations were authorized. The first could not use the account model with the older CLI. The next two produced harnesses rejected for a Boolean assertion and a posting API compilation error. The fourth executed successfully on both engines, but the independent gate rejected twenty accounting-history rows per engine caused by redundant reposting. Its passing per-lane business readbacks did not make its overall result a pass.

The fourth and fifth proposals were constrained to exact source replacements, enforced by SHA-256 before native execution. The fifth skips posting when the completion workflow already posted the document. No expected business value, permitted-table list or comparison rule was broadened. Failed receipts remain failed; their history is not rewritten by a later result.

Human-approved repair guidance and budget increases occurred between attempts. An unattended final native run does not mean the entire development sequence needed no human decisions. The generated artifact is one application test harness, not transformed iDempiere production code.

Full application equivalence, schema equivalence, platform qualification and independent attestation remain false. The earlier fractional shipment timestamp finding remains open. No GCP resources were used.
