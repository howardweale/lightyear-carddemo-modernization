$ErrorActionPreference = "Stop"

$ProjectDir = $PSScriptRoot
$VerificationDir = Join-Path $ProjectDir "work\java-candidate-verify"
$CandidateJar = Join-Path $ProjectDir "candidate-java\target\carddemo-spring-batch-candidate-0.1.0-SNAPSHOT.jar"
$env:PYTHONPATH = Join-Path $ProjectDir "src"
. (Join-Path $ProjectDir "python-runtime.ps1")

Invoke-FactoryDarkPython -m lightyear_common prerequisites --project-root $ProjectDir
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Invoke-FactoryDarkPython -m lightyear_common receipt-claims --project-root $ProjectDir
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Invoke-FactoryDarkPython -m lightyear_common scripts --project-root $ProjectDir
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Invoke-FactoryDarkPython -m unittest discover -s (Join-Path $ProjectDir "tests") -v
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Invoke-FactoryDarkPython -m carddemo_oracle validate-normalizations `
    --ledger (Join-Path $ProjectDir "spec\comparison-normalizations.json")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& (Join-Path $ProjectDir "model-workcell.ps1") validate
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& (Join-Path $ProjectDir "hardened-execution.ps1") verify
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& (Join-Path $ProjectDir "data-modernization.ps1") verify
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& (Join-Path $ProjectDir "migration-rehearsal.ps1") verify
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& (Join-Path $ProjectDir "knowledge-graph.ps1") verify
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& (Join-Path $ProjectDir "extension-foundation.ps1") verify
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& (Join-Path $ProjectDir "mainframe-access.ps1") verify
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& (Join-Path $ProjectDir "zosmf-adapter.ps1") verify
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& (Join-Path $ProjectDir "collection-appliance.ps1") verify
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& (Join-Path $ProjectDir "cobol-qualification.ps1") verify
& (Join-Path $ProjectDir "pli-qualification.ps1") verify
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& (Join-Path $ProjectDir "jcl-qualification.ps1") verify
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& (Join-Path $ProjectDir "pli-conformance.ps1") verify
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& (Join-Path $ProjectDir "pli-modernization.ps1") verify
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& (Join-Path $ProjectDir "pli-build-attestation.ps1") verify
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& (Join-Path $ProjectDir "composite-estate.ps1") verify
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& (Join-Path $ProjectDir "runtime-evidence.ps1") verify
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& (Join-Path $ProjectDir "semantic-memory.ps1") validate
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& (Join-Path $ProjectDir "portfolio-factory.ps1") verify
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& (Join-Path $ProjectDir "factory-qualification.ps1") verify
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& (Join-Path $ProjectDir "durable-factory.ps1") verify
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& (Join-Path $ProjectDir "live-control-tower.ps1") verify
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& (Join-Path $ProjectDir "cics-vsam-readiness.ps1") verify
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& (Join-Path $ProjectDir "asm-readiness.ps1") verify
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& (Join-Path $ProjectDir "ims-readiness.ps1") verify
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& (Join-Path $ProjectDir "audit-control-tower.ps1") verify
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& (Join-Path $ProjectDir "source-only-pilot.ps1") verify
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& (Join-Path $ProjectDir "integrated-pilot-qualification.ps1") verify
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Push-Location (Join-Path $ProjectDir "candidate-java")
try {
    & .\mvnw.cmd test package
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Pop-Location
}

Invoke-FactoryDarkPython -m carddemo_oracle demo --work-dir $VerificationDir
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& java -jar $CandidateJar `
    "--carddemo.input-dir=$(Join-Path $VerificationDir 'input')" `
    "--carddemo.output-dir=$(Join-Path $VerificationDir 'candidate-output')" `
    "--carddemo.processing-date=2022071800" `
    "--carddemo.timestamp=2022-07-18-00.00.00.000000" `
    "--carddemo.final-account-policy=source-faithful"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Invoke-FactoryDarkPython -m carddemo_oracle compare `
    --expected (Join-Path $VerificationDir "oracle-output") `
    --actual (Join-Path $VerificationDir "candidate-output") `
    --report (Join-Path $VerificationDir "comparison.json")
exit $LASTEXITCODE
