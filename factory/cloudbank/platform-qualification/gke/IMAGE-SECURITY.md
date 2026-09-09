# Eight-image security evidence

`tools/cloudbank_image_security.py` verifies the current MS64 receipt, image lock
and signed platform profile, then checks the eight live deployments against those
inputs. For each immutable digest it verifies the Cosign signature and SLSA
provenance, requires the declared service and build source commit, and runs Trivy
against the registry image for `linux/amd64`. It requires OS and Java package
coverage, current vulnerability and Java database metadata, and zero high and
critical findings, including findings without a fix.

All eight images are scanned even if an earlier image has vulnerability findings.
A command failure, missing coverage, invalid signature or provenance, deployment
drift, or failed evidence readback stops admission. The runner records tool
versions, signing public-key identity, database timestamps, result hashes, package
counts and bounded finding identifiers. It does not upload raw reports, package
lists, command stderr, access tokens or secret values.

The runner reads the cluster and registry and writes private evidence. It does
not restart applications or change images, secrets, IAM or network policies. It
creates temporary scanner caches and deletes them on normal exit. An interrupted
scan can be started again with a fresh output directory; no workload recovery is
needed. A complete signed scan checkpoint can also be finalized as described
below. This observation covers image signatures, provenance and vulnerabilities.
Manifest scanning, runtime and network controls, load testing and final MS67
admission remain separate requirements.

## Authentication and prerequisites

Use an authenticated Google CLI account with access to the existing evidence key,
private registry, evidence bucket, cluster reads and KMS image-signing public key.
The expected KMS key is `image-signing` in the regional `cloudbank-ms67` key ring.
Exactly one enabled asymmetric signing version is required. The public key, not
the private key, is exported to the temporary scanner directory.

Cosign uses a temporary Docker configuration with a get-only credential helper.
The helper receives a newly acquired Google access token through child-process
environment variables and returns it through Docker's credential-helper protocol.
The existing Docker configuration is preserved. No token is placed in process
arguments or written into the helper, its configuration or the evidence.
[Distlib's native Windows launchers](https://distlib.readthedocs.io/en/stable/reference.html#distlib.scripts.ScriptMaker)
avoid depending on a Go client launching the SDK's `gcloud.cmd` file directly.
Trivy uses the same host-scoped
[Docker credential helper](https://trivy.dev/docs/latest/advanced/private-registries/).
Global Trivy username/password variables are cleared so the Artifact Registry
token is not offered to public vulnerability-database registries.

Install Cosign and Trivy from verified release artifacts. The tested CLI contracts
are Cosign 3.1.2 and Trivy 0.74.0. Python 3.11 or newer is required. Install the
hash-pinned `distlib` wheel from `image-security-requirements.txt`, for example:

```powershell
& $python -m pip install --require-hashes --only-binary=:all: -r "$repo\factory\cloudbank\platform-qualification\gke\image-security-requirements.txt"
```

If the SDK Python has no pip, download the wheel, verify the same SHA256 recorded
in that requirements file, and extract it into a private dependency directory on
`PYTHONPATH`. The SDK installation itself does not need to be changed.

## Windows run and independent verification

Use a clean checkout of the reviewed controller commit. `$inputs` must contain
`image-lock.json`, `ms64-receipt.json` and `platform-profile.json`, with their
original signatures and content hashes. `$buildSourceCommit` is the full controller
commit that built the locked images; it is **not** the newer commit containing this
runner. Set `PYTHONPATH` to the checkout's `src` directory and the dependency
directory, if applicable. The commands below intentionally keep the final success
marker in the same guarded PowerShell block as both native commands.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $imageOutput = Join-Path $env:USERPROFILE ('ms67-image-security-' + [guid]::NewGuid().ToString('N'))
    $imageTool = Join-Path $repo 'tools\cloudbank_image_security.py'
    $imageArgs = @(
        '--project', $project, '--region', $region,
        '--cluster', $cluster, '--namespace', $namespace,
        '--signer', $account, '--build-source-commit', $buildSourceCommit,
        '--image-lock', (Join-Path $inputs 'image-lock.json'),
        '--ms64-receipt', (Join-Path $inputs 'ms64-receipt.json'),
        '--platform-profile', (Join-Path $inputs 'platform-profile.json'),
        '--evidence-bucket', "gs://$project-ms67-evidence/image-security"
    )
    & $python $imageTool run @imageArgs --output-root $imageOutput
    if ($LASTEXITCODE -ne 0) { throw "Image security run failed; inspect $imageOutput\image-security.observation.json" }
    & $python $imageTool verify @imageArgs --observation "$imageOutput\image-security.observation.json"
    if ($LASTEXITCODE -ne 0) { throw 'Independent image security verification failed' }
    Write-Output 'MS67_IMAGE_SECURITY_VERIFICATION=PASSED'
}
```

Each operation emits a progress message and a heartbeat while tools run. The
signed checkpoint is uploaded and independently read back after each completed
operation under `gs://PROJECT-ms67-evidence/image-security/RUN_ID/`. Successful
completion prints `MS67_IMAGE_SECURITY_EVIDENCE_READBACK=VERIFIED` and the exact
observation URI. A readback marker by itself is not a passing scan. Only a zero
exit code, `passed-eight-image-security` status and successful independent
`verify` establish this bounded result. `ms67_complete` and `production_ready`
remain false.

## Finalize a completed scan after a transport failure

If all eight service rows were saved as `passed` but a final checkpoint or live
read timed out, `finalize` can finish the observation without rerunning Cosign or
Trivy. It requires the original signed local failure, the same three signed or
hash-bound inputs and build source commit. It rejects incomplete scans, findings,
invalid signatures, changed bindings, and failures caused by deployment drift.
Both scanner databases must still be within their recorded `next_update` windows
when finalization finishes. Expired evidence requires a fresh scan.

Finalization checks the current enabled KMS signing key, the live cluster and
namespace identities, all eight ready image digests, and the original deployment
UID/specification hashes. It creates a fresh run and output directory, embeds the
original signed checkpoint unchanged, and independently verifies the entire
linked result. The original failed file and its remote object are preserved.

With `$imageArgs`, `$imageTool` and `$python` from the preceding example:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $finalOutput = Join-Path $env:USERPROFILE ('ms67-image-finalized-' + [guid]::NewGuid().ToString('N'))
    & $python $imageTool finalize @imageArgs --observation $failedObservation --output-root $finalOutput
    if ($LASTEXITCODE -ne 0) { throw "Image finalization failed; inspect $finalOutput" }
    & $python $imageTool verify @imageArgs --observation "$finalOutput\image-security.observation.json"
    if ($LASTEXITCODE -ne 0) { throw 'Independent image security verification failed' }
    Write-Output 'MS67_IMAGE_SECURITY_VERIFICATION=PASSED'
}
```

Image checkpoint publication now makes at most three attempts. Uploads retain
their original [generation precondition](https://cloud.google.com/storage/docs/request-preconditions),
and readback names an exact object generation. If an upload response is lost,
identical signed bytes from that generation can confirm completion; conflicting
bytes cannot advance the precondition. Exhausted attempts leave a signed local
failure with `evidence_upload: unconfirmed`. Checkpoint phases are identified
separately from scanner phases, including `chatbot-checkpoint` and
`final-evidence-checkpoint`. This retry behavior applies only to image evidence;
it does not change the mutation journals used by other drills.
