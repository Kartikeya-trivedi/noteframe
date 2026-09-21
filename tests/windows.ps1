#Requires -Version 5.1
param([string]$Python)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
. (Join-Path $root 'scripts\windows\common.ps1')
if (-not $Python) { $Python = Join-Path $root '.venv\Scripts\python.exe' }
$sandbox = Join-Path $root ('.data\windows-tests-' + [guid]::NewGuid().ToString('N'))
New-LocalDirectory $sandbox
$script:Passed = 0
function Assert-True($Condition, [string]$Message) {
    if (-not $Condition) { throw "FAILED: $Message" }
    $script:Passed++
    Write-Host "PASS: $Message"
}
function Assert-Throws([scriptblock]$Action, [string]$Pattern, [string]$Message) {
    $caught = $null
    try { & $Action } catch { $caught = $_.Exception.Message }
    Assert-True ($caught -and $caught -like "*$Pattern*") $Message
}

Assert-Throws { Assert-ChildPath $sandbox $root } 'outside' 'Parent traversal is refused'
Assert-Throws { Assert-ChildPath $sandbox $sandbox } 'outside' 'Deleting the sandbox root is refused'
$oddPath = Join-Path $sandbox 'spaces & [brackets] ! (parentheses)'
New-LocalDirectory $oddPath
Assert-True (Test-Path -LiteralPath $oddPath -PathType Container) 'Special-character directories work'
$file = Join-Path $oddPath 'data.txt'
[IO.File]::WriteAllText($file, 'hello')
$expected = '2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824'
Assert-True (Test-Hash $file $expected) 'Known SHA-256 is accepted'
Assert-True (-not (Test-Hash $file ('0' * 64))) 'Corrupt SHA-256 is rejected'
Get-VerifiedDownload 'https://example.invalid/unused' $file $expected
Assert-True (([IO.File]::ReadAllText($file)) -eq 'hello') 'Verified cache works without network'

# Mock only the download transport; exercise the real integrity/retry logic.
$originalTransport = ${function:Save-HttpsFile}
$script:DownloadAttempts = 0
function Save-HttpsFile([string]$Url, [string]$Path) {
    $script:DownloadAttempts++
    [IO.File]::WriteAllText($Path, 'corrupt')
}
function Start-Sleep { param($Seconds) }
try {
    $bad = Join-Path $sandbox 'bad.zip'
    Assert-Throws { Get-VerifiedDownload 'https://example.invalid/bad' $bad $expected } 'SHA-256' 'Corrupt downloads fail closed'
    Assert-True ($script:DownloadAttempts -eq 3) 'Download attempts are bounded at three'
    Assert-True (-not (Test-Path -LiteralPath ($bad + '.partial'))) 'Failed partial download is removed'
    Assert-True (-not (Test-Path -LiteralPath $bad)) 'Corrupt archive never becomes the cache entry'
} finally {
    Set-Item Function:Save-HttpsFile $originalTransport
    Remove-Item Function:Start-Sleep
}

Add-Type -AssemblyName System.IO.Compression.FileSystem
$zipPath = Join-Path $sandbox 'unsafe.zip'
$zip = [IO.Compression.ZipFile]::Open($zipPath, 'Create')
try { $null = $zip.CreateEntry('../escaped.txt') } finally { $zip.Dispose() }
Assert-Throws { Expand-VerifiedArchive $zipPath (Join-Path $sandbox 'expanded') } 'outside' 'Archive path traversal is rejected'
Assert-True (-not (Test-Path -LiteralPath (Join-Path $sandbox 'escaped.txt'))) 'Archive writes remain inside extraction directory'

$broken = Join-Path $sandbox '.venv'
New-LocalDirectory $broken
[IO.File]::WriteAllText((Join-Path $broken 'keep.txt'), 'preserve me')
Backup-Directory $sandbox $broken
$backup = @(Get-ChildItem -LiteralPath $sandbox -Directory | Where-Object Name -like '.venv.backup-*')
Assert-True ($backup.Count -eq 1 -and (Test-Path -LiteralPath (Join-Path $backup[0].FullName 'keep.txt'))) 'Broken environments are backed up, not deleted'
Assert-Throws { Invoke-Native $Python @('-c', 'import sys; sys.exit(7)') } 'code 7' 'Native process failures propagate'

$listener = New-Object Net.Sockets.TcpListener([Net.IPAddress]::Loopback, 0)
$listener.Start()
try {
    $port = $listener.LocalEndpoint.Port
    Assert-Throws { Assert-PortAvailable $port } 'already in use' 'Occupied ports produce actionable errors'
} finally { $listener.Stop() }

foreach ($path in @(Get-ChildItem -LiteralPath (Join-Path $root 'scripts\windows') -Filter '*.ps1')) {
    $tokens = $null; $parseErrors = $null
    $null = [Management.Automation.Language.Parser]::ParseFile($path.FullName, [ref]$tokens, [ref]$parseErrors)
    Assert-True ($parseErrors.Count -eq 0) "$($path.Name) parses on Windows PowerShell 5.1"
}
Write-Host "$script:Passed Windows bootstrap checks passed. Fixtures retained at $sandbox"
