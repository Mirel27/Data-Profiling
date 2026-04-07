$ErrorActionPreference = "Stop"

if (Get-Command py -ErrorAction SilentlyContinue) {
    $pythonCmd = "py"
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonCmd = "python"
} else {
    throw "No Python launcher found. Install Python or add it to PATH."
}

$venvPython = Join-Path ".venv" "Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    & $pythonCmd -m venv .venv
}

& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r requirements.txt
& $venvPython -m src simulate

Write-Host "Created or reused .venv, installed dependencies, and generated data/dwh/raw_demo.db"
