param(
  [ValidateSet("plan", "sign", "run", "verify")][string]$Command = "plan",
  [string]$Manifest = "$PSScriptRoot/factory/portfolio/carddemo-portfolio.json",
  [string]$Plan = "$PSScriptRoot/work/portfolio/carddemo-plan.json",
  [string]$Approval = "$PSScriptRoot/work/portfolio/human-approval.json",
  [string]$Output = "$PSScriptRoot/work/portfolio/carddemo-run"
)
$env:PYTHONPATH = "$PSScriptRoot/src"
$python = if (Get-Command python3.13 -ErrorAction SilentlyContinue) { "python3.13" } else { "python" }
if ($Command -eq "plan") { & $python -m lightyear_factory portfolio-plan --project-root $PSScriptRoot --manifest $Manifest --output $Plan }
elseif ($Command -eq "sign") {
  $approver = if ($env:LIGHTYEAR_PORTFOLIO_APPROVER) { $env:LIGHTYEAR_PORTFOLIO_APPROVER } else { "local-human-operator" }
  & $python -m lightyear_factory portfolio-sign --plan $Plan --output $Approval --approver $approver
}
elseif ($Command -eq "run") { & $python -m lightyear_factory portfolio-run --project-root $PSScriptRoot --manifest $Manifest --plan $Plan --approval $Approval --output-root $Output }
else {
  $verificationPlan = "$PSScriptRoot/work/portfolio-verify/carddemo-plan.json"
  & $python -m lightyear_factory portfolio-plan --project-root $PSScriptRoot --manifest $Manifest --output $verificationPlan | Out-Null
  if ($LASTEXITCODE -eq 0) { & $python -m lightyear_factory portfolio-validate --plan $verificationPlan }
}
exit $LASTEXITCODE
