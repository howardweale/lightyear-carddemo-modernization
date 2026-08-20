param(
  [ValidateSet("plan", "sign", "run", "verify")][string]$Command = "plan",
  [string]$Manifest = "$PSScriptRoot/factory/portfolio/carddemo-portfolio.json",
  [string]$Plan = "$PSScriptRoot/work/portfolio/carddemo-plan.json",
  [string]$Approval = "$PSScriptRoot/work/portfolio/human-approval.json",
  [string]$Output = "$PSScriptRoot/work/portfolio/carddemo-run"
)
$env:PYTHONPATH = "$PSScriptRoot/src"
. (Join-Path $PSScriptRoot "python-runtime.ps1")
if ($Command -eq "plan") { Invoke-FactoryDarkPython -m lightyear_factory portfolio-plan --project-root $PSScriptRoot --manifest $Manifest --output $Plan }
elseif ($Command -eq "sign") {
  $approver = if ($env:LIGHTYEAR_PORTFOLIO_APPROVER) { $env:LIGHTYEAR_PORTFOLIO_APPROVER } else { "local-human-operator" }
  Invoke-FactoryDarkPython -m lightyear_factory portfolio-sign --plan $Plan --output $Approval --approver $approver
}
elseif ($Command -eq "run") { Invoke-FactoryDarkPython -m lightyear_factory portfolio-run --project-root $PSScriptRoot --manifest $Manifest --plan $Plan --approval $Approval --output-root $Output }
else {
  $verificationPlan = "$PSScriptRoot/work/portfolio-verify/carddemo-plan.json"
  Invoke-FactoryDarkPython -m lightyear_factory portfolio-plan --project-root $PSScriptRoot --manifest $Manifest --output $verificationPlan | Out-Null
  if ($LASTEXITCODE -eq 0) { Invoke-FactoryDarkPython -m lightyear_factory portfolio-validate --plan $verificationPlan }
}
exit $LASTEXITCODE
