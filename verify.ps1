$ErrorActionPreference = "Stop"

$ProjectDir = $PSScriptRoot
$VerificationDir = Join-Path $ProjectDir "work\java-candidate-verify"
$CandidateJar = Join-Path $ProjectDir "candidate-java\target\carddemo-spring-batch-candidate-0.1.0-SNAPSHOT.jar"
$env:PYTHONPATH = Join-Path $ProjectDir "src"

& py -3.11 -m unittest discover -s (Join-Path $ProjectDir "tests") -v
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Push-Location (Join-Path $ProjectDir "candidate-java")
try {
    & .\mvnw.cmd test package
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Pop-Location
}

& py -3.11 -m carddemo_oracle demo --work-dir $VerificationDir
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& java -jar $CandidateJar `
    "--carddemo.input-dir=$(Join-Path $VerificationDir 'input')" `
    "--carddemo.output-dir=$(Join-Path $VerificationDir 'candidate-output')" `
    "--carddemo.processing-date=2022071800" `
    "--carddemo.timestamp=2022-07-18-00.00.00.000000" `
    "--carddemo.final-account-policy=source-faithful"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& py -3.11 -m carddemo_oracle compare `
    --expected (Join-Path $VerificationDir "oracle-output") `
    --actual (Join-Path $VerificationDir "candidate-output") `
    --report (Join-Path $VerificationDir "comparison.json")
exit $LASTEXITCODE
