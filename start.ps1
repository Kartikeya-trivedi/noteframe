# Compatibility entry point. Prefer double-clicking start.bat on Windows.
& (Join-Path $PSScriptRoot 'scripts\windows\bootstrap.ps1') -Mode Start @args
exit $LASTEXITCODE
