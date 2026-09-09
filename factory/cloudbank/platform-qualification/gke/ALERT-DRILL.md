# MS67 synthetic alert and recovery observation

The alert drill qualifies one synthetic Cloud Monitoring incident. It writes a
unique custom metric with values `0`, `1`, then `0`, observes the provider's
incident change from `OPEN` to `CLOSED`, and removes its policy and metric
descriptor. The policy has no notification channels. Applications, the collector,
secrets, existing metrics, and existing policies receive no mutations.

This observation covers the alert exercise within MS67. Eight-service telemetry
correlation and full platform admission remain separate requirements. Existing
MS65, MS66, and secret-rotation evidence is retained. The drill does not install
permanent service alert policies.

## Inputs and access

Use a clean controller checkout and the current signed MS64 receipt, its bound
eight-image lock, and an independently validated signed platform profile. The
profile must match the current cluster and namespace. Preflight checks the
non-production labels and all eight deployed image identities using read-only
requests. Recovery uses the signed run identity and does not require applications
to be ready.

The operator needs permission to read the cluster and evidence signing key,
read/write the private evidence prefix, read incidents and time series, write
time series, and create/read/delete custom metric descriptors and alert policies
in the specified project. The runner grants no IAM roles. Incident-list access
is checked before any Monitoring resource is created. Use one alert drill at a
time, and finish or recover it before starting another.

## Windows execution

Use Windows PowerShell with the authenticated Google Cloud SDK, Git, kubectl,
and the GKE authentication plugin. The controller's SDK adapter invokes
`gcloud.py` through Python and avoids the Windows `.cmd` subprocess issue.
Set the following paths to existing local files outside the checkout:

```powershell
$repo = 'C:\path\to\lightyear-carddemo-modernization'
$imageLock = 'C:\path\to\image-lock.json'
$ms64Receipt = 'C:\path\to\ms64-receipt.json'
$platformProfile = 'C:\path\to\platform-profile.json'
$env:CLOUDSDK_CORE_ACCOUNT = 'howard.weale@gmail.com'
$env:CLOUDSDK_CORE_PROJECT = 'lightyear-ms67-nonproduction'
$python = (gcloud info --format='value(basic.python_location)').Trim()
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $python)) { throw 'SDK Python unavailable' }
$env:PYTHONPATH = Join-Path $repo 'src'
$tool = Join-Path $repo 'tools\cloudbank_alert_drill.py'
$common = @(
  '--project', 'lightyear-ms67-nonproduction', '--region', 'us-west1',
  '--cluster', 'cloudbank-ms67', '--namespace', 'cloudbank-ms67',
  '--signer', 'howard.weale@gmail.com',
  '--evidence-bucket', 'gs://lightyear-ms67-nonproduction-ms67-evidence/alert-drill'
)
$inputs = @('--image-lock', $imageLock, '--ms64-receipt', $ms64Receipt,
            '--platform-profile', $platformProfile)
& $python $tool preflight @common @inputs
if ($LASTEXITCODE -ne 0) { throw 'Alert preflight failed' }
$env:LIGHTYEAR_NON_PRODUCTION_ACK = 'I-AUTHORIZE-MS67-NON-PRODUCTION-MUTATIONS'
$output = Join-Path $env:USERPROFILE ('ms67-alert-run-' + [guid]::NewGuid().ToString('N'))
& $python $tool run @common @inputs --output-root $output
if ($LASTEXITCODE -ne 0) { throw 'Read the bounded failure and recovery status before continuing' }
& $python $tool verify @common --observation (Join-Path $output 'alert-drill.observation.json')
if ($LASTEXITCODE -ne 0) { throw 'Independent alert verification failed' }
```

Keep the terminal and computer running until the command exits. This executor
runs locally; it is not a Cloud Build submission. Progress is printed every 20
seconds. Each observation phase has a 12-minute timeout. Baseline, firing, and
recovery require positive metric readback. Missing data retains the condition's
state. An absent incident, a mismatched incident, policy modification, policy
deletion, and automatic closure after 30 minutes cannot qualify recovery.

Successful completion requires `passed-synthetic-alert-and-recovery`,
`MS67_ALERT_EVIDENCE_READBACK=VERIFIED`, and a passing independent `verify`.
The signed observation records the same incident identity, metric-point hashes,
timestamps, input bindings, and confirmed resource removal. Tokens and API
response bodies are not persisted. The runner prints the private observation URI
and recovery-state URI.

## Interrupted execution

Stop the original process before recovery. Do not run recovery concurrently with
it. Download the printed `MS67_ALERT_RECOVERY_STATE` object to a local JSON file,
then invoke the same controller with the same `$common` context:

```powershell
& $python $tool recover @common --recovery-state $checkpoint --original-process-stopped
if ($LASTEXITCODE -ne 0) { throw 'Resource reconciliation is still required' }
```

The local file locates the latest signed, generation-pinned checkpoint in Cloud
Storage. Every resource mutation requires an uploaded and independently read-back
checkpoint. A stale writer or uncertain checkpoint stops further mutations.
This complements the requirement that the original process has stopped; Cloud
Storage and Monitoring cannot provide a single atomic transaction together.

Recovery removes only the recorded policy and uniquely named custom descriptor
whose ownership and configuration still match. It never retries an ambiguous
creation POST. A lost creation response requires positive identification of the
created resource; duplicate or missing candidates remain unresolved. Modified
resources are preserved for reconciliation. Recovery produces
`recovered-alert-drill`, which cannot pass the qualification verifier. After
confirmed cleanup, a new drill can collect fresh firing and recovery evidence.

## Provider references

The implementation uses the documented [incident list](https://docs.cloud.google.com/monitoring/api/ref_v3/rest/v3/projects.alerts/list)
and [incident fields](https://docs.cloud.google.com/monitoring/api/ref_v3/rest/v3/projects.alerts)
to observe the provider's state and policy association.
[Metric-threshold configuration](https://docs.cloud.google.com/monitoring/api/ref_v3/rest/v3/projects.alertPolicies)
defines the 60-second window and missing-data behavior. Creation of a
[custom metric descriptor](https://docs.cloud.google.com/monitoring/api/ref_v3/rest/v3/projects.metricDescriptors/create)
can become visible asynchronously, so the runner waits for readback without
issuing another creation request.
