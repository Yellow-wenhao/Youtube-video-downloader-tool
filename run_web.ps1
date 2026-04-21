param(
    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$HostName = "127.0.0.1"
$Port = 8000
$Url = "http://${HostName}:${Port}"
$CondaEnvName = if ($env:YTBDLP_CONDA_ENV) { $env:YTBDLP_CONDA_ENV } else { "base" }
$PythonExe = if ($env:YTBDLP_PYTHON) { $env:YTBDLP_PYTHON } else { "python" }

function Resolve-CondaExe {
    if ($env:CONDA_EXE -and (Test-Path -LiteralPath $env:CONDA_EXE)) {
        return $env:CONDA_EXE
    }

    $candidates = @(
        "$env:USERPROFILE\AppData\Local\miniconda3\Scripts\conda.exe",
        "$env:USERPROFILE\miniconda3\Scripts\conda.exe",
        "$env:USERPROFILE\anaconda3\Scripts\conda.exe"
    )

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) {
            return $candidate
        }
    }

    return $null
}

function Resolve-CurrentPythonExe {
    if ($env:YTBDLP_PYTHON) {
        return $env:YTBDLP_PYTHON
    }
    if ($env:CONDA_PREFIX) {
        $condaPython = Join-Path $env:CONDA_PREFIX "python.exe"
        if (Test-Path -LiteralPath $condaPython) {
            return $condaPython
        }
    }
    return "python"
}

$CondaExe = Resolve-CondaExe
$AlreadyInTargetCondaEnv = ($env:CONDA_DEFAULT_ENV -eq $CondaEnvName)
$UseConda = ($null -ne $CondaExe) -and (-not $AlreadyInTargetCondaEnv)
$PythonExe = Resolve-CurrentPythonExe

function Invoke-EnvironmentSelfCheck {
    if ($UseConda) {
        & $CondaExe run -n $CondaEnvName python -m app.core.startup_self_check | Out-Host
    } else {
        & $PythonExe -m app.core.startup_self_check | Out-Host
    }
    return $LASTEXITCODE
}

Write-Host "Starting YouTube Downloader development workspace at $Url" -ForegroundColor Cyan
if ($UseConda) {
    Write-Host "Using conda environment: $CondaEnvName" -ForegroundColor DarkCyan
} elseif ($AlreadyInTargetCondaEnv) {
    Write-Host "Already running inside conda environment: $CondaEnvName" -ForegroundColor DarkCyan
} else {
    Write-Host "Conda not found. Falling back to current Python: $PythonExe" -ForegroundColor Yellow
}

Push-Location $Root
try {
    $checkExitCode = Invoke-EnvironmentSelfCheck
    if ($checkExitCode -ne 0) {
        if ($UseConda) {
            Write-Host "Missing dependencies in conda env '$CondaEnvName'. Required: langgraph, fastapi, uvicorn, yt-dlp. Run: conda run -n $CondaEnvName python -m pip install -U -r requirements-dev.txt" -ForegroundColor Yellow
        } else {
            Write-Host "Missing dependencies in current Python. Required: langgraph, fastapi, uvicorn, yt-dlp. Run: $PythonExe -m pip install -U -r requirements-dev.txt" -ForegroundColor Yellow
        }
        exit 1
    }
    if ($CheckOnly) {
        exit 0
    }
    Start-Job -ScriptBlock {
        param($TargetUrl)
        Start-Sleep -Seconds 2
        Start-Process $TargetUrl
    } -ArgumentList $Url | Out-Null
    if ($UseConda) {
        & $CondaExe run --no-capture-output -n $CondaEnvName python -m uvicorn --app-dir $Root app.web.main:app --host $HostName --port $Port --reload
    } else {
        & $PythonExe -m uvicorn --app-dir $Root app.web.main:app --host $HostName --port $Port --reload
    }
}
finally {
    Pop-Location
}
