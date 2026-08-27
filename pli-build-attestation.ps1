param(
    [ValidateSet("build", "verify", "ci-build")]
    [string]$Action = "verify"
)

$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:PYTHONPATH = "$(Join-Path $ProjectDir 'extensions/runtime')$([IO.Path]::PathSeparator)$(Join-Path $ProjectDir 'src')"
. (Join-Path $ProjectDir "python-runtime.ps1")
$Canonical = Join-Path $ProjectDir "extensions/pli/attestation"
$Generated = Join-Path $ProjectDir "work/pli-build-attestation-$Action"

function Run-Python { Invoke-FactoryDarkPython @args; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE } }

function Build-Outputs([string]$OutputRoot, [string]$SourceCommit) {
    if (Test-Path $OutputRoot) { Remove-Item -Recurse -Force $OutputRoot }
    Run-Python -m lightyear_extensions build-pli-attestation `
        --project-root $ProjectDir --output-root $OutputRoot --source-commit $SourceCommit
}

if ($Action -eq "build") {
    $SourceCommit = (git -C $ProjectDir rev-parse HEAD).Trim()
    Build-Outputs $Generated $SourceCommit
    New-Item -ItemType Directory -Force -Path $Canonical | Out-Null
    @("pli-auth-risk-candidate.jar", "TEST-MixedPliAuthorizationAttestation.xml", "dependencies.json", "sbom.cdx.json", "build.attestation.json", "build.receipt.json") | ForEach-Object {
        $Existing = Join-Path $Canonical $_
        if (Test-Path $Existing) { Remove-Item -Force $Existing }
    }
    Copy-Item (Join-Path $Generated "*") $Canonical
} elseif ($Action -eq "ci-build") {
    $SourceCommit = if ($env:GITHUB_SHA) { $env:GITHUB_SHA } else { (git -C $ProjectDir rev-parse HEAD).Trim() }
    Build-Outputs $Generated $SourceCommit
} else {
    $SourceCommit = (Get-Content (Join-Path $Canonical "build.receipt.json") -Raw | ConvertFrom-Json).source_commit
    Build-Outputs $Generated $SourceCommit
    Run-Python -m unittest extensions.tests.test_pli_build_attestation -v
    @("pli-auth-risk-candidate.jar", "TEST-MixedPliAuthorizationAttestation.xml", "dependencies.json", "sbom.cdx.json", "build.attestation.json", "build.receipt.json") | ForEach-Object {
        $Expected = Join-Path $Canonical $_
        $Actual = Join-Path $Generated $_
        if ((Get-FileHash $Expected -Algorithm SHA256).Hash -ne (Get-FileHash $Actual -Algorithm SHA256).Hash) {
            throw "Attestation artifact differs: $_"
        }
    }
}

$ArtifactRoot = if ($Action -eq "ci-build") { $Generated } else { $Canonical }
Run-Python -m lightyear_extensions validate-pli-attestation --project-root $ProjectDir --artifact-root $ArtifactRoot
Write-Host "PL/I candidate JAR, JUnit-compatible results, SBOM, provenance, and development signature are bound; live z/OS equivalence remains blocked."
