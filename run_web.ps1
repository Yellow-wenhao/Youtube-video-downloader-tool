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

$CondaExe = Resolve-CondaExe
$UseConda = $null -ne $CondaExe

Write-Host "Starting YouTube Downloader development workspace at $Url" -ForegroundColor Cyan
if ($UseConda) {
    Write-Host "Using conda environment: $CondaEnvName" -ForegroundColor DarkCyan
} else {
    Write-Host "Conda not found. Falling back to current Python: $PythonExe" -ForegroundColor Yellow
}

Push-Location $Root
try {
    if ($UseConda) {
        & $CondaExe run -n $CondaEnvName python -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('fastapi') and importlib.util.find_spec('uvicorn') else 1)"
    } else {
        & $PythonExe -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('fastapi') and importlib.util.find_spec('uvicorn') else 1)"
    }
    if ($LASTEXITCODE -ne 0) {
        if ($UseConda) {
            Write-Host "Missing dependencies in conda env '$CondaEnvName'. Run: conda run -n $CondaEnvName python -m pip install -U -r requirements.txt" -ForegroundColor Yellow
        } else {
            Write-Host "Missing dependencies in current Python. Run: $PythonExe -m pip install -U -r requirements.txt" -ForegroundColor Yellow
        }
        exit 1
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
