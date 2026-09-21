# Compatible with the Windows PowerShell 5.1 shipped with Windows 10/11.
Set-StrictMode -Version Latest

function Assert-ChildPath([string]$Root, [string]$Path) {
    $base = [IO.Path]::GetFullPath($Root).TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
    $full = [IO.Path]::GetFullPath($Path)
    if (-not $full.StartsWith($base, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing a file operation outside the intended folder: $full"
    }
    return $full
}

function New-LocalDirectory([string]$Path) {
    if (Test-Path -LiteralPath $Path) {
        $item = Get-Item -LiteralPath $Path -Force
        if (-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw "Expected an ordinary local directory, not a file or junction: $Path"
        }
    } else {
        [IO.Directory]::CreateDirectory($Path) | Out-Null
    }
}

function Backup-Directory([string]$Root, [string]$Path) {
    $source = Assert-ChildPath $Root $Path
    if (-not (Test-Path -LiteralPath $source)) { return }
    New-LocalDirectory $source
    $destination = Assert-ChildPath $Root ($source + '.backup-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0, 6))
    Move-Item -LiteralPath $source -Destination $destination
    Write-Host "Preserved the previous environment at $destination"
}

function Invoke-Native([string]$Executable, [string[]]$Arguments) {
    if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) { throw "Executable not found: $Executable" }
    $previous = $ErrorActionPreference
    try {
        # Windows PowerShell treats native stderr as ErrorRecord objects even on success.
        $ErrorActionPreference = 'Continue'
        & $Executable @Arguments 2>&1 | ForEach-Object { Write-Host "$_" }
        $code = $LASTEXITCODE
    } finally { $ErrorActionPreference = $previous }
    if ($code -ne 0) { throw "$(Split-Path -Leaf $Executable) exited with code $code. See the log above." }
}

function Test-Python([string]$Executable) {
    if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) { return $false }
    if ($Executable -like '*\Microsoft\WindowsApps\*') { return $false }
    try {
        & $Executable -c "import sys,struct,venv,ensurepip,sysconfig; sys.exit(0 if (3,11)<=sys.version_info[:2]<(3,15) and struct.calcsize('P')==8 and not sysconfig.get_config_var('Py_GIL_DISABLED') else 1)" 2>$null | Out-Null
        return $LASTEXITCODE -eq 0
    } catch { return $false }
}

function Test-Tool([string]$Executable, [string]$Kind) {
    if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) { return $false }
    try {
        if ($Kind -eq 'node') {
            $version = (& $Executable --version 2>$null | Out-String).Trim()
            return $LASTEXITCODE -eq 0 -and $version -match '^v(\d+)\.' -and [int]$Matches[1] -ge 22
        }
        & $Executable -version 2>$null | Out-Null
        return $LASTEXITCODE -eq 0
    } catch { return $false }
}

function Find-SystemPython {
    $candidates = @()
    $commands = @(Get-Command python.exe -CommandType Application -All -ErrorAction SilentlyContinue)
    $candidates += @($commands | ForEach-Object { $_.Source })
    foreach ($hive in @('HKCU:\Software\Python\PythonCore', 'HKLM:\Software\Python\PythonCore')) {
        foreach ($key in @(Get-ChildItem -LiteralPath $hive -ErrorAction SilentlyContinue)) {
            $install = Get-Item -LiteralPath ($key.PSPath + '\InstallPath') -ErrorAction SilentlyContinue
            if ($install -and $install.GetValue('')) { $candidates += Join-Path $install.GetValue('') 'python.exe' }
        }
    }
    foreach ($candidate in @($candidates | Select-Object -Unique)) {
        if (Test-Python $candidate) { return $candidate }
    }
    return $null
}

function Get-Sha256([string]$Path) {
    $stream = [IO.File]::OpenRead($Path)
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($algorithm.ComputeHash($stream))).Replace('-', '').ToLowerInvariant() }
    finally { $stream.Dispose(); $algorithm.Dispose() }
}

function Test-Hash([string]$Path, [string]$Expected) {
    return (Test-Path -LiteralPath $Path -PathType Leaf) -and ((Get-Sha256 $Path) -eq $Expected)
}

