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
needed. This observation covers image signatures, provenance and vulnerabilities.
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
