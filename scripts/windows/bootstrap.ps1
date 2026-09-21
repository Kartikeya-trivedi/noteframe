#Requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateSet('Setup', 'Start')][string]$Mode = 'Start',
    [ValidateRange(1024, 65535)][int]$Port = 8767,
    [switch]$Check,
    [switch]$NoBrowser,
    [switch]$NoPause,
    [switch]$LocalTools
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')
$taskRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$taskExit = 1
$taskLock = $null
$taskTranscript = $false
$taskLog = ''
$taskLocation = Get-Location
try {
    Assert-WindowsPlatform
    if ($taskRoot.StartsWith('\\')) { throw 'Extract NoteFrame to a local drive before running the batch scripts.' }
    if (-not (Test-Path -LiteralPath (Join-Path $taskRoot 'pyproject.toml'))) { throw 'Project files are missing. Extract the whole ZIP; do not run the BAT from inside an archive.' }
    Set-Location -LiteralPath $taskRoot
    New-LocalDirectory (Join-Path $taskRoot '.tools')
    New-LocalDirectory (Join-Path $taskRoot '.logs')
    $taskLog = Join-Path $taskRoot ('.logs\' + $Mode.ToLower() + '-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + $PID + '.log')
    Start-Transcript -LiteralPath $taskLog | Out-Null
    $taskTranscript = $true
    try {
        # Held for the whole launch so two launchers cannot mutate or run one environment simultaneously.
        $taskLock = [IO.File]::Open((Join-Path $taskRoot '.tools\bootstrap.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
    } catch { throw 'Another setup/launcher is using this project. Wait for it to finish or use the already open NoteFrame window.' }
    Write-Host "NoteFrame - $Mode" -ForegroundColor Green
    Write-Host "Project: $taskRoot"
    Write-Host "Log: $taskLog"
    if ($Mode -eq 'Start' -and -not $Check) { Assert-PortAvailable $Port }
    # Process-local environment only. Do not modify system PATH or execution policy.
    $env:PYTHONHOME = $null
    $env:PYTHONPATH = $null
    $env:PYTHONIOENCODING = 'utf-8'
    $env:PIP_DISABLE_PIP_VERSION_CHECK = '1'
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    $ProgressPreference = 'SilentlyContinue'
    $manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'downloads.json') -Raw | ConvertFrom-Json
    $tools = Resolve-Tools $taskRoot $manifest -LocalTools:$LocalTools -NoDownload:$Check
    if ($Check) {
        $python = Join-Path $taskRoot '.venv\Scripts\python.exe'
        if (-not (Test-AppEnvironment $python)) { throw 'The Python environment is missing or incomplete. Run setup.bat.' }
        Write-Host 'Dependency checks passed. No downloads or server startup were performed.' -ForegroundColor Green
    } else {
        $python = Set-UpEnvironment $taskRoot $tools.python -AlwaysInstall:($Mode -eq 'Setup')
        if ($Mode -eq 'Setup') {
            Write-Host 'Setup complete. Double-click start.bat to open NoteFrame.' -ForegroundColor Green
        } else {
            Assert-PortAvailable $Port
            $url = "http://127.0.0.1:$Port"
            Write-Host "Opening $url. Keep this window open; press Ctrl+C to stop."
            $launchArguments = @('-m', 'noteframe', 'serve', '--port', [string]$Port)
            if (-not $NoBrowser) { $launchArguments += '--open-browser' }
            Invoke-Native $python $launchArguments
        }
    }
    $taskExit = 0
} catch {
    Write-Host "`nNoteFrame could not finish: $($_.Exception.Message)" -ForegroundColor Red
    if ($taskLog) { Write-Host "Details: $taskLog" }
    Write-Host 'Fix the issue above and retry. Your .data notes have not been removed.'
} finally {
    if ($taskLock) { $taskLock.Dispose() }
    if ($taskTranscript) { Stop-Transcript | Out-Null }
    Set-Location -LiteralPath $taskLocation.Path
}
if (-not $NoPause -and -not [Console]::IsInputRedirected) {
    $null = Read-Host 'Press Enter to close this window'
}
exit $taskExit