function Save-HttpsFile([string]$Url, [string]$Path) {
    # Literal .NET file paths avoid PowerShell 5.1 OutFile wildcard handling for [brackets].
    $request = [Net.WebRequest]::Create($Url)
    $request.Timeout = 600000
    $request.ReadWriteTimeout = 600000
    $request.UserAgent = 'NoteFrame-Windows-Setup'
    $response = $null
    $inputStream = $null
    $outputStream = $null
    try {
        $response = $request.GetResponse()
        if ($response.ResponseUri.Scheme -ne 'https') { throw 'Refusing a download redirected away from HTTPS.' }
        $inputStream = $response.GetResponseStream()
        $outputStream = [IO.File]::Create($Path)
        $inputStream.CopyTo($outputStream)
    } finally {
        if ($outputStream) { $outputStream.Dispose() }
        if ($inputStream) { $inputStream.Dispose() }
        if ($response) { $response.Dispose() }
    }
}

function Get-VerifiedDownload([string]$Url, [string]$Destination, [string]$Sha256) {
    if ($Url -notmatch '^https://' -or $Sha256 -notmatch '^[a-fA-F0-9]{64}$') { throw 'Invalid dependency manifest.' }
    if (Test-Hash $Destination $Sha256) { Write-Host 'Using a verified cached download.'; return }
    $partial = $Destination + '.partial'
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        try {
            Write-Host "Downloading $(Split-Path -Leaf $Destination) (attempt $attempt/3)..."
            Save-HttpsFile $Url $partial
            if (-not (Test-Hash $partial $Sha256)) { throw 'SHA-256 verification failed; the download will not be executed.' }
            Move-Item -LiteralPath $partial -Destination $Destination -Force
            return
        } catch {
            if (Test-Path -LiteralPath $partial) { Remove-Item -LiteralPath $partial -Force }
            if ($attempt -eq 3) { throw "Download failed after 3 attempts: $Url`n$($_.Exception.Message)`nCheck your connection/proxy and retry setup.bat. HTTPS verification has not been disabled." }
            Start-Sleep -Seconds (2 * $attempt)
        }
    }
}

function Expand-VerifiedArchive([string]$Archive, [string]$Destination) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [IO.Compression.ZipFile]::OpenRead($Archive)
    try {
        foreach ($entry in $zip.Entries) {
            $null = Assert-ChildPath $Destination ([IO.Path]::Combine($Destination, $entry.FullName))
        }
    } finally { $zip.Dispose() }
    [IO.Compression.ZipFile]::ExtractToDirectory($Archive, $Destination)
}

function Install-LocalTool([string]$Root, [string]$Kind, $Spec) {
    $tools = Join-Path $Root '.tools'
    $cache = Join-Path $tools 'cache'
    New-LocalDirectory $cache
    $destination = Join-Path $tools $Kind
    $archive = Join-Path $cache ($Kind + '-' + $Spec.version + '.zip')
    Get-VerifiedDownload $Spec.url $archive $Spec.sha256
    $stage = Assert-ChildPath $tools (Join-Path $tools ('staging-' + [guid]::NewGuid().ToString('N')))
    try {
        Expand-VerifiedArchive $archive $stage
        $exe = Join-Path $stage $Spec.executable
        $valid = if ($Kind -eq 'python') { Test-Python $exe } else { Test-Tool $exe $Kind }
        if (-not $valid) { throw "Downloaded $Kind could not run. Check Windows/antivirus requirements; no system settings were changed." }
        Backup-Directory $tools $destination
        Move-Item -LiteralPath $stage -Destination $destination
        return Join-Path $destination $Spec.executable
    } finally {
        if (Test-Path -LiteralPath $stage) {
            $safeStage = Assert-ChildPath $tools $stage
            Remove-Item -LiteralPath $safeStage -Recurse -Force
        }
    }
}

