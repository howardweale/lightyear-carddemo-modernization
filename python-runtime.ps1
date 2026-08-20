$ErrorActionPreference = "Stop"

function Initialize-FactoryDarkPython {
    $candidates = @()

    if (-not [string]::IsNullOrWhiteSpace($env:LIGHTYEAR_PYTHON)) {
        $candidates += [pscustomobject]@{ Command = $env:LIGHTYEAR_PYTHON; Prefix = @() }
    }

    if (Get-Command py -ErrorAction SilentlyContinue) {
        foreach ($version in @("3.13", "3.12", "3.11", "3.14")) {
            $candidates += [pscustomobject]@{ Command = "py"; Prefix = @("-$version") }
        }
    }

    foreach ($command in @("python3.13", "python3.12", "python3.11", "python3.14", "python3", "python")) {
        if (Get-Command $command -ErrorAction SilentlyContinue) {
            $candidates += [pscustomobject]@{ Command = $command; Prefix = @() }
        }
    }

    foreach ($candidate in $candidates) {
        $command = $candidate.Command
        $prefix = @($candidate.Prefix)
        try {
            & $command @prefix -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" 2>$null
            if ($LASTEXITCODE -eq 0) {
                $script:FactoryDarkPythonCommand = $command
                $script:FactoryDarkPythonPrefix = $prefix
                $version = (& $command @prefix -c "import sys; print('.'.join(map(str, sys.version_info[:3])))").Trim()
                $display = ("Using Python ${version}: $command $($prefix -join ' ')").TrimEnd()
                Write-Host $display
                return
            }
        } catch {
            continue
        }
    }

    throw "FactoryDark requires Python 3.11 or newer. Set LIGHTYEAR_PYTHON or install a supported runtime."
}

function Invoke-FactoryDarkPython {
    # Windows PowerShell 5.1 turns ordinary native stderr (including unittest
    # progress) into PowerShell error records. Do not let those records become
    # terminating errors; callers still fail closed on the native exit code.
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & $script:FactoryDarkPythonCommand @script:FactoryDarkPythonPrefix @args
    } finally {
        $ErrorActionPreference = $previousPreference
    }
}

Initialize-FactoryDarkPython
