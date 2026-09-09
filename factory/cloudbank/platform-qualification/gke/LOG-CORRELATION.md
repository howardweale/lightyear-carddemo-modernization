# MS67 request log and trace correlation

Trace coverage for eight services and ordinary log delivery for eight services do
not establish log-to-trace correlation. The request log must name an actual span
in the exported trace, from the expected service and a current application pod.

The runtime images already include the OpenTelemetry Java agent. Logs travel
through Kubernetes stdout; the collector exports metrics and traces. This change
mounts `logback-correlation.xml` through an immutable, content-addressed ConfigMap.
It enables only the DispatcherServlet request logger at DEBUG and sends that
logger to a dedicated appender. Every event contains a fixed message and the
agent's active trace and span IDs. The pattern deliberately excludes the original
message and throwable, which could contain URLs, query parameters or request
data. Other application loggers retain the normal Boot console appender and
their configured levels. The logging configuration remains installed on success.

`deploy.sh` includes this configuration in new deployment bundles. Existing
deployments use `tools/cloudbank_log_correlation.py`. Both paths use identical XML
and reuse the existing image digests. This does not require a new MS64 target or
a new image build.

An exact existing installation can be probed again. The runner preserves it on
failure and requires a matching immutable ConfigMap; it does not adopt arbitrary
logging settings.

The integration gate runs a real Spring Boot 3.5.15 application with the pinned
OpenTelemetry Java agent 2.18.1. It checks log IDs against exported server spans,
preservation of ordinary application logging, and exclusion of synthetic header,
body and query markers from application logs. This fixture verifies the logging
mechanism; the live runner must independently observe the deployed agent's output.

## Windows execution

Use the SDK's bundled Python and the controller checkout containing this change.
The example assumes `$repo`, `$python`, and `$work` refer to the controller, Python
executable, and private directory containing the three signed/bound input files.
Set these variables to the operator's existing locations before running it.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $env:CLOUDSDK_CORE_ACCOUNT = 'howard.weale@gmail.com'
    $env:CLOUDSDK_CORE_PROJECT = 'lightyear-ms67-nonproduction'
    $env:PYTHONPATH = Join-Path $repo 'src'
    $env:LIGHTYEAR_NON_PRODUCTION_ACK = 'I-AUTHORIZE-MS67-NON-PRODUCTION-MUTATIONS'
    $tool = Join-Path $repo 'tools\cloudbank_log_correlation.py'
    $common = @('--project','lightyear-ms67-nonproduction','--region','us-west1',
        '--cluster','cloudbank-ms67','--namespace','cloudbank-ms67',
        '--signer','howard.weale@gmail.com',
        '--evidence-bucket','gs://lightyear-ms67-nonproduction-ms67-evidence/log-correlation')
    $inputs = @('--image-lock',"$work\image-lock.json",'--ms64-receipt',"$work\ms64-receipt.json",
        '--platform-profile',"$work\platform-profile.json")
    foreach ($file in @($python,$tool,"$work\image-lock.json","$work\ms64-receipt.json","$work\platform-profile.json")) {
        if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "Missing file: $file" }
    }
    gcloud container clusters get-credentials cloudbank-ms67 --region us-west1 --project lightyear-ms67-nonproduction
    if ($LASTEXITCODE -ne 0) { throw 'Cluster credentials failed' }
    & $python $tool preflight @common @inputs
    if ($LASTEXITCODE -ne 0) { throw 'Logging preflight failed; inspect its reason' }
    $run = Join-Path $work ('log-correlation-' + [guid]::NewGuid().ToString('N'))
    Write-Output "MS67_LOG_CORRELATION_RUN=$run"
    & $python $tool run @common @inputs --output-root $run
    if ($LASTEXITCODE -ne 0) { throw 'Logging rollout or correlation failed; inspect its recovery result' }
    & $python $tool verify @common @inputs --observation "$run\log-correlation.observation.json"
    if ($LASTEXITCODE -ne 0) { throw 'Independent correlation verification failed' }
    Write-Output 'MS67_LOG_CORRELATION_VERIFICATION=PASSED'
}
```

The runner verifies the current MS64 receipt, image lock, signed platform profile,
cluster and namespace identities, all eight image digests, and two ready replicas
per service. It refuses conflicting logging configuration and requires the
zero-unavailable rolling strategy. Before deployment mutations it writes a signed
checkpoint, uploads it with a generation precondition, and independently reads it
back. A Kubernetes Lease and deployment UID/resource-version checks fence other
executors and concurrent configuration edits. Services roll sequentially.

The probe sends one HTTP readiness request per service under a shared client trace
context. It then queries only Cloud Logging metadata and Cloud Trace span metadata.
Each passing row must match the trace ID, exact span ID, service, namespace,
cluster, current pod and bounded timestamps. The signed observation hashes those
identities and binds the profile, MS64 receipt, image lock and logging config.
This qualifies eight-service request log/trace correlation. It does not claim a
causal eight-service business transaction, metrics correlation, alert behavior,
whole MS67 completion or production readiness. Existing business journey and
alert evidence remain separate inputs to final admission.

## Interruption recovery

Normal failure handling restores the original logging configuration of each
deployment whose identity/specification still matches its checkpoint. It never
overwrites another operator's drift. It removes a newly created ConfigMap only
after proving it is unused; preexisting ConfigMaps are preserved. On a failed
restore the Lease remains held and the result reports `recovery-required`.

After the original process has stopped, download the exact printed
`MS67_LOG_CORRELATION_RECOVERY_STATE` URI and run:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $env:PYTHONPATH = Join-Path $repo 'src'
    $env:LIGHTYEAR_NON_PRODUCTION_ACK = 'I-AUTHORIZE-MS67-NON-PRODUCTION-MUTATIONS'
    $tool = Join-Path $repo 'tools\cloudbank_log_correlation.py'
    $common = @('--project','lightyear-ms67-nonproduction','--region','us-west1',
        '--cluster','cloudbank-ms67','--namespace','cloudbank-ms67',
        '--signer','howard.weale@gmail.com',
        '--evidence-bucket','gs://lightyear-ms67-nonproduction-ms67-evidence/log-correlation')
    # $checkpoint is the downloaded signed recovery JSON, outside the checkout.
    & $python $tool recover @common --recovery-state $checkpoint --original-process-stopped
    if ($LASTEXITCODE -ne 0) { throw 'Logging recovery still requires reconciliation' }
}
```

Recovery always fetches and verifies the newest generation at the checkpoint's
private URI. It restores the prior configuration; it does not create a passing
correlation observation. A completed installation is not eligible for this
interruption-recovery command.

The logging pattern uses the agent's [Logback MDC instrumentation](https://opentelemetry.io/docs/zero-code/java/agent/supported-libraries/)
and Google's [structured log trace/span fields](https://docs.cloud.google.com/logging/docs/structured-logging).