function Resolve-Tools([string]$Root, $Manifest, [switch]$LocalTools, [switch]$NoDownload) {
    $resolved = @{}
    foreach ($kind in @('python', 'node', 'ffmpeg')) {
        $spec = $Manifest.$kind
        $local = Join-Path (Join-Path (Join-Path $Root '.tools') $kind) $spec.executable
        $candidate = $null
        $valid = if ($kind -eq 'python') { Test-Python $local } else { Test-Tool $local $kind }
        if ($valid) { $candidate = $local }
        if (-not $candidate -and -not $LocalTools) {
            if ($kind -eq 'python') {
                $candidate = Find-SystemPython
            } else {
                foreach ($command in @(Get-Command ($kind + '.exe') -CommandType Application -All -ErrorAction SilentlyContinue)) {
                    if (Test-Tool $command.Source $kind) { $candidate = $command.Source; break }
                }
            }
        }
        if ($kind -eq 'ffmpeg' -and $candidate) {
            if (-not (Test-Tool (Join-Path (Split-Path $candidate) 'ffprobe.exe') 'ffprobe')) { $candidate = $null }
        }
        if (-not $candidate) {
            if ($NoDownload) { throw "A compatible $kind was not found. Run setup.bat first." }
            $candidate = Install-LocalTool $Root $kind $spec
        }
        Write-Host "Using ${kind}: $candidate"
        $resolved[$kind] = $candidate
    }
    $env:PATH = (Split-Path $resolved.node) + ';' + (Split-Path $resolved.ffmpeg) + ';' + $env:PATH
    return $resolved
}

function Test-AppEnvironment([string]$Python) {
    if (-not (Test-Python $Python)) { return $false }
    try {
        & $Python -c "import fastapi,uvicorn,yt_dlp,cv2,numpy,PIL,reportlab,noteframe; from importlib.metadata import version; version('noteframe')" 2>$null | Out-Null
        if ($LASTEXITCODE -ne 0) { return $false }
        & $Python -m pip check --disable-pip-version-check 2>$null | Out-Null
        return $LASTEXITCODE -eq 0
    } catch { return $false }
}

function Get-EnvironmentStamp([string]$Root) {
    return (Get-Sha256 (Join-Path $Root 'pyproject.toml')) + '|' + $Root
}

function Set-UpEnvironment([string]$Root, [string]$BasePython, [switch]$AlwaysInstall) {
    $venv = Join-Path $Root '.venv'
    $python = Join-Path $venv 'Scripts\python.exe'
    $marker = Join-Path $venv '.noteframe-ready'
    $stamp = Get-EnvironmentStamp $Root
    $environmentReady = Test-AppEnvironment $python
    if (-not $environmentReady) {
        # pip can call a package 'already satisfied' even when its files are missing.
        # Rebuild in that case instead of repeatedly attempting an ineffective repair.
        Backup-Directory $Root $venv
        Write-Host 'Creating the isolated Python environment...'
        Invoke-Native $BasePython @('-m', 'venv', $venv)
    }
    $stampMatches = (Test-Path -LiteralPath $marker) -and ((Get-Content -LiteralPath $marker -Raw).Trim() -eq $stamp)
    if ($AlwaysInstall -or -not $stampMatches -or -not $environmentReady) {
        if (Test-Path -LiteralPath $marker) { Remove-Item -LiteralPath $marker }
        Invoke-Native $python @('-m', 'ensurepip', '--upgrade')
        Write-Host 'Installing NoteFrame and its Python dependencies...'
        Invoke-Native $python @('-m', 'pip', 'install', '--disable-pip-version-check', '--retries', '3', '--timeout', '30', '--prefer-binary', '-e', $Root)
        Invoke-Native $python @('-m', 'pip', 'check', '--disable-pip-version-check')
        if (-not (Test-AppEnvironment $python)) { throw 'The environment failed its import check. Rerun setup.bat; your notes are preserved.' }
        Set-Content -LiteralPath $marker -Value $stamp -Encoding UTF8
    } else { Write-Host 'Python dependencies are ready; no package download needed.' }
    return $python
}

function Assert-PortAvailable([int]$Port) {
    $listener = New-Object Net.Sockets.TcpListener([Net.IPAddress]::Loopback, $Port)
    try { $listener.Start() } catch {
        throw "Port $Port is already in use. If NoteFrame is running, open http://127.0.0.1:$Port. Otherwise choose another port with start.bat -Port 8768. No process was stopped."
    } finally { $listener.Stop() }
}

function Assert-WindowsPlatform {
    $arch = if ($env:PROCESSOR_ARCHITEW6432) { $env:PROCESSOR_ARCHITEW6432 } else { $env:PROCESSOR_ARCHITECTURE }
    if (-not [Environment]::Is64BitOperatingSystem -or $arch -ne 'AMD64') {
        throw 'Automatic setup supports Windows 10/11 x64. ARM64 and 32-bit Windows require manual dependency setup.'
    }
    if ([Environment]::OSVersion.Version.Major -lt 10) { throw 'Automatic setup requires Windows 10 or later.' }
}
