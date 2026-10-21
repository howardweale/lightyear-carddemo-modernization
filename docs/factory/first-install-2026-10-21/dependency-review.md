# Key and Tower dependency review
The machine investigation did not substantiate an installed Factory folder,
authority, login task or current listener. Missing logs do not prove that no
installation ever existed elsewhere. Treat this as first installation.

## Old key provenance and custody
The SHA-256 of docs/factory/factory-authority.public.pem is
7e1fc72cf3d4d66e6e269a1b73c7e5a215cfa537824a28ceb9861ce006b12f61.
Git first introduces that public PEM in commit
bfc981c83a330e330dcfe4a9e6668e5a110c8a81, dated October 15, 2026
12:51:06 -07:00, authored as howardweale, with subject
"Require signed POSTTRAN authorization and retained image before reservation".
The accompanying signing document says only the public key was committed.
Git authorship is attribution metadata, not proof of who generated/possessed a key.

No verified generation receipt, installation receipt, key custody record, private
key location or recoverable private half has been established. Its private half's
current existence ANYWHERE is UNKNOWN. We have not searched secret contents or
read private keys and cannot honestly claim it is lost, destroyed or recoverable.
Do not label the old key a fixture or Howard's live key without evidence.
The existing runbook already identifies it as a CI trust anchor, not proof of the
local Tower's key. A new key is a new authority; old signatures cannot be transferred.

## Consequences by dependency
| Dependency | Effect of the new key / required action |
| --- | --- |
| POSTTRAN runbook | Old key comparison, installed-path assumption, executable commit, request hash/queue seal and proof procedure become historical. Publish a new runbook/handoff with new public trust and fresh exact bindings; preserve the old file. |
| Oct 17 plan amendment | Records the previous projection binding change only. It does not authorize a key change. Add a new amendment naming old/new public-key hashes and every changed binding; recompute full plan seal through reviewed preparation. |
| Oct 16/17 readiness and Oct 18 clock | Old effective=false/signed=false and old key/plan/request/executable/artifact bindings remain historical. New readiness must bind actual new CI artifact IDs, downloaded hashes, current lifetime and exclusive deadline. Scheduled clock checks still matter. |
| Oct 15/16 authorization requests | Unsigned but sealed to old executable/plan. Re-prepare; never edit in place or pretend their signatures transfer. No real approval yet. |
| Oct 14/15/16 plans and original CI plan | Old immutable evidence. Key replacement changes a frozen bound file. Separate explicit reviewed exception and new preparation required before use with new key. |
| PR415 (called F2 in the request) | Actual title: "docs: retain F8 Release receipts and exact workspace manifest". Its five records and six Release assets preserve F8 measurements and need no byte change for key rotation. It explicitly leaves F2 request_ready=false. Owner remains untouched. |
| COPAU F2 request/preparation | New operator public trust and current journal/backfill proof required, together with final policy, WorkOrder, model/call/token/cost estimate, executable head and human wall-clock/window. Existing model selection and USD10 cap remain; key setup gives no spend approval. |
| G1/G2/G3 and B07 requests | CI-only/synthetic authorities remain CI evidence. Future operator projection approval, backfill/current journal and exact engineering or spend contracts must bind the new authority. G3 comparison scope/cost/window remain unapproved. |
| Seven-record backfill | Re-sign the preserved exact historical source records under the new authority, at the actual present time. Preserve original dates/conditions and current supersessions. This creates a new proof, not evidence that the Oct 14 claimed signatures existed. |
| Factory local activation records, MS-106 | All three claims are unverified: installed service, signed backfill and signed-only migration. Additive correction applies; keep originals. New installation, operator signing and consumer activation each need their own evidence. |
| MS-104, MS-107, MS-109 and milestone index | Software/readiness assertions remain scoped to CI. Any assertion that MS-106 supplied an installed/signing authority is qualified by the correction. New public receipts and subsequent CI-generated projection are needed to restore effective deployment claims. |
| Generated current-status, dated status/handoff records | Preserve dated snapshots. Do not manually rewrite current-status files. Review renderer/input reconciliation separately so the correction appears; no claimed effective operator activation meanwhile. |
| INTCALC ordered-signing and APPL-result/equivalence/I/O/threshold reviews | Evidence bytes stay intact. Import reviewed unsigned contracts and obtain new operator decisions/proofs under new key and a current independently trusted journal; no old signature inheritance. |
| Factory consumers and release/decision packets | Operator config/public key/current head/backfill proof must all agree. Refresh proof/head together, fail on mismatch. Fresh deployment verification precedes release/acceptance claims. |
| B06 | Independent B06 authority and runtime remain untouched. Historical B06 source within the Factory backfill keeps its scope. Factory's new key is not a replacement for B06 attempt signatures. |

dependency-inventory.json lists EACH matched repository path, its byte hash and the
action above, including milestone/status records and all five PR415 paths.
It records reproducible search scope and patterns. This covers direct references
plus the transitive families in this table; it cannot attest unknown external
deployments, backups, untracked private files or future PRs. Refresh before signing.

The old plan/PEM are frozen and unchanged here. Installation may complete Friday;
POSTTRAN signing waits for the separate new-key preparation and exact reviewed
request. No login or private key output belongs in Git, CI, a chat transcript,
an installation receipt, a Release asset or an assistant log.