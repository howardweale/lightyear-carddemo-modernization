# Observer v2: exact image-artifact extraction proposal

**Historical proposal; superseded by the [inventory-first review
follow-up](../review-pr269-271/README.md). Do not execute the old commands below.**
Its extraction attempt and later larger-bound proposal remain preserved. The
new controller refuses a broad-extraction core; a new inventory snapshot,
public commit and Tower window are required.

Prepared for Howard's separate Control Tower decision. **Not launched.**
Operator review; not independent attestation. This is an artifact extraction,
not a smoke group, qualification, five-path census or measurement.

## Exact bindings and window

| Binding | Value |
|---|---|
| Source commit | `0b26118788c4ca780202526f62bdceb42aab2e21` |
| [Plan](plan.json), content hash | `b3be9fced9e41aec44931d8e5947eb563893139d335d170c6c17aac93378a026` |
| [Executable snapshot](snapshot.json), content hash | `4c36ab3bb6115ab533b84284eb0a70c045451c3cc4686f338ab6c885c28a0b6f` |
| Application image | `sha256:f3bed005214fbaec7f580a2d27e0dffa7a868bfc913db8c231d6f2b3fe4e0300` |
| Confirmed Tower public-key fingerprint | `65bcec7f9fb46d5a618cd61b8bcd0a74497b9a0c360738781e269ef2d87a6240` |
| Proposed window | October 7, 2026, **21:30–22:00 UTC / 2:30–3:00 PM PDT** |
| Latest start | **21:35 UTC / 2:35 PM PDT**, subject to remaining cleanup reserve |
| Limits | One container; 900 seconds extraction; 600 seconds cleanup reserve; zero retries |

The executable source files are copied from Git blobs, not line-ending-converted
working files. The snapshot includes the exact Python library closure and tests.
The immutable local root is
`work/b06-execution-snapshots/observer-v2-image-extraction-r1`.
The final publication commit must contain every exact mapped blob, manifest and
plan. The Tower request binds that commit after remote verification; the source
commit above alone does not satisfy the publication gate.

## Scope

Read the existing image's `/application` and `/root/.m2` class/JAR artifacts and
the resolved JDK's executable, release file, module image, native libraries and
original JMOD class entries. Keep every duplicate origin and ZIP entry ordinal.
No loaded-source conclusion is inferred from a filename or an artifact search.
Full artifact bytes and logs stay local; public reporting contains hashes,
counts, duration, cleanup and limitations only.

The single new container has no network, a read-only image root, all capabilities
dropped and no-new-privileges. Its only mounts are the exact read-only extractor
and a new owned writable evidence directory. No database, target JVM, native
pair, compiler, candidate, model, image pull/build or private input/key mount is
permitted. An image declaring anonymous volumes is rejected before creation.
Extraction is capped at 8 GiB of unique retained blobs and 200,000 class entries;
the host requires 16 GiB free. Missing inputs, symlink-directory ambiguities,
read errors or exceeded bounds fail closed and are preserved.

Before any Docker command, the runner checks the snapshot, public Git bytes,
window and a fresh signed Tower journal. The Tower key must match the confirmed
fingerprint and differ from the campaign signing key. It then refuses overlap
with any running container and checks the local image ID. Cleanup may remove
only the new container after verifying its ID, exact name, ownership label and
image; it verifies absence afterward. It creates no networks or volumes. No
prune, foreign-resource removal, retry or extension is permitted. All clocks and
signing remain on the host's real time.

## Preparation validation

Six offline extraction tests passed in DEV and from the immutable snapshot.
They cover exact Git-byte freezing (including namespace packages), all
publication bindings, fresh distinct Tower signatures, missing/rejected/stale
decisions, late starts, output reuse, duplicate artifact preservation, successful
extraction, tampered blobs, timeout evidence, foreign ownership and anonymous
volume refusal. Docker is mocked in these tests. CLI help and the deferred
runtime imports passed from the same snapshot without opening a signer.

The preceding combined host-proof/extraction suite passed 30 tests; the added
namespace regression makes 31 distinct tests across the two checks. These are
offline checks, not native qualification. An initial assembler attempt rejected
assumed `__init__.py` files before creating any snapshot; the corrected assembler
handles the repository's namespace packages explicitly. The failed attempt is
recorded as preparation, not a native slot. Windows sandbox temporary-directory
permission failures were retained; the normal-host tests passed.

r10 remains failed; all 2,117 frozen input files were reverified unchanged.
The unrun r11's 2,125 frozen inputs were also unchanged. No J1 predicate or
expected outcome changed. See the [host progress addendum](../observer-v2-generated-proof/progress-addendum.json).

## Tower review and execution

After publication, preparation writes one `campaign-authorization` request in
scope `ms94-b06`, with a summary beginning **One offline pinned-image artifact
extraction, NOT a smoke run**. The request binds the plan, snapshot, public commit,
limits and exact UTC window. Approve that item only if this scope and window are
acceptable. A decision on an old r11 smoke item does not authorize this action.

No automatic launch or recurring monitor is installed by this preparation.
After the exact Tower decision, an authorized operator can invoke the frozen
runner once. The local `work/b06-image-preparation-r1/publication.json` records
the verified final public commit and request ID. From the B06 checkout:

```powershell
$repo = (Get-Location).Path
$snapshot = Join-Path $repo 'work/b06-execution-snapshots/observer-v2-image-extraction-r1'
$plan = Join-Path $repo 'docs/calibration/idempiere-ms94/stage-b-06/preparation/observer-v2-image-extraction-r1/plan.json'
$publication = Get-Content -LiteralPath (Join-Path $repo 'work/b06-image-preparation-r1/publication.json') -Raw | ConvertFrom-Json
$python = Join-Path (Split-Path $repo) 'idempiere-runtime-evidence/work/native-venv/Scripts/python.exe'
$authority = Join-Path (Split-Path $repo) 'idempiere-runtime-evidence'
$env:PYTHONPATH = 'src;.'
$env:PYTHONUTF8 = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
Set-Location -LiteralPath $snapshot
& $python -B -m tools.b06_image_artifacts.controller `
  --root $snapshot --plan $plan --repository $repo `
  --output (Join-Path $repo 'work/b06-image-preparation-r1/execution') `
  --public-commit $publication.public_commit --authority $authority `
  --tower-key (Join-Path $repo 'docs/calibration/idempiere-ms94/stage-b-06/preparation/tower-r8.public.pem') `
  --credential 'C:/ProgramData/Lightyear/B06TowerAuthority/authority.credential.txt'
```

The credential is read in place for authenticated read-only Tower access; do
not display, copy or mount it. The existing campaign signer signs only the
extraction start/report, not the operator's authorization. Signed start/report,
the exact Tower proof, inspected container identity, command ledger and raw
catalogue remain in the fresh local output. No output directory can be reused.

After a passing extraction, complete native artifact/provenance bindings and
prepare the separate five-path executable and Tower request. Full generated-class
admission is still incomplete. The Oct 9 JDI proof time box remains in force.
