$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
        python -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
        & '.\.venv\Scripts\python.exe' -m pip install -e .
        if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    }
    Write-Host 'Open NoteFrame at http://127.0.0.1:8767. Press Ctrl+C to stop.'
    & '.\.venv\Scripts\python.exe' -m noteframe serve
} finally {
    Pop-Location
}
